#!/usr/bin/env python3
"""연구논문 법무 사전 검토(Legal Review) 에이전트 (GitHub Actions 실행용).

GitHub 이슈 폼으로 입력된 논문 정보(PDF URL 또는 논문 등재 웹페이지 URL)를 읽어,
Gemini API로 논문 원문을 판독하고 Legal Review 보고서를 생성한다.
- PDF URL(또는 arXiv abs) → 원문 PDF를 내려받아 Gemini에 직접 첨부(inline)해 판독.
- 그 외 웹페이지 → url_context 도구로 페이지를 읽고(미지원 시 Google 검색) 검토.

데이터셋 검토(dataset_review.py)와 동일한 실행 구조를 따르며, 공용 헬퍼(재시도·모델
폴백·빈 응답 복구·그라운딩 인용·실패 분류 등)를 dataset_review.py에서 재사용한다.

환경 변수
----------
GEMINI_API_KEY : (필수) Google AI Studio API 키
GEMINI_DEFAULT_MODEL : (선택) 사용할 모델. 기본값 gemini-flash-latest
ISSUE_TITLE    : (선택) 이슈 제목
ISSUE_BODY     : (선택) 이슈 본문(이슈 폼 렌더링 결과)
REVIEW_OUTPUT  : (선택) 결과 저장 경로. 기본 review.md
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

import dataset_review as R  # 공용 헬퍼 재사용 (scripts/ 가 sys.path[0] 이므로 import 가능)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# 시스템 프롬프트(검토 지침)는 prompt-book/ 폴더에서 일관되게 관리한다.
PAPER_PROMPT_PATH = REPO_ROOT / "prompt-book" / "system_prompt_paper_review.md"

# 이슈 폼(paper-review.yml) 필드 라벨 → 내부 키
PAPER_FIELD_LABELS = {
    "논문 제목": "paper_title",
    "논문 PDF / 웹사이트 URL": "paper_url",
    "추가 참고 사항": "extra_notes",
}
NO_RESPONSE_MARKERS = {"_No response_", "_없음_", "N/A", "없음", ""}

# 내려받는 PDF 크기 상한. 이 값 이하이면 요청에 inline 으로 첨부하고, 초과하면 Files API 로 업로드.
INLINE_PDF_CAP = 18 * 1024 * 1024
MAX_PDF_BYTES = 45 * 1024 * 1024


def parse_paper_body(body: str) -> dict[str, str]:
    """GitHub 이슈 폼이 렌더링한 본문(`### 라벨\\n\\n값`)을 논문 필드 dict로 파싱."""
    fields: dict[str, str] = {}
    for chunk in re.split(r"^###\s+", body or "", flags=re.MULTILINE):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        key = PAPER_FIELD_LABELS.get(lines[0].strip())
        if not key:
            continue
        value = "\n".join(lines[1:]).strip()
        fields[key] = "" if value in NO_RESPONSE_MARKERS else value
    return fields


def derive_paper_title(title: str, fields: dict[str, str]) -> str:
    name = (fields.get("paper_title") or "").strip()
    if not name and title:
        name = re.sub(r"^\s*\[논문검토\]\s*", "", title).strip()
    return name


def first_url(text: str) -> str:
    """입력 문자열에서 첫 번째 http(s) URL 을 추출(여러 줄/공백 대응)."""
    m = re.search(r"https?://\S+", text or "")
    return m.group(0).rstrip(").,]") if m else (text or "").strip()


# GitHub 이슈에 드래그&드롭으로 첨부한 파일 링크(공개 저장소는 인증 없이 접근 가능).
_GH_ATTACH_RES = [
    re.compile(r"https://github\.com/user-attachments/assets/[0-9a-f-]+", re.I),
    re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/files/\d+/\S+?\.pdf", re.I),
    re.compile(r"https://[\w.-]*githubusercontent\.com/\S+?\.pdf", re.I),
]


def attachment_urls(body: str) -> list[str]:
    """이슈 본문에서 GitHub 첨부 파일(PDF 등) URL 후보를 순서대로 추출(중복 제거)."""
    found: list[str] = []
    for rx in _GH_ATTACH_RES:
        for u in rx.findall(body or ""):
            u = u.rstrip(").,]")
            if u not in found:
                found.append(u)
    return found


def normalize_pdf_url(url: str) -> str:
    """arXiv abs 링크는 PDF 링크로 변환한다(그 외는 그대로)."""
    m = re.match(r"https?://arxiv\.org/abs/([\w.\-/]+)", url, re.I)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}"
    return url


# 봇 접근을 차단(403/로그인 게이트)하는 것으로 알려진 호스트 — PDF 첨부를 권장.
BLOCKED_HOSTS = ("researchgate.net", "academia.edu", "sciencedirect.com", "ieeexplore.ieee.org")


def is_blocked_host(url: str) -> bool:
    return any(h in (url or "").lower() for h in BLOCKED_HOSTS)


def fetch_bytes(url: str) -> tuple[bytes, str]:
    """URL 을 내려받아 (본문 바이트, content-type) 을 반환. 실패 시 예외.

    일부 오픈액세스 서버는 기본 봇 UA 를 차단하므로 브라우저 유사 UA 를 사용한다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 dataset-review-bot"
        ),
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310 - 신뢰된 사용자 입력 URL
        ctype = (resp.headers.get("Content-Type") or "").lower()
        data = resp.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise RuntimeError(
            f"논문 파일이 너무 큽니다(>{MAX_PDF_BYTES // (1024 * 1024)}MB). "
            "더 작은 PDF 또는 논문 웹페이지 URL 로 다시 요청하세요."
        )
    return data, ctype


