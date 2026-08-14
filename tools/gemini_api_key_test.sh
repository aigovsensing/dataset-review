#!/usr/bin/env bash
#
# gemini_api_key_test.sh
# ----------------------
# GEMINI_API_KEY(Google AI Studio) 키를 curl 로 테스트한다.
#
# 표 모드(기본): 폴백 체인의 모든 모델을 순회하며, 각 모델을
#   (1) 그라운딩 없이(PLAIN)  (2) google_search 그라운딩 포함(GROUND)
# 두 방식으로 호출해 HTTP 코드·status·쿼터값을 나란히 출력한다.
# 무료 티어에서 3.x 가 왜 막히는지 — 모델 자체 쿼터(0)인지, 아니면
# '그라운딩 도구'의 별도 쿼터 때문인지 — 를 한 번에 판별하기 위함이다.
#
#   PLAIN=200, GROUND=429  →  모델은 무료로 되는데 그라운딩만 막힘
#                             ⇒ 3.x 를 '그라운딩 끄고' 쓰면 무료로 결과 획득 가능
#   PLAIN=429, GROUND=429  →  모델 자체가 무료 티어 한도 0(유료 전용)
#   PLAIN=404              →  그 모델 ID 자체가 없음
#
# 단일 모드: GEMINI_MODEL 을 지정하면 그 모델 하나만(양쪽 방식) 검증한다.
#
# 키 탐색 순서:
#   1) 명령행 인자           : ./gemini_api_key_test.sh <API_KEY>
#   2) 환경변수 GEMINI_API_KEY
#   3) 프로젝트 루트의 .env  : GEMINI_API_KEY=...
#
# 옵션(환경변수):
#   GEMINI_MODELS="a,b,c"  표 모드에서 테스트할 모델 목록 덮어쓰기
#   NO_GROUNDING=1         GROUND 열(그라운딩 호출) 생략, PLAIN 만 테스트
#
# 사용 예:
#   export GEMINI_API_KEY=xxxx && ./tools/gemini_api_key_test.sh
#   ./tools/gemini_api_key_test.sh AIza...
#   GEMINI_MODEL=gemini-3.7-flash ./tools/gemini_api_key_test.sh
#
set -euo pipefail

BASE="https://generativelanguage.googleapis.com/v1beta"

# 폴백 체인 기본 모델 목록 (scripts/dataset_review.py 의 build_model_chain 과 동일 순서).
# 끝에 gemini-3-flash-preview 를 덧붙여 프리뷰 변형이 무료로 열려 있는지도 함께 본다.
# GEMINI_MODELS(쉼표/공백 구분)로 덮어쓸 수 있다.
DEFAULT_MODELS=(
  gemini-flash-latest
  gemini-3.7-flash
  gemini-3.6-flash
  gemini-3.5-flash
  gemini-3.5-flash-lite
  gemini-3.1-flash-lite
  gemini-3-flash-preview
  gemini-2.5-flash
  gemini-2.5-flash-lite
)

# ---- 색상 ----
if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; DIM=""; BOLD=""; RESET=""
fi
ok()   { echo "${GREEN}✓${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET} $*"; }
err()  { echo "${RED}✗${RESET} $*" >&2; }

# ---- 의존성 확인 ----
command -v curl >/dev/null 2>&1 || { err "curl 이 필요합니다."; exit 1; }
HAS_JQ=0
command -v jq >/dev/null 2>&1 && HAS_JQ=1

# ---- API 키 확보 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

API_KEY="${1:-${GEMINI_API_KEY:-}}"
if [ -z "${API_KEY}" ] && [ -f "${PROJECT_ROOT}/.env" ]; then
  API_KEY="$(grep -E '^[[:space:]]*GEMINI_API_KEY[[:space:]]*=' "${PROJECT_ROOT}/.env" \
             | tail -n1 | cut -d= -f2- | tr -d '"'"'"' \r' | xargs || true)"
  [ -n "${API_KEY}" ] && warn ".env 에서 GEMINI_API_KEY 를 읽었습니다."
