#!/usr/bin/env bash
#
# gemini_api_key_test.sh
# ----------------------
# GEMINI_API_KEY(Google AI Studio) 키를 curl 로 테스트한다.
#
# 두 가지 모드:
#   1) 표 모드(기본)  : 폴백 체인의 모든 모델을 순회하며 HTTP 코드·status·쿼터값을
#                       표로 출력한다. 어떤 모델이 무료 티어에서 실제로 붙는지, 3.x 가
#                       404(미지원)인지 429(쿼터 0/소진)인지 한눈에 판별한다.
#   2) 단일 모드      : GEMINI_MODEL 을 지정하면 그 모델 하나만 상세 검증한다.
#
# 키 탐색 순서:
#   1) 명령행 인자           : ./gemini_api_key_test.sh <API_KEY>
#   2) 환경변수 GEMINI_API_KEY
#   3) 프로젝트 루트의 .env  : GEMINI_API_KEY=...
#
# 테스트할 모델 목록 커스터마이즈(표 모드):
#   GEMINI_MODELS="gemini-2.5-flash,gemini-3.7-flash" ./tools/gemini_api_key_test.sh
#
# 사용 예:
#   export GEMINI_API_KEY=xxxx && ./tools/gemini_api_key_test.sh      # 전체 체인 표
#   ./tools/gemini_api_key_test.sh AIza...                            # 키를 인자로
#   GEMINI_MODEL=gemini-3.7-flash ./tools/gemini_api_key_test.sh      # 단일 모델만
#
set -euo pipefail

BASE="https://generativelanguage.googleapis.com/v1beta"