def looks_like_pdf(data: bytes, ctype: str) -> bool:
    return "application/pdf" in ctype or data[:5] == b"%PDF-"


def build_paper_prompt(name: str, fields: dict[str, str], mode: str, url: str) -> str:
    lines = [
        "첨부(또는 아래 URL)의 연구논문을 시스템 지침에 따라 법무 사전 검토(Legal Review)하라.",
        "반드시 논문 내용에 근거해서만 판단하고, 확인되지 않는 항목은 '확인 불가'로 표기한다(추측 금지).",
        "",
        f"- 논문 제목: {name or '(미입력 — 원문에서 확인)'}",
    ]
    if mode == "url":
        lines.append(f"- 논문 URL(원문 판독 대상): {url}")
    else:
        lines.append("- 논문 원문 PDF 가 이 요청에 첨부되어 있다. 첨부 PDF 를 직접 판독하라.")
    if fields.get("extra_notes"):
        lines.append(f"- 추가 참고 사항: {fields['extra_notes']}")
    lines += [
        "",
        "[자의적 해석 금지 — 신뢰성 필수] 근거 없는 해석·추리를 사실처럼 쓰지 말 것. 큰따옴표 원문 인용은 "
        "논문에 그 문장이 실제로 있을 때만 사용하고, 없으면 지어내지 말고 '확인 불가'로 둔다. 사용자 입력"
        "(prompt)은 근거가 아니다. **사실을 주장하는 모든 문장(Reason·Result 포함) 끝에 근거가 된 논문 "
        "위치(p.N/섹션)나 실제 출처 URL 을 함께 표기**한다(뒷받침 근거 없으면 '확인 불가').",
        "",
        "출력은 시스템 지침의 [출력 형식]을 정확히 따른다(종합의견 · 논문 개요 · 1~3 항목 · 결론).",
        "'논문 개요'에는 (1) Abstract에 근거한 논문 초록의 충실한 한국어 요약과 (2) 논문 실험에서 "
        "각 외부·자체 생성 데이터셋을 사용한 목적을 반드시 출력하라. 데이터셋별로 학습·미세조정·검증·"
        "평가·벤치마크·비교 실험 등 실제 역할과 사용 단계를 구분하고 근거 위치와 원문 인용을 붙인다. "
        "Abstract나 사용 목적을 원문에서 확인할 수 없으면 추정하지 말고 '확인 불가'로 표기한다.",
        "특히 이 논문이 외부 Dataset(AI Dataset)을 사용한 연구인지, 연구자가 자체 생성한 실험 "
        "데이터를 사용한 연구인지 구분해 판단하고, 마지막에 'Dataset을 이용한 실험 논문인지'를 "
        "예/아니오로 명확히 결론짓는다. 각 판정에 논문 내 근거 위치(페이지/섹션)와 원문 인용을 붙인다.",
    ]
    return "\n".join(lines)