fi

if [ -z "${API_KEY}" ]; then
  err "GEMINI_API_KEY 를 찾을 수 없습니다."
  echo "  다음 중 하나로 제공하세요:" >&2
  echo "    export GEMINI_API_KEY=<키>" >&2
  echo "    ./tools/gemini_api_key_test.sh <키>" >&2
  echo "    프로젝트 .env 에 GEMINI_API_KEY=<키> 추가" >&2
  exit 2
fi

MASKED="${API_KEY:0:6}…${API_KEY: -4}"

# ---- 테스트할 모델 목록 결정 ----
SINGLE_MODE=0
declare -a MODELS
if [ -n "${GEMINI_MODEL:-}" ]; then
  SINGLE_MODE=1
  MODELS=("${GEMINI_MODEL}")
elif [ -n "${GEMINI_MODELS:-}" ]; then
  IFS=', ' read -r -a MODELS <<< "${GEMINI_MODELS}"
else
  MODELS=("${DEFAULT_MODELS[@]}")
fi

DO_GROUND=1
[ "${NO_GROUNDING:-0}" = "1" ] && DO_GROUND=0

# 검증 요청 본문(최소 토큰). PLAIN 은 도구 없음, GROUND 는 google_search 그라운딩 부착.
REQ_PLAIN='{"contents":[{"parts":[{"text":"Reply with the single word: OK"}]}],"generationConfig":{"maxOutputTokens":8}}'
REQ_GROUND='{"contents":[{"parts":[{"text":"Reply with the single word: OK"}]}],"tools":[{"google_search":{}}],"generationConfig":{"maxOutputTokens":16}}'

