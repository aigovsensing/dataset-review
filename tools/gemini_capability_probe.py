#!/usr/bin/env python3
"""Gemini API 키별·모델별 '도구 사용 가능 여부'를 실측하는 진단 도구 (표준 라이브러리만 사용).

각 (키, 모델)에 대해 아래 4가지를 아주 작은 요청으로 시도해 HTTP 상태와 실제 동작을 표로 보여 준다.
  PLAIN   : 도구 없이 생성
  SEARCH  : google_search 그라운딩 (검색 근거가 실제로 붙었는지까지 확인)
  URLCTX  : url_context 도구 (지정한 URL 을 실제로 읽었는지까지 확인)
  (참고) 모델 목록(ListModels)에 해당 모델이 있는지

출력에는 API 키 값을 절대 넣지 않는다(키는 Secret 변수명으로만 표기, 같은 값은 한 줄로 묶음).

환경 변수
  GEMINI_API_KEY, GEMINI_API_KEY_<이름> ... : 점검할 키(워크플로가 Secret 을 매핑)
  PROBE_MODELS : 쉼표로 구분한 모델 목록(기본값은 DEFAULT_MODELS)
  PROBE_DELAY  : 호출 사이 대기 초(기본 3) — 무료 티어 분당 한도(RPM) 보호
  GITHUB_STEP_SUMMARY : 있으면 표를 Actions 요약 화면에도 기록
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODELS = (
    "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite,"
    "gemini-3.6-flash,gemini-3.8-flash,gemini-3-flash-preview"
)
KEY_NAME_RE = re.compile(r"^GEMINI_API_KEY(?:_[A-Z0-9_]+)?$")
SEARCH_PROMPT = "Which license is the CelebA face attributes dataset released under? Answer in one short sentence."
URL_PROMPT = ("Read https://huggingface.co/datasets/stanfordnlp/imdb and tell me the license "
              "stated on that page, in one short sentence.")
PLAIN_PROMPT = "Reply with the single word: pong"


def collect_keys(env=None) -> list[tuple[list[str], str]]:
    """[(Secret 변수명 목록, 키 값)] — 같은 값은 한 항목으로 묶는다."""
    env = os.environ if env is None else env
    by_value: dict[str, list[str]] = {}
    for name in sorted(n for n in env if KEY_NAME_RE.fullmatch(n)):
        v = (env.get(name) or "").strip()
        if v:
            by_value.setdefault(v, []).append(name)
    return [(names, v) for v, names in by_value.items()]


def _request(url: str, key: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            payload = {}
        return e.code, payload
    except Exception as e:  # noqa: BLE001 - 네트워크 오류
        return 0, {"error": {"message": f"{type(e).__name__}: {e}", "status": "NETWORK"}}


def classify(status: int, payload: dict, tool: str) -> tuple[str, str]:
    """(요약 라벨, 상세) — 라벨: OK / EMPTY / 429 / 404 / 400 / 403 / ERR."""
    if status == 200:
        cand = (payload.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])).strip()
        meta = cand.get("groundingMetadata") or {}
        if tool == "SEARCH":
            chunks = len(meta.get("groundingChunks") or [])
            queries = len(meta.get("webSearchQueries") or [])
            if chunks:
                return "OK", f"sources={chunks} queries={queries}"
            return "NOSRC", f"200 이지만 검색 근거 없음(text={len(text)}자)"
        if tool == "URLCTX":
            um = cand.get("urlContextMetadata") or {}
            urls = um.get("urlMetadata") or []
            ok = [u for u in urls if "SUCCESS" in str(u.get("urlRetrievalStatus", ""))]
            if ok:
                return "OK", f"urls_read={len(ok)}"
            return "NOURL", f"200 이지만 URL 을 읽지 못함(meta={len(urls)}, text={len(text)}자)"
        return ("OK", f"text={len(text)}자") if text else ("EMPTY", "빈 응답")
    err = payload.get("error") or {}
    msg = re.sub(r"\s+", " ", str(err.get("message", ""))).strip()
    if status == 429:
        reason = "선불 크레딧 소진" if "prepayment" in msg.lower() else (
            "한도 0(해당 도구/모델 무료 불가)" if "limit: 0" in msg else "쿼터 소진")
        return "429", f"{reason} · {msg[:90]}"
    return (str(status) if status in (400, 403, 404, 503) else "ERR"), msg[:110] or err.get("status", "")


def probe(key: str, model: str, tool: str) -> tuple[str, str]:
    prompt = {"PLAIN": PLAIN_PROMPT, "SEARCH": SEARCH_PROMPT, "URLCTX": URL_PROMPT}[tool]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 512, "temperature": 0}}
    if tool == "SEARCH":
        body["tools"] = [{"google_search": {}}]
    elif tool == "URLCTX":
        body["tools"] = [{"url_context": {}}]
    status, payload = _request(f"{BASE}/models/{model}:generateContent", key, body)
    return classify(status, payload, tool)


def list_models(key: str) -> set[str]:
    names: set[str] = set()
    token = ""
    for _ in range(5):
        url = f"{BASE}/models?pageSize=200" + (f"&pageToken={token}" if token else "")
        status, payload = _request(url, key)
        if status != 200:
            break
        names |= {m.get("name", "").removeprefix("models/") for m in payload.get("models", [])}
        token = payload.get("nextPageToken", "")
        if not token:
            break
    return names


def main() -> int:
    keys = collect_keys()
    if not keys:
        print("점검할 GEMINI_API_KEY* 환경변수가 없습니다.", file=sys.stderr)
        return 1
    models = [m.strip() for m in os.environ.get("PROBE_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
    delay = float(os.environ.get("PROBE_DELAY", "3"))
    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    out("## Gemini 도구 사용 가능 여부 실측 (키 값은 표시하지 않음)")
    out("")
    for names, key in keys:
        fp = hashlib.sha256(key.encode()).hexdigest()[:6]
        kind = "AQ." if key.startswith("AQ.") else ("AIza" if key.startswith("AIza") else "기타")
        avail = list_models(key)
        out(f"### 🔑 {', '.join(f'`{n}`' for n in names)}  <sub>형식 `{kind}…` · 길이 {len(key)} · 지문 {fp} · 모델 {len(avail)}개 조회됨</sub>")
        out("")
        out("| 모델 | 목록에 있음 | PLAIN | SEARCH(그라운딩) | URLCTX | 비고 |")
        out("| --- | :-: | --- | --- | --- | --- |")
        for model in models:
            res = {}
            for tool in ("PLAIN", "SEARCH", "URLCTX"):
                res[tool] = probe(key, model, tool)
                time.sleep(delay)
            note = res["SEARCH"][1] if res["SEARCH"][0] != "OK" else res["SEARCH"][1]
            out(f"| `{model}` | {'✅' if model in avail else '—'} | {res['PLAIN'][0]} | {res['SEARCH'][0]} | {res['URLCTX'][0]} | "
                f"S: {res['SEARCH'][1][:70]} / U: {res['URLCTX'][1][:60]} |")
        out("")
    out("범례: OK=정상 · NOSRC/NOURL=200 이지만 도구가 실제로 동작하지 않음 · 429=쿼터/한도 · 404=모델 없음 · 400/403=요청 불가")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