def _make_config(types, base: dict, tools, budget: int):
    kw = dict(base)
    if tools:
        kw["tools"] = tools
    try:
        return types.GenerateContentConfig(
            **kw, thinking_config=types.ThinkingConfig(thinking_budget=budget)
        )
    except Exception:  # noqa: BLE001 - 구버전 SDK/미지원 모델 호환
        return types.GenerateContentConfig(**kw)


def _generate(client, model: str, contents, config, config_min):
    """모델 폴백 + 빈 응답(STOP) 복구 루프. (dataset_review.py 의 로직과 동일한 정책)"""
    chain = R.build_model_chain(model)
    print(f"[diag] paper model_chain={chain}", file=sys.stderr)
    response = None
    text = ""
    finish_reason = ""
    used_model = model
    gen_error: Exception | None = None

    for ci, cand in enumerate(chain):
        used_model = cand
        try:
            for attempt in range(2):
                cfg = config if attempt == 0 else config_min
                response = R.generate_with_retry(client, cand, contents, cfg)
                text = (response.text or "").strip()
                finish_reason = ""
                try:
                    finish_reason = str(response.candidates[0].finish_reason or "")
                except Exception:  # noqa: BLE001
                    pass
                print(
                    f"[diag] paper model={cand} attempt={attempt + 1} "
                    f"finish_reason={finish_reason} text_chars={len(text)}",
                    file=sys.stderr,
                )
                if text and "MAX_TOKENS" not in finish_reason:
                    break
                if attempt == 0:
                    why = "빈 응답(STOP)" if not text else "출력 잘림(MAX_TOKENS)"
                    print(f"{cand}: {why} → thinking 최소화로 1회 재생성합니다.", file=sys.stderr)
            if text:
                gen_error = None
                break
            if ci < len(chain) - 1:
                print(
                    f"모델 `{cand}` 가 답변 없이 종료(빈 응답) → 다음 모델로 폴백합니다.",
                    file=sys.stderr,
                )
                gen_error = None
                continue
            gen_error = None
        except Exception as exc:  # noqa: BLE001 - 폴백 판단
            gen_error = exc
            if R.is_fallbackable(exc) and ci < len(chain) - 1:
                print(
                    f"모델 `{cand}` 호출 실패({type(exc).__name__}) → 다음 모델로 폴백합니다.",
                    file=sys.stderr,
                )
                continue
            raise

    if gen_error is not None:
        raise gen_error
    if not text:
        raise RuntimeError(
            f"Gemini 응답이 비어 있습니다 (finish_reason={finish_reason or '알 수 없음'}). "
            "폴백 체인의 모든 모델이 답변 없이 종료했습니다. 잠시 후 'rerun-review' 라벨로 재시도하세요."
        )
    return response, text, used_model, finish_reason