# 폴백 체인 기본 모델 목록 (scripts/dataset_review.py 의 build_model_chain 과 동일 순서).
# GEMINI_MODELS(쉼표/공백 구분)로 덮어쓸 수 있다.
DEFAULT_MODELS=(
  gemini-flash-latest
  gemini-3.7-flash
  gemini-3.6-flash
  gemini-3.5-flash
  gemini-3.5-flash-lite
  gemini-3.1-flash-lite
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
# GEMINI_MODEL(단일) 이 명시되면 단일 모드, 아니면 GEMINI_MODELS 또는 기본 체인으로 표 모드.
SINGLE_MODE=0
declare -a MODELS
if [ -n "${GEMINI_MODEL:-}" ]; then
  SINGLE_MODE=1
  MODELS=("${GEMINI_MODEL}")
elif [ -n "${GEMINI_MODELS:-}" ]; then
  # 쉼표/공백 구분 → 배열
  IFS=', ' read -r -a MODELS <<< "${GEMINI_MODELS}"
else
  MODELS=("${DEFAULT_MODELS[@]}")
fi

# 검증 요청 본문(모든 모델 공통, 최소 토큰).
REQ_BODY='{"contents":[{"parts":[{"text":"Reply with the single word: OK"}]}],"generationConfig":{"maxOutputTokens":8}}'

# ------------------------------------------------------------------------------
# probe_model <model>
#   한 모델을 호출하고 전역 변수(P_CODE/P_STATUS/P_QUOTA/P_NOTE/P_TIME/P_CLASS)를 채운다.
#   P_CLASS: ok | quota | notfound | auth | badreq | blocked | neterr | other
# ------------------------------------------------------------------------------
probe_model() {
  local model="$1"
  local resp code time_total
  resp="$(mktemp)"

  # http_code 와 time_total 을 마지막 줄에 함께 받는다.
  local metrics
  metrics="$(curl -sS -w '%{http_code} %{time_total}' -o "${resp}" \
    -X POST \
    -H 'Content-Type: application/json' \
    -H "x-goog-api-key: ${API_KEY}" \
    "${BASE}/models/${model}:generateContent" \
    -d "${REQ_BODY}" 2>/dev/null || echo "000 0")"
  code="${metrics%% *}"
  time_total="${metrics##* }"

  P_CODE="${code}"
  P_TIME="${time_total}s"
  P_STATUS=""
  P_QUOTA=""
  P_NOTE=""

  # 응답이 JSON 인지 확인(프록시/방화벽은 HTML 반환).
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
      if [ -n "${txt}" ]; then
        P_NOTE="응답=\"${txt}\""
      else
        # 200 이지만 본문 없음(예: thinking 예산 소진으로 빈 STOP).
        P_NOTE="빈 응답(finishReason=${fr:-?})"
      fi
    fi
    rm -f "${resp}"; return 0
  fi

  # ---- 비200: 오류 분류 ----
  if [ "${is_json}" -eq 0 ] && grep -qi '<html' "${resp}" 2>/dev/null; then
    P_CLASS="blocked"; P_STATUS="BLOCKED(HTML)"
    P_NOTE="프록시/방화벽 차단(비-Google 응답)"
    rm -f "${resp}"; return 0
  fi
  if [ "${code}" = "000" ]; then
    P_CLASS="neterr"; P_STATUS="NETWORK"
    P_NOTE="연결 실패(프록시/방화벽)"
    rm -f "${resp}"; return 0
  fi

  if [ "${HAS_JQ}" -eq 1 ] && [ "${is_json}" -eq 1 ]; then
    P_STATUS="$(jq -r '.error.status // empty' "${resp}" 2>/dev/null || true)"
    local msg
    msg="$(jq -r '.error.message // empty' "${resp}" 2>/dev/null || true)"
    # QuotaFailure 상세에서 쿼터 한도(quotaValue)와 metric/id 추출 → "0" 이면 무료 티어 미개방.
    local qv retry
    qv="$(jq -r '
      [ .error.details[]?
        | select((.["@type"] // "") | test("QuotaFailure"))
        | .violations[]?
        | ((.quotaId // .quotaMetric // "quota") + "=" + (.quotaValue // "?"))
      ] | unique | join(", ")' "${resp}" 2>/dev/null || true)"
    retry="$(jq -r '
      [ .error.details[]?
        | select((.["@type"] // "") | test("RetryInfo"))
        | .retryDelay ] | join("")' "${resp}" 2>/dev/null || true)"
    if [ -n "${qv}" ]; then
      P_QUOTA="${qv}"
      [ -n "${retry}" ] && P_QUOTA="${P_QUOTA} (retry ${retry})"
    elif [ -n "${retry}" ]; then
      P_QUOTA="retry ${retry}"
    fi
    [ -z "${P_QUOTA}" ] && [ -n "${msg}" ] && P_NOTE="${msg:0:70}"
  else
    P_STATUS="HTTP ${code}"
    P_NOTE="$(tr -d '\n' < "${resp}" | head -c 70)"
    [ "${HAS_JQ}" -eq 0 ] && P_NOTE="${P_NOTE}  (jq 설치 시 쿼터 상세 표시)"
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

# 클래스 → 색상/아이콘
class_deco() {
  case "$1" in
    ok)       ICON="${GREEN}✓${RESET}"; COL="${GREEN}" ;;
    quota)    ICON="${RED}✗${RESET}";   COL="${RED}" ;;
    notfound) ICON="${YELLOW}?${RESET}"; COL="${YELLOW}" ;;
    auth)     ICON="${RED}✗${RESET}";   COL="${RED}" ;;
    badreq)   ICON="${YELLOW}!${RESET}"; COL="${YELLOW}" ;;
    blocked|neterr) ICON="${YELLOW}!${RESET}"; COL="${YELLOW}" ;;
    *)        ICON="${RED}✗${RESET}";   COL="${RED}" ;;
  esac
}

echo "${BOLD}Gemini API 키 테스트${RESET}"
echo "  키    : ${MASKED} (길이 ${#API_KEY})"
if [ "${SINGLE_MODE}" -eq 1 ]; then
  echo "  모드  : 단일 모델(${MODELS[0]})"
else
  echo "  모드  : 표(모델 ${#MODELS[@]}개)"
fi
echo

# ---- 표 헤더 ----
HDR_FMT="%b%-24s %-5s %-18s %-9s %-40s%b\n"
ROW_FMT="%b%-24s %-5s %-18s %-9s %-40s%b\n"
printf "${HDR_FMT}" "${BOLD}" "MODEL" "HTTP" "STATUS" "TIME" "QUOTA / NOTE" "${RESET}"
printf "%s\n" "$(printf '─%.0s' $(seq 1 100))"

# ---- 순회 ----
N_OK=0; N_QUOTA=0; N_NOTFOUND=0; N_OTHER=0
FIRST_OK=""
for m in "${MODELS[@]}"; do
  [ -z "${m}" ] && continue
  probe_model "${m}"
  class_deco "${P_CLASS}"
  DETAIL="${P_QUOTA}"
  [ -z "${DETAIL}" ] && DETAIL="${P_NOTE}"
  [ -z "${DETAIL}" ] && DETAIL="-"
  printf "${ROW_FMT}" "${COL}" "${m}" "${P_CODE}" "${P_STATUS}" "${P_TIME}" "${DETAIL:0:40}" "${RESET}"
  case "${P_CLASS}" in
    ok)       N_OK=$((N_OK+1)); [ -z "${FIRST_OK}" ] && FIRST_OK="${m}" ;;
    quota)    N_QUOTA=$((N_QUOTA+1)) ;;
    notfound) N_NOTFOUND=$((N_NOTFOUND+1)) ;;
    *)        N_OTHER=$((N_OTHER+1)) ;;
  esac
done

echo
echo "${BOLD}요약${RESET}: ${GREEN}OK ${N_OK}${RESET} · ${RED}429/쿼터 ${N_QUOTA}${RESET} · ${YELLOW}404/미지원 ${N_NOTFOUND}${RESET} · 기타 ${N_OTHER}"
if [ -n "${FIRST_OK}" ]; then
  ok "이 키로 실제 붙는 첫 모델: ${BOLD}${FIRST_OK}${RESET}"
fi
echo "${DIM}해설: QUOTA 열의 '...=0' 은 무료 티어 미개방(한도 0), 429 는 쿼터 소진/레이트리밋,${RESET}"
echo "${DIM}      404(STATUS=NOT_FOUND) 는 그 모델 ID 자체가 없음을 의미합니다.${RESET}"

# 종료 코드: OK 가 하나도 없으면 1, 있으면 0.
if [ "${N_OK}" -eq 0 ]; then
  err "정상 동작하는 모델이 없습니다."
  # 흔한 원인 힌트
  if [ "${N_QUOTA}" -gt 0 ] && [ "${N_OK}" -eq 0 ]; then
    warn "모든 모델이 429 입니다: 무료 일일 쿼터 소진이거나 키에 결제(빌링)가 없어 3.x 한도가 0일 수 있습니다."
  fi
  exit 1
fi
exit 0
