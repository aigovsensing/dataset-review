#!/usr/bin/env bash
#
# gemini_api_key_test.sh
# ----------------------
# GEMINI_API_KEY(Google AI Studio) 키가 정상 동작하는지 curl 로 테스트한다.
#
# 키 탐색 순서:
#   1) 명령행 인자           : ./gemini_api_key_test.sh <API_KEY>
#   2) 환경변수 GEMINI_API_KEY
#   3) 프로젝트 루트의 .env  : GEMINI_API_KEY=...
#
# 사용 예:
#   export GEMINI_API_KEY=xxxx && ./tools/gemini_api_key_test.sh
#   ./tools/gemini_api_key_test.sh AIza...
#   GEMINI_MODEL=gemini-2.5-flash ./tools/gemini_api_key_test.sh
#
set -euo pipefail

MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
BASE="https://generativelanguage.googleapis.com/v1beta"

# ---- 색상 ----
if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
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
echo "${BOLD}Gemini API 키 테스트${RESET}"
echo "  키    : ${MASKED} (길이 ${#API_KEY})"
echo "  모델  : ${MODEL}"
echo

# ---- 실제 generateContent 호출 ----
REQ_BODY='{"contents":[{"parts":[{"text":"Reply with the single word: OK"}]}]}'
RESP_FILE="$(mktemp)"
trap 'rm -f "${RESP_FILE}"' EXIT

HTTP_CODE="$(curl -sS -w '%{http_code}' -o "${RESP_FILE}" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H "x-goog-api-key: ${API_KEY}" \
  "${BASE}/models/${MODEL}:generateContent" \
  -d "${REQ_BODY}" || echo "000")"

echo "HTTP 상태 코드: ${HTTP_CODE}"

# 응답이 JSON 인지(첫 non-space 문자가 '{') 확인 — 프록시 차단 등은 HTML 을 반환한다.
IS_JSON=0
if [ -s "${RESP_FILE}" ] && [ "$(tr -d '[:space:]' < "${RESP_FILE}" | head -c1)" = "{" ]; then
  IS_JSON=1
fi

if [ "${HTTP_CODE}" = "200" ]; then
  if [ "${HAS_JQ}" -eq 1 ] && [ "${IS_JSON}" -eq 1 ]; then
    TEXT="$(jq -r '.candidates[0].content.parts[0].text // empty' "${RESP_FILE}" 2>/dev/null || true)"
    ok "API 키 정상 동작 (generateContent 성공)"
    [ -n "${TEXT}" ] && echo "  모델 응답: ${TEXT}"
  else
    ok "API 키 정상 동작 (HTTP 200). 응답 본문 일부:"
    head -c 400 "${RESP_FILE}"; echo
  fi
  exit 0
fi

# ---- 실패 처리 ----
err "테스트 실패 (HTTP ${HTTP_CODE})"

# 프록시/방화벽이 HTML 로 차단한 경우 (예: "Generative AI policy_denied")
if [ "${IS_JSON}" -eq 0 ] && grep -qi '<html' "${RESP_FILE}" 2>/dev/null; then
  warn "Google API 가 아닌 프록시/방화벽의 차단 응답(HTML)을 받았습니다."
  warn "이 네트워크에서 generativelanguage.googleapis.com 접근이 차단된 것으로 보입니다."
  echo "  (참고: 차단이 없는 환경 - 예: GitHub Actions - 에서는 정상 동작합니다.)" >&2
elif [ "${HAS_JQ}" -eq 1 ] && [ "${IS_JSON}" -eq 1 ]; then
  STATUS="$(jq -r '.error.status // empty' "${RESP_FILE}" 2>/dev/null || true)"
  MSG="$(jq -r '.error.message // empty' "${RESP_FILE}" 2>/dev/null || true)"
  [ -n "${STATUS}" ] && echo "  status : ${STATUS}" >&2
  [ -n "${MSG}" ]    && echo "  message: ${MSG}" >&2
else
  head -c 600 "${RESP_FILE}" >&2; echo >&2
fi

case "${HTTP_CODE}" in
  400) warn "요청 형식 오류 또는 API 키 형식이 잘못되었을 수 있습니다." ;;
  401|403) warn "인증 실패 또는 접근 차단: 키가 유효하지 않거나, API 권한/네트워크 정책을 확인하세요." ;;
  404) warn "모델(${MODEL})을 찾을 수 없습니다. GEMINI_MODEL 값을 확인하세요." ;;
  429) warn "쿼터 초과: 잠시 후 재시도하거나 무료 티어 한도를 확인하세요." ;;
  000) warn "네트워크 연결 실패 (프록시/방화벽 확인)." ;;
esac
exit 1
