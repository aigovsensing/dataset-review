#!/usr/bin/env python3
"""오픈 데이터셋 법적 리스크 검토 에이전트 (GitHub Actions 실행용).

GitHub 이슈 폼으로 입력된 데이터셋 정보를 읽어, Google AI Studio(Gemini) API를
Google 검색 그라운딩과 함께 호출하여 법적 리스크 검토 보고서를 생성한다.
결과 Markdown은 --output 경로(기본: review.md)로 저장되며, 워크플로가 이를
이슈 댓글로 등록한다.

환경 변수
----------
GEMINI_API_KEY : (필수) Google AI Studio API 키
GEMINI_MODEL   : (선택) 사용할 모델. 기본값 gemini-2.5-flash
ISSUE_TITLE    : (선택) 이슈 제목
ISSUE_BODY     : (선택) 이슈 본문(이슈 폼 렌더링 결과)
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "system_prompt.md"

# 이슈 폼(dataset-review.yml)의 라벨 → 내부 필드 키 매핑
FIELD_LABELS = {
    "데이터셋 명칭": "dataset_name",
    "관련 / 원본 데이터셋": "related_datasets",
    "논문 주소 (URL)": "paper_urls",
    "공식 홈페이지 / 저장소 URL": "homepage_url",
    "관련 소송 (CourtListener URL)": "litigation_url",
    "추가 참고 사항": "extra_notes",
}

NO_RESPONSE_MARKERS = {"_No response_", "_없음_", "N/A", "없음", ""}


def parse_issue_body(body: str) -> dict[str, str]:
    """GitHub 이슈 폼이 렌더링한 본문(`### 라벨\n\n값`)을 필드 dict로 파싱."""
    fields: dict[str, str] = {}
    # "### " 헤딩 기준으로 분할
    chunks = re.split(r"^###\s+", body, flags=re.MULTILINE)
    for chunk in chunks:
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        heading = lines[0].strip()
        value = "\n".join(lines[1:]).strip()
        key = FIELD_LABELS.get(heading)
        if key is None:
            continue
        if value in NO_RESPONSE_MARKERS:
            value = ""
        fields[key] = value
    return fields


def derive_dataset_name(title: str, fields: dict[str, str]) -> str:
    """폼의 데이터셋 명칭을 우선 사용하고, 없으면 제목에서 접두어를 제거해 추정."""
    name = fields.get("dataset_name", "").strip()
    if not name and title:
        name = re.sub(r"^\s*\[검토\]\s*", "", title).strip()
    return name


def build_user_prompt(title: str, fields: dict[str, str]) -> str:
    name = derive_dataset_name(title, fields)

    lines = [
        "다음 오픈 데이터셋에 대해 시스템 지침에 따라 법적 리스크를 검토하라.",
        "제공된 Google 검색 도구로 공식 자료를 직접 확인한 뒤 판단하라.",
        "",
        f"- 데이터셋 명칭: {name or '(미입력 — 검색으로 확인)'}",
    ]
    if fields.get("related_datasets"):
        lines.append(f"- 관련 / 원본 데이터셋: {fields['related_datasets']}")
    if fields.get("paper_urls"):
        lines.append(f"- 논문 주소: {fields['paper_urls']}")
    if fields.get("homepage_url"):
        lines.append(f"- 공식 홈페이지 / 저장소: {fields['homepage_url']}")
    if fields.get("litigation_url"):
        lines.append(f"- 관련 소송 (CourtListener): {fields['litigation_url']}")
    if fields.get("extra_notes"):
        lines.append(f"- 추가 참고 사항: {fields['extra_notes']}")
    if fields.get("litigation_url"):
        lines.append(
            "\n위 소송 URL 이 제공되었으므로 시스템 지침의 [소송 리스크 검토]를 반드시 수행하고, "
            "출력의 '3. 소송 리스크' 섹션에 근거 강도(강/중/약)와 소장 원문 인용·요약을 포함한다."
        )
    lines += [
        "",
        "출력은 시스템 지침의 [출력 형식]을 정확히 따른다.",
    ]
    return "\n".join(lines)


def get_grounding_sources(response) -> list[tuple[str, str]]:
    """그라운딩 메타데이터에서 (제목, URL) 목록을 원본 순서 그대로 반환.

    반환 리스트의 인덱스 i 는 인용 번호 i+1 에 대응한다(중복 제거하지 않음).
    모델이 본문에 남기는 `cite: N` 의 N 이 이 순서를 따르므로 순서를 보존한다.
    """
    sources: list[tuple[str, str]] = []
    try:
        cand = (response.candidates or [None])[0]
        meta = getattr(cand, "grounding_metadata", None) if cand else None
        for chunk in (getattr(meta, "grounding_chunks", None) or []) if meta else []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                title = (getattr(web, "title", "") or web.uri).strip()
                sources.append((title, web.uri))
    except Exception:  # noqa: BLE001 - 그라운딩 메타데이터는 부가 정보이므로 실패해도 무시
        pass
    return sources


# 모델이 본문에 남기는 인용 표기(예: "cite: 2, 8", "cite:2") 를 잡아낸다.
_CITE_RE = re.compile(r"(cite\s*:\s*)([0-9][0-9,\s]*)", re.IGNORECASE)


def linkify_citations(text: str, sources: list[tuple[str, str]]) -> str:
    """본문의 `cite: N` 안 숫자를 실제 출처 URL 로 가는 마크다운 링크로 변환.

    - `cite:` 문맥 안의 숫자만 대상으로 하여 버전 번호(예: 'CC BY 4.0') 오인식을 방지한다.
    - N 이 출처 개수 범위를 벗어나면 링크로 만들지 않고 원문 숫자를 유지한다.
    - GitHub 이슈 댓글은 커스텀 앵커(id/name)를 제거하므로 외부 URL 로 직접 링크한다.
    """
    if not sources:
        return text

    def _num_to_link(num_match: re.Match) -> str:
        n = int(num_match.group(0))
        if 1 <= n <= len(sources):
            return f"[{n}]({sources[n - 1][1]})"
        return num_match.group(0)

    def _repl(m: re.Match) -> str:
        prefix, numbers = m.group(1), m.group(2)
        return prefix + re.sub(r"\d+", _num_to_link, numbers)

    return _CITE_RE.sub(_repl, text)


def render_sources(sources: list[tuple[str, str]]) -> str:
    """인용 번호와 일치하는 번호 매김 출처 목록을 마크다운으로 렌더링."""
    return "\n".join(
        f"{i + 1}. [{title}]({uri})" for i, (title, uri) in enumerate(sources)
    )


# GitHub 이슈/댓글 본문 최대 길이(65,536자)보다 안전 여유를 둔 상한
MAX_COMMENT_CHARS = 64000


def strip_preamble(text: str) -> str:
    """보고서 앞의 서두(사고 과정·영어 노트·'Now I will...')와 재작성 흔적을 제거.

    보고서는 '## 1. 요약 결론' 으로 시작해야 한다. 모델이 서두를 붙이거나 보고서를
    두 번 시작하는 경우, 마지막 '## 1.' 부터를 최종 보고서로 간주한다.
    """
    # 줄 시작 여부와 무관하게 '## 1.'(예: "...format.## 1.") 를 모두 찾아
    # 마지막(최종 재작성본)부터를 보고서로 사용한다.
    matches = list(re.finditer(r"##[ \t]+1\.", text))
    if matches:
        return text[matches[-1].start():].strip()
    return text


def sanitize_markdown(text: str) -> str:
    """모델 출력의 병리적 패턴을 정리한다.

    - 표 구분선 등에서 나타나는 과도한 대시 연속(수천~수십만 개)을 3개로 축소.
      (실제로 gemini 가 40만 자짜리 구분선을 생성해 댓글 길이 제한을 초과한 사례)
    - 4개 이상 연속된 공백 줄을 2개로 축소.
    """
    text = re.sub(r"-{4,}", "---", text)
    text = re.sub(r"={4,}", "===", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


def enforce_length_limit(text: str, limit: int = MAX_COMMENT_CHARS) -> str:
    """GitHub 댓글 길이 제한을 넘으면 안전하게 잘라내고 안내를 덧붙인다."""
    if len(text) <= limit:
        return text
    notice = (
        "\n\n---\n> ⚠️ 검토 내용이 GitHub 댓글 길이 제한(65,536자)을 초과하여 "
        "이후 내용이 생략되었습니다. 전체 내용은 검토 로그를 참고하세요."
    )
    return text[: limit - len(notice)].rstrip() + notice


# 판정 → (배지 이모지, 색상 라벨). 가장 보수적인 순서로 탐색한다.
_VERDICTS = [
    ("사용 비권고", "⛔"),
    ("추가 검토 필요", "⚠️"),
    ("사용 가능", "✅"),
]

_SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$", re.MULTILINE)
# 상세 분석 h2 헤더(번호 유무 무관)
_DETAIL_H2_RE = re.compile(r"^##\s+(?:\d+\.\s*)?.*상세\s*분석", re.MULTILINE)
# 상세 분석에 속하는 h3 서브섹션 시작 표지
_DETAIL_H3_RE = re.compile(r"^###\s+(?:라이선스|데이터\s*생성|개인정보)", re.MULTILINE)


def ensure_detail_section_header(text: str) -> str:
    """모델이 '## 2. 항목별 상세 분석' 헤더를 생략한 경우 자동으로 삽입.

    일부 실행에서 모델이 상세 분석 h2 헤더 없이 곧바로 h3 서브섹션을 출력해
    상세 분석이 요약 섹션에 흡수되는 것을 방지한다.
    """
    if _DETAIL_H2_RE.search(text):
        return text
    m = _DETAIL_H3_RE.search(text)
    if not m:
        return text
    idx = m.start()
    return text[:idx] + "## 2. 항목별 상세 분석\n\n" + text[idx:]


def detect_verdict(text: str) -> tuple[str | None, str]:
    """'내부 검토 결과' 판정을 추출. 못 찾으면 (None, 📋)."""
    m = re.search(r"내부\s*검토\s*결과[^\n]*\n+\s*([^\n]+)", text)
    region = m.group(1) if m else text[:500]
    for label, emoji in _VERDICTS:
        if label in region:
            return label, emoji
    for label, emoji in _VERDICTS:  # 폴백: 본문 전체에서 탐색
        if label in text:
            return label, emoji
    return None, "📋"


def restructure_review(text: str, name: str) -> str:
    """모델 출력을 스캔하기 쉬운 형태로 재구성.

    - 상단에 데이터셋명 + 판정 배지 배너를 붙인다.
    - 1. 요약 결론은 펼친 상태로 노출.
    - 2. 항목별 상세 분석 / 3. 근거 및 출처는 접이식(<details>)으로 감싸 어수선함을 줄인다.
    - 예상 형식(## N. 제목)이 아니면 원문을 그대로 두어 안전하게 처리한다.
    """
    text = ensure_detail_section_header(text)
    verdict, emoji = detect_verdict(text)
    verdict_line = f"{emoji} **{verdict}**" if verdict else "📋 (판정 확인 불가)"
    banner = (
        "# 🛡️ 오픈 데이터셋 법적 리스크 검토 결과\n\n"
        f"> **대상 데이터셋** &nbsp;`{name or '확인 불가'}`\n"
        f"> **내부 검토 결과** &nbsp;{verdict_line}\n"
    )

    matches = list(_SECTION_RE.finditer(text))
    if len(matches) < 2:
        return banner + "\n---\n\n" + text  # 형식이 다르면 배너만 추가

    icons = {"1": "🧭", "2": "🔍", "3": "⚖️", "4": "📚"}
    blocks: list[str] = []
    for i, m in enumerate(matches):
        num, sec_title = m.group(1), m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip().strip("-").strip()
        icon = icons.get(num, "📄")
        if num == "1":
            blocks.append(f"## {icon} 요약 결론\n\n{body}")
        else:
            open_attr = " open" if num == "2" else ""
            blocks.append(
                f"<details{open_attr}>\n<summary><b>{icon} {num}. {sec_title}</b></summary>\n\n"
                f"{body}\n\n</details>"
            )
    return banner + "\n---\n\n" + "\n\n".join(blocks)


# 일시적으로 재시도할 가치가 있는 오류(서버 과부하/속도 제한 등)
_RETRIABLE_MARKERS = ("503", "500", "502", "504", "UNAVAILABLE", "high demand", "RESOURCE_EXHAUSTED", "429")


def generate_with_retry(client, model, contents, config, attempts: int = 4, base_delay: float = 5.0):
    """Gemini 호출을 일시적 오류(예: 503 high demand, 429)에 대해 지수 백오프로 재시도."""
    delay = base_delay
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # noqa: BLE001 - 재시도 판단 후 마지막에 재발생
            last_exc = exc
            code = getattr(exc, "code", None)
            msg = str(exc)
            retriable = code in (429, 500, 502, 503, 504) or any(m in msg for m in _RETRIABLE_MARKERS)
            if not retriable or i == attempts - 1:
                raise
            print(f"일시적 오류로 재시도 ({i + 1}/{attempts - 1}), {delay:.0f}s 대기: {msg[:120]}", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 40.0)
    assert last_exc is not None  # 도달하지 않음
    raise last_exc


def run_review(title: str, body: str) -> str:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다. "
            "저장소 Settings → Secrets → Actions 에 GEMINI_API_KEY 를 등록하세요."
        )

    # 빈 문자열(예: 미설정 GitHub 변수 vars.GEMINI_MODEL)도 기본값으로 대체되도록 `or` 사용
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    fields = parse_issue_body(body)
    name = derive_dataset_name(title, fields)
    user_prompt = build_user_prompt(title, fields)

    client = genai.Client(api_key=api_key)
    base_config = dict(
        system_instruction=system_prompt,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.2,
        max_output_tokens=32768,
    )
    # gemini-2.5 계열의 동적 thinking 이 출력 토큰 예산을 모두 소진해 답변이 중간에
    # 잘리는 문제를 방지하기 위해 thinking 예산을 제한한다(미지원 SDK/모델이면 무시).
    try:
        config = types.GenerateContentConfig(
            **base_config,
            thinking_config=types.ThinkingConfig(thinking_budget=8192),
        )
    except Exception:  # noqa: BLE001 - 구버전 SDK 호환
        config = types.GenerateContentConfig(**base_config)

    response = generate_with_retry(client, model, user_prompt, config)

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError(
            "Gemini 응답이 비어 있습니다. 모델이 답변 없이 종료했거나 thinking 예산을 "
            "모두 소진했을 수 있습니다. 잠시 후 재시도하세요."
        )

    # 출력이 토큰 한도로 중간에 잘렸는지 확인 + 진단 로깅
    finish_reason = ""
    try:
        finish_reason = str(response.candidates[0].finish_reason or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        um = response.usage_metadata
        print(
            f"[diag] finish_reason={finish_reason} "
            f"prompt={getattr(um, 'prompt_token_count', '?')} "
            f"thoughts={getattr(um, 'thoughts_token_count', '?')} "
            f"output={getattr(um, 'candidates_token_count', '?')} "
            f"total={getattr(um, 'total_token_count', '?')} "
            f"text_chars={len(text)}",
            file=sys.stderr,
        )
    except Exception:  # noqa: BLE001
        pass
    truncated = "MAX_TOKENS" in finish_reason

    text = strip_preamble(text)
    text = sanitize_markdown(text)
    sources = get_grounding_sources(response)
    text = linkify_citations(text, sources)
    text = restructure_review(text, name)
    parts = [text]
    if sources:
        # 그라운딩 출처 목록은 길고 리다이렉트 URL 이라 어수선하므로 접이식으로 감싼다.
        parts.append(
            f"\n<details>\n<summary><b>🔎 참고 출처 (Google 검색 그라운딩) — {len(sources)}건</b></summary>\n\n"
            "본문의 `cite: N` 번호는 아래 동일 번호 출처로 연결됩니다.\n\n"
            + render_sources(sources)
            + "\n\n</details>"
        )
    if truncated:
        parts.append(
            "\n> ⚠️ 모델 출력이 토큰 한도로 중간에 잘렸을 수 있습니다. "
            "`rerun-review` 라벨로 재검토하거나 입력 범위를 좁혀 다시 시도하세요."
        )
    parts.append(
        "\n---\n"
        f"<sub>🤖 자동 생성 (model: <code>{model}</code>, Google Search grounding) · "
        "본 검토는 회사 내부 사전 리스크 검토용 참고 자료이며 법률 자문을 대체하지 않습니다.</sub>"
    )
    return enforce_length_limit("\n".join(parts))


def main() -> int:
    output_path = Path(os.environ.get("REVIEW_OUTPUT", "review.md"))
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")

    try:
        result = run_review(title, body)
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 이슈 댓글로 남기기 위해 포착
        result = (
            "## ⚠️ 자동 법적 리스크 검토 실패\n\n"
            "검토 에이전트 실행 중 오류가 발생했습니다.\n\n"
            f"```\n{type(exc).__name__}: {exc}\n```\n\n"
            "관리자에게 문의하거나, 저장소 설정(GEMINI_API_KEY Secret, API 쿼터)을 확인 후 "
            "`rerun-review` 라벨을 추가해 재시도하세요."
        )
        output_path.write_text(result, encoding="utf-8")
        print(result, file=sys.stderr)
        return 1

    output_path.write_text(result, encoding="utf-8")
    print(f"검토 결과를 {output_path} 에 저장했습니다 ({len(result)} chars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