# ------------------------------------------------------------------------------
# probe <model> <body>
#   호출 후 전역 P_CODE/P_STATUS/P_QUOTA/P_NOTE/P_TIME/P_CLASS 를 채운다.
#   P_CLASS: ok | quota | notfound | auth | badreq | blocked | neterr | other
# ------------------------------------------------------------------------------
probe() {
  local model="$1" body="$2"
  local resp code time_total metrics
  resp="$(mktemp)"
  metrics="$(curl -sS -w '%{http_code} %{time_total}' -o "${resp}" \
    -X POST \
    -H 'Content-Type: application/json' \
    -H "x-goog-api-key: ${API_KEY}" \
    "${BASE}/models/${model}:generateContent" \
    -d "${body}" 2>/dev/null || echo "000 0")"
  code="${metrics%% *}"; time_total="${metrics##* }"
  P_CODE="${code}"; P_TIME="${time_total}s"; P_STATUS=""; P_QUOTA=""; P_NOTE=""

  local is_json=0
  if [ -s "${resp}" ] && [ "$(tr -d '[:space:]' < "${resp}" | head -c1)" = "{" ]; then
    is_json=1
  fi

  if [ "${code}" = "200" ]; then
    P_CLASS="ok"; P_STATUS="OK"
    if [ "${HAS_JQ}" -eq 1 ] && [ "${is_json}" -eq 1 ]; then
      local txt fr
      txt="$(jq -r '.candidates[0].content.parts[0].text // empty' "${resp}" 2>/dev/null | tr -d '\n' || true)"
      fr="$(jq -r '.candidates[0].finishReason // empty' "${resp}" 2>/dev/null || true)"
      if [ -n "${txt}" ]; then P_NOTE="응답=\"${txt}\""; else P_NOTE="빈 응답(finishReason=${fr:-?})"; fi
    fi
    rm -f "${resp}"; return 0
  fi

  if [ "${is_json}" -eq 0 ] && grep -qi '<html' "${resp}" 2>/dev/null; then
    P_CLASS="blocked"; P_STATUS="BLOCKED(HTML)"; P_NOTE="프록시/방화벽 차단"
    rm -f "${resp}"; return 0
  fi
  if [ "${code}" = "000" ]; then
    P_CLASS="neterr"; P_STATUS="NETWORK"; P_NOTE="연결 실패"
    rm -f "${resp}"; return 0
  fi

  if [ "${HAS_JQ}" -eq 1 ] && [ "${is_json}" -eq 1 ]; then
    P_STATUS="$(jq -r '.error.status // empty' "${resp}" 2>/dev/null || true)"
    local msg qv retry
    msg="$(jq -r '.error.message // empty' "${resp}" 2>/dev/null || true)"
    qv="$(jq -r '
      [ .error.details[]?
        | select((.["@type"] // "") | test("QuotaFailure"))
        | .violations[]?
        | ((.quotaId // .quotaMetric // "quota") + "=" + (.quotaValue // "?"))
      ] | unique | join(", ")' "${resp}" 2>/dev/null || true)"
    retry="$(jq -r '
      [ .error.details[]? | select((.["@type"] // "") | test("RetryInfo")) | .retryDelay ] | join("")' "${resp}" 2>/dev/null || true)"
    if [ -n "${qv}" ]; then
      P_QUOTA="${qv}"; [ -n "${retry}" ] && P_QUOTA="${P_QUOTA} (retry ${retry})"
    elif [ -n "${retry}" ]; then
      P_QUOTA="retry ${retry}"
    fi
    [ -z "${P_QUOTA}" ] && [ -n "${msg}" ] && P_NOTE="${msg:0:70}"
  else
    P_STATUS="HTTP ${code}"; P_NOTE="$(tr -d '\n' < "${resp}" | head -c 70)"
    [ "${HAS_JQ}" -eq 0 ] && P_NOTE="${P_NOTE}  (jq 설치 시 쿼터 상세)"
  fi

  case "${code}" in
    401|403) P_CLASS="auth" ;;
    404)     P_CLASS="notfound" ;;
    400)     P_CLASS="badreq" ;;
    429)     P_CLASS="quota" ;;
    *)       P_CLASS="other" ;;
  esac
  [ -z "${P_STATUS}" ] && P_STATUS="HTTP ${code}"
  rm -f "${resp}"; return 0
}

# 코드 → 색상 조각(표 셀용)
code_col() {
  case "$1" in
    200) printf "%b%-4s%b" "${GREEN}" "$1" "${RESET}" ;;
    429) printf "%b%-4s%b" "${RED}" "$1" "${RESET}" ;;
    404|400) printf "%b%-4s%b" "${YELLOW}" "$1" "${RESET}" ;;
    -)   printf "%-4s" "-" ;;
    *)   printf "%b%-4s%b" "${RED}" "$1" "${RESET}" ;;
  esac
}

echo "${BOLD}Gemini API 키 테스트${RESET}"
echo "  키    : ${MASKED} (길이 ${#API_KEY})"
if [ "${SINGLE_MODE}" -eq 1 ]; then
  echo "  모드  : 단일 모델(${MODELS[0]})"
else
  echo "  모드  : 표(모델 ${#MODELS[@]}개)${DO_GROUND:+, PLAIN+GROUND 비교}"
fi
echo

# ---- 표 헤더 ----
printf "%b%-24s %-4s %-4s  %-18s %-34s%b\n" "${BOLD}" "MODEL" "PLN" "GRD" "STATUS(대표)" "QUOTA / NOTE" "${RESET}"
printf "%s\n" "$(printf '─%.0s' $(seq 1 92))"