def run_paper_review(title: str, body: str, api_key: str) -> str:
    from google import genai
    from google.genai import types

    model = os.environ.get("GEMINI_DEFAULT_MODEL") or "gemini-flash-latest"
    system_prompt = PAPER_PROMPT_PATH.read_text(encoding="utf-8")
    fields = parse_paper_body(body)
    name = derive_paper_title(title, fields)
    raw_url = fields.get("paper_url") or ""
    url = normalize_pdf_url(first_url(raw_url))
    # 이슈 본문에 드래그&드롭으로 첨부한 PDF 링크(있으면 우선 다운로드 후보에 포함)
    attachments = attachment_urls(body)

    if not url and not attachments:
        raise RuntimeError(
            "검토할 논문 URL 이 없습니다 (논문 PDF 링크·웹페이지 URL·첨부 PDF 모두 없음). "
            "Gemini API 를 호출하지 않고 종료했습니다. 이슈 폼을 채우거나 PDF 를 첨부한 뒤 "
            "'rerun-review' 로 재시도하세요."
        )

    client = genai.Client(api_key=api_key)
    base_config = dict(
        system_instruction=system_prompt,
        temperature=0.2,
        max_output_tokens=32768,
    )

    # ── 논문 원문 확보 ──────────────────────────────────────────────
    # PDF 우선: 입력 URL + 이슈 첨부 파일을 차례로 내려받아 첫 번째 PDF 를 직접 판독한다.
    # (ResearchGate 등 봇 차단 페이지는 첨부 PDF 로 우회할 수 있다.)
    # PDF 를 못 구하면 웹페이지 URL 을 url_context 로 판독한다.
    mode = "url"
    source_note = ""
    contents: list = []
    tools = None

    candidates: list[str] = []
    for c in ([url] if url else []) + attachments:
        if c and c not in candidates:
            candidates.append(c)

    pdf_data = None
    pdf_from = ""
    for cand in candidates:
        try:
            data, ctype = fetch_bytes(cand)
            if looks_like_pdf(data, ctype):
                pdf_data = data
                pdf_from = cand
                break
            print(f"[diag] 후보 non-PDF(ctype={ctype[:40]}): {cand[:80]}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - 다음 후보로 진행
            print(f"다운로드 실패({type(exc).__name__}: {str(exc)[:80]}): {cand[:80]}", file=sys.stderr)

    if pdf_data is not None:
        mode = "pdf"
        is_attach = pdf_from in attachments
        prompt_text = build_paper_prompt(name, fields, mode, pdf_from)
        via = "이슈 첨부" if is_attach else "URL"
        if len(pdf_data) <= INLINE_PDF_CAP:
            pdf_part = types.Part.from_bytes(data=pdf_data, mime_type="application/pdf")
            contents = [pdf_part, prompt_text]
            source_note = f"PDF 원문 직접 판독(inline, {via})"
        else:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_data)
                tmp_path = tf.name
            uploaded = client.files.upload(file=tmp_path)
            contents = [uploaded, prompt_text]
            source_note = f"PDF 원문 직접 판독(Files API, {via})"
        print(f"[diag] paper mode=pdf bytes={len(pdf_data)} via={via}", file=sys.stderr)
    else:
        # PDF 확보 실패 → 웹페이지 URL 판독. 봇 차단 호스트면 안내를 위해 근거를 남긴다.
        if not url:
            raise RuntimeError(
                "첨부/링크에서 PDF 를 확인하지 못했습니다. 논문 PDF 직접 링크를 넣거나, "
                "이슈 작성 화면에서 논문 PDF 파일을 드래그&드롭으로 첨부한 뒤 'rerun-review' 로 재시도하세요."
            )
        if is_blocked_host(url):
            print(f"[diag] 봇 차단 가능 호스트: {url}", file=sys.stderr)
        prompt_text = build_paper_prompt(name, fields, mode, url)
        contents = [prompt_text]
        try:
            tools = [types.Tool(url_context=types.UrlContext())]
            source_note = "웹페이지 원문 판독(url_context)"
        except Exception:  # noqa: BLE001 - url_context 미지원 SDK → 검색 그라운딩
            tools = [types.Tool(google_search=types.GoogleSearch())]
            source_note = "웹 검색 그라운딩(url_context 미지원)"
        if is_blocked_host(url):
            source_note += " ⚠️ 로그인/봇 차단 사이트일 수 있어 PDF 첨부를 권장"
        print(f"[diag] paper mode=url source_note={source_note}", file=sys.stderr)

    config = _make_config(types, base_config, tools, 8192)
    config_min = _make_config(types, base_config, tools, 512)

    response, text, used_model, finish_reason = _generate(client, model, contents, config, config_min)

    truncated = "MAX_TOKENS" in finish_reason
    resolved_model = ""
    try:
        resolved_model = (response.model_version or "").strip()
    except Exception:  # noqa: BLE001
        pass
    resolved_model = resolved_model or used_model

    # 서비스 티어(표시용 라벨): 환경변수 우선 → 없으면 응답 메타데이터 자동 판별 → 기본값 "Free".
    service_tier = (os.environ.get("GEMINI_SERVICE_TIER") or "").strip()
    if not service_tier:
        try:
            tv = getattr(response.usage_metadata, "service_tier", None)
            if tv and str(tv).lower() != "none":
                service_tier = str(tv).capitalize()
        except Exception:  # noqa: BLE001
            pass
    service_tier = service_tier or "Free"

    # 상단 정보 박스 — 한눈에 읽히도록 아이콘+라벨로 한 줄씩 분리(블록쿼트, 줄끝 두 칸=줄바꿈).
    hdr = [f"🤖 **검토 모델** &nbsp;`{resolved_model}`"]
    if used_model != model:
        hdr.append(f"<sub>⚠️ 요청 `{model}` → 폴백(쿼터 소진/불가), 실제 사용 `{used_model}`</sub>")
    elif resolved_model != model:
        hdr.append(f"<sub>요청 `{model}` → 실제 버전 `{resolved_model}`</sub>")
    hdr.append(f"🏷️ **서비스 티어** &nbsp;`{service_tier}`")
    hdr.append(f"📄 **원문 판독 방식** &nbsp;{source_note}")
    hdr.append(f"🔗 **대상** &nbsp;{url}")
    header = "\n".join(f"> {ln}  " for ln in hdr) + "\n"

    text = R.insert_grounding_citations(response.text or text, response)
    text = R.strip_preamble(text)
    text = R.sanitize_markdown(text)
    sources = R.get_grounding_sources(response)
    text = R.linkify_citations(text, sources)
    text = R.link_source_refs(text, sources)  # 본문 `[출처 N]` 을 실제 출처 URL 링크로 변환

    parts = [header, text]
    if sources:
        parts.append(
            f"\n<details>\n<summary><b>🔎 참고 출처 — {len(sources)}건</b></summary>\n\n"
            "본문 문장 끝의 `[N]` 링크는 아래 동일 번호 출처로 연결됩니다.\n\n"
            + R.render_sources(sources)
            + "\n\n</details>"
        )
    if truncated:
        parts.append(
            "\n> ⚠️ 모델 출력이 토큰 한도로 중간에 잘렸을 수 있습니다. "
            "`rerun-review` 라벨로 재검토하세요."
        )
    parts.append(
        "\n---\n"
        f"<sub>🤖 자동 생성 (model: <code>{resolved_model}</code>) · "
        "본 논문 법무 검토는 회사 내부 사전 리스크 검토용 참고 자료이며 법률 자문을 대체하지 않습니다.</sub>"
    )
    return R.enforce_length_limit("\n".join(parts))


def main() -> int:
    output_path = Path(os.environ.get("REVIEW_OUTPUT", "review.md"))
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")

    env_keys = sorted(
        [k for k in os.environ.keys() if k.startswith("GEMINI_API_KEY")],
        key=lambda x: (0 if x == "GEMINI_API_KEY" else 1, x)
    )
    api_keys = []
    for k in env_keys:
        val = os.environ[k].strip()
        if val and val not in api_keys:
            api_keys.append(val)

    if not api_keys:
        result = (
            "## ⚠️ 자동 논문 법무 검토 실패\n\n"
            "GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다. "
            "저장소 Settings → Secrets → Actions 에 키를 등록하고 워크플로 env 에 매핑하세요."
        )
        output_path.write_text(result, encoding="utf-8")
        print(result, file=sys.stderr)
        return 1

    last_exc = None
    used_key = ""
    result = ""

    for i, key in enumerate(api_keys):
        try:
            result = run_paper_review(title, body, key)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            used_key = key
            masked = f"{key[:6]}****{key[-4:]}" if len(key) > 10 else "(미설정)"
            print(f"[diag] API Key ({masked}) 시도 실패 ({type(exc).__name__}): {exc}", file=sys.stderr)
            if i < len(api_keys) - 1:
                print(f"-> 다른 API 키로 폴백하여 전체 모델 체인을 재시도합니다... ({i+1}/{len(api_keys)})", file=sys.stderr)
                continue

    if not result and last_exc:
        result = (
            "## ⚠️ 자동 논문 법무 검토 실패\n\n"
            "검토 에이전트 실행 중 오류가 발생했습니다.\n\n"
            f"```\n{type(last_exc).__name__}: {last_exc}\n```\n\n"
            + R.classify_failure(last_exc, used_key)
        )
        output_path.write_text(result, encoding="utf-8")
        print(result, file=sys.stderr)
        return 1

    output_path.write_text(result, encoding="utf-8")
    print(f"논문 검토 결과를 {output_path} 에 저장했습니다 ({len(result)} chars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