N_PLAIN_OK=0; N_GROUND_OK=0; N_GROUND_ONLY_FAIL=0
FIRST_PLAIN_OK=""; FIRST_GROUND_OK=""
for m in "${MODELS[@]}"; do
  [ -z "${m}" ] && continue

  probe "${m}" "${REQ_PLAIN}"
  local_plain_code="${P_CODE}"; local_plain_class="${P_CLASS}"
  plain_status="${P_STATUS}"; plain_quota="${P_QUOTA}"; plain_note="${P_NOTE}"

  ground_code="-"; ground_class="skip"; ground_status=""; ground_quota=""; ground_note=""
  if [ "${DO_GROUND}" -eq 1 ]; then
    probe "${m}" "${REQ_GROUND}"
    ground_code="${P_CODE}"; ground_class="${P_CLASS}"
    ground_status="${P_STATUS}"; ground_quota="${P_QUOTA}"; ground_note="${P_NOTE}"
  fi

  # 대표 STATUS/QUOTA: 실패한 쪽(특히 그라운딩)이 흥미로우므로 우선 노출.
  rep_status="${plain_status}"; rep_detail="${plain_quota:-${plain_note}}"
  if [ "${DO_GROUND}" -eq 1 ] && [ "${ground_code}" != "200" ]; then
    rep_status="${ground_status}"; rep_detail="${ground_quota:-${ground_note}}"
  elif [ "${local_plain_code}" = "200" ] && { [ "${DO_GROUND}" -eq 0 ] || [ "${ground_code}" = "200" ]; }; then
    rep_status="OK"; rep_detail="${plain_note}"
  fi
  [ -z "${rep_detail}" ] && rep_detail="-"

  printf "%-24s " "${m}"
  code_col "${local_plain_code}"; printf " "
  code_col "${ground_code}"; printf "  "
  printf "%-18s %-34s\n" "${rep_status:0:18}" "${rep_detail:0:34}"

  [ "${local_plain_code}" = "200" ] && { N_PLAIN_OK=$((N_PLAIN_OK+1)); [ -z "${FIRST_PLAIN_OK}" ] && FIRST_PLAIN_OK="${m}"; }
  if [ "${DO_GROUND}" -eq 1 ]; then
    [ "${ground_code}" = "200" ] && { N_GROUND_OK=$((N_GROUND_OK+1)); [ -z "${FIRST_GROUND_OK}" ] && FIRST_GROUND_OK="${m}"; }
    # 모델은 되는데(PLAIN 200) 그라운딩만 막힌(GROUND 429/403) 경우 집계
    if [ "${local_plain_code}" = "200" ] && [ "${ground_code}" != "200" ] && [ "${ground_code}" != "-" ]; then
      N_GROUND_ONLY_FAIL=$((N_GROUND_ONLY_FAIL+1))
    fi
  fi
done

echo
echo "${BOLD}요약${RESET}  PLAIN(도구없음) OK ${GREEN}${N_PLAIN_OK}${RESET}   |   GROUND(그라운딩) OK ${GREEN}${N_GROUND_OK}${RESET}"
[ -n "${FIRST_PLAIN_OK}" ]  && ok "도구 없이 붙는 첫 모델      : ${BOLD}${FIRST_PLAIN_OK}${RESET}"
[ "${DO_GROUND}" -eq 1 ] && [ -n "${FIRST_GROUND_OK}" ] && ok "그라운딩까지 되는 첫 모델   : ${BOLD}${FIRST_GROUND_OK}${RESET}"
echo
echo "${DIM}판독:${RESET}"
echo "${DIM}  PLN=200, GRD=429  → 모델은 무료 OK, '그라운딩'만 막힘 ⇒ 3.x 를 그라운딩 끄고 쓰면 무료로 결과 획득${RESET}"
echo "${DIM}  PLN=429, GRD=429  → 모델 자체가 무료 한도 0(유료 전용)${RESET}"
echo "${DIM}  PLN=404           → 그 모델 ID 자체가 없음${RESET}"
echo "${DIM}  QUOTA '…=0' 은 무료 티어 미개방(한도 0) 을 뜻함${RESET}"

if [ "${DO_GROUND}" -eq 1 ] && [ "${N_GROUND_ONLY_FAIL}" -gt 0 ]; then
  warn "모델은 무료로 되는데 그라운딩만 막힌 케이스 ${N_GROUND_ONLY_FAIL}건 → 그라운딩 조건부 비활성화로 무료 3.x 사용 가능성 있음."
fi

# 종료 코드: PLAIN 이든 GROUND 든 하나도 200 이 없으면 1.
if [ "${N_PLAIN_OK}" -eq 0 ] && [ "${N_GROUND_OK}" -eq 0 ]; then
  err "정상 동작하는 모델이 없습니다."
  exit 1
fi
exit 0
