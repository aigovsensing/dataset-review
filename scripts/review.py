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
        "제공된 Google 검색 도구로 공식 자료(공식 홈페이지·LICENSE·Terms·논문·GitHub·Hugging Face)를 "
        "직접 확인한 뒤 판단하라. 아래 제공된 URL 을 우선 근거로 활용하고, 인용 시 출처 URL 을 "
        "함께 제시한다.",
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
    # 보고서는 '## 종합의견' 으로 시작한다(없으면 '## 1.'). 줄 시작 여부와 무관하게
    # (예: "...format.## 종합의견") 모두 찾아 마지막(최종 재작성본)부터를 보고서로 사용한다.
    for pat in (r"##[ \t]+종합의견", r"##[ \t]+1\."):
        matches = list(re.finditer(pat, text))
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


# 종합의견의 번호 항목(예: "1. 라이선스: ...")을 파싱
_SUMMARY_ITEM_RE = re.compile(r"^\s*\d+\.\s*([^:：\n]+?)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
# 항목 라벨 → 아이콘
_SUMMARY_ICONS = (("라이선스", "⚖️"), ("수집", "🛠️"), ("생성", "🛠️"), ("원본", "🛠️"), ("개인정보", "🔐"))


def _item_key(label: str) -> str | None:
    """검토 항목 라벨을 표준 키로 매핑. 알려진 3개 항목이 아니면 None.

    (판정 문구 '사용 가능/추가 검토 필요/사용 비권고' 등이 항목 행으로 잘못 섞이는 것을 방지)
    """
    if "라이선스" in label:
        return "license"
    if "수집" in label or "생성" in label or "원본" in label:
        return "collection"
    if "개인정보" in label:
        return "privacy"
    return None


def _md_cell(s: str) -> str:
    """표 셀 안전화: 파이프 이스케이프 + 개행 제거."""
    return " ".join(s.split()).replace("|", "\\|")


# 종합의견 항목의 '값 — 근거: 근거' 를 값과 근거로 분리
_SUMMARY_BASIS_RE = re.compile(r"\s+[—–-]\s*근거\s*[:：]\s*(.+)$")


def _split_value_basis(rest: str) -> tuple[str, str]:
    """'값 — 근거: 근거' → (값, 근거). 마커가 없으면 (전체, '')."""
    m = _SUMMARY_BASIS_RE.search(rest)
    if m:
        return rest[: m.start()].strip(), m.group(1).strip()
    return rest.strip(), ""


# '## 1. 요약 결론' 의 항목 불릿: "- **라이선스** — 확인 결과: … / 내부 판단: … / 판단 근거: …"
# 들여쓰기 허용, 구분자는 em/en 대시만(하이픈 제외 — 별도 볼드 줄 다음 불릿의 '-' 를
# 구분자로 삼아 항목을 삼키는 것을 방지), 대시 주변은 [ \t] 로 제한(줄바꿈 미포함).
_YOYAK_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+\*\*(.+?)\*\*[ \t]*[—–][ \t]*(.+)$", re.MULTILINE)


def _summary_table(verdict_line: str, items: list[tuple[str, str, str, str]]) -> str:
    """(라벨, 확인 결과, 내부 판단, 판단 근거) 목록으로 종합의견 4열 표를 렌더."""
    rows = [f"| 🏁 **내부 검토 결과** | — | {verdict_line} | — |"]
    for label, checked, judgment, basis in items:
        icon = next((ic for key, ic in _SUMMARY_ICONS if key in label), "•")
        rows.append(
            f"| {icon} **{_md_cell(label)}** | {_md_cell(checked) or '—'} "
            f"| {_md_cell(judgment) or '—'} | {_md_cell(basis) or '—'} |"
        )
    return (
        "## 📌 종합의견\n\n"
        "| 검토 항목 | 확인 결과 | 내부 판단 | 판단 근거 |\n"
        "| :-- | :-- | :-- | :-- |\n" + "\n".join(rows)
    )


def _field(rest: str, key: str, stop: str | None) -> str:
    """'키: 값 / 다음키: ...' 형태에서 키의 값을 추출. stop 이 None 이면 끝까지."""
    if stop:
        m = re.search(rf"{key}\s*[:：]\s*(.+?)(?:\s*[/—–]\s*(?:{stop})\s*[:：]|$)", rest)
    else:
        m = re.search(rf"{key}\s*[:：]\s*(.+)$", rest)
    return m.group(1).strip() if m else ""


def summary_from_yoyak(section1_body: str, verdict_line: str) -> str:
    """'1. 요약 결론' 의 항목 불릿에서 종합의견 4열 표를 만든다.

    요약 결론 각 항목은 '확인 결과 / 내부 판단 / 판단 근거' 를 모두 담으므로,
    이 세 값을 그대로 표의 3개 열로 사용한다.
    """
    items: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for m in _YOYAK_BULLET_RE.finditer(section1_body):
        label, rest = m.group(1).strip(), m.group(2).strip()
        key = _item_key(label)  # 알려진 검토 항목만 행으로 인정(판정/잡음 불릿 배제)
        if not key or key in seen:
            continue
        seen.add(key)
        checked = _field(rest, r"확인\s*결과", r"내부\s*판단|판단\s*근거")
        judgment = _field(rest, r"내부\s*판단", r"판단\s*근거")
        basis = _field(rest, r"판단\s*근거", None)
        if not (checked or judgment or basis):
            checked = rest  # 필드 구분이 없으면 전체를 확인 결과로
        items.append((label, checked, judgment, basis))
    if len(items) < 2:
        return ""
    return _summary_table(verdict_line, items)


def summary_from_opinion(lead: str, verdict_line: str) -> str:
    """(폴백) '## 종합의견' 항목(값 — 근거)에서 표를 만든다. 내부 판단 열은 값에 통합/생략."""
    if "종합의견" not in lead:
        return ""
    matches = list(_SUMMARY_ITEM_RE.finditer(lead))
    if len(matches) < 2:
        return ""
    items = []
    seen: set[str] = set()
    for m in matches:
        label = m.group(1).strip()
        key = _item_key(label)  # 알려진 검토 항목만 인정
        if not key or key in seen:
            continue
        seen.add(key)
        value, basis = _split_value_basis(m.group(2).strip())
        items.append((label, value, "—", basis))  # 확인 결과=값, 내부 판단 없음
    if len(items) < 2:
        return ""
    return _summary_table(verdict_line, items)


def opinion_conclusion(lead: str) -> str:
    """'## 종합의견' 의 마지막 결론 문단(번호 항목 뒤 텍스트)을 한 줄로 추출."""
    if "종합의견" not in lead:
        return ""
    matches = list(_SUMMARY_ITEM_RE.finditer(lead))
    if not matches:
        return ""
    return " ".join(lead[matches[-1].end():].split()).strip()


def restructure_review(text: str, name: str) -> str:
    """모델 출력을 스캔하기 쉬운 형태로 재구성.

    - 상단에 데이터셋명 + 판정 배지 배너를 붙인다.
    - 배너 바로 아래에 '종합의견'(복사·붙여넣기용 회신문)을 펼친 상태로 노출.
    - 1. 요약 결론은 펼친 상태로 노출.
    - 2~4 상세/소송/근거 섹션은 접이식(<details>)으로 감싸 어수선함을 줄인다.
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

    # 종합의견 표(검토 항목/확인 결과/내부 판단/판단 근거)를 만든다.
    #  - 표 데이터는 '1. 요약 결론' 항목(확인 결과·내부 판단·판단 근거를 모두 담음)에서 우선 생성.
    #  - 요약 결론 파싱 실패 시 '## 종합의견' 항목에서 폴백(내부 판단 없음).
    #  - 결론 문단은 '## 종합의견' 에서 가져와 콜아웃으로 덧붙인다.
    lead_raw = text[: matches[0].start()].strip()
    sec1_end = matches[1].start() if len(matches) > 1 else len(text)
    table = summary_from_yoyak(text[matches[0].end():sec1_end], verdict_line) or \
        summary_from_opinion(lead_raw, verdict_line)
    if table:
        conclusion = opinion_conclusion(lead_raw)
        lead = table + (f"\n\n> 💬 **결론** — {conclusion}" if conclusion else "")
    else:
        lead = lead_raw  # 표를 못 만들면 원문 유지(안전)

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

    pieces = [banner, "---"]
    if lead:
        pieces.append(lead)
    pieces.append("\n\n".join(blocks))
    return "\n\n".join(pieces)


# 같은 모델을 재시도할 가치가 있는 일시적 서버 오류. (429/쿼터는 여기서 재시도하지 않고
#  build_model_chain 의 '다음 모델 폴백'으로 처리한다 — 일일 쿼터는 대기해도 회복되지 않으므로.)
_RETRIABLE_MARKERS = ("503", "500", "502", "504", "UNAVAILABLE", "high demand", "INTERNAL")

# 쿼터 소진(429) 또는 모델 사용 불가(404/미지원) → 다른 모델로 폴백해야 하는 오류
_FALLBACK_MARKERS = ("429", "resource_exhausted", "quota", "404", "not_found", "not found", "not supported")


def is_fallbackable(exc: Exception) -> bool:
    """다른(구세대) 모델로 폴백하면 해결될 수 있는 오류인지 판단."""
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    return code in (429, 404) or any(m in msg for m in _FALLBACK_MARKERS)


def build_model_chain(primary: str) -> list[str]:
    """사용자 지정 모델을 최우선으로, 무료 쿼터가 더 큰 구세대 모델을 폴백으로 잇는 체인.

    무료 티어 일일 쿼터(RPD)는 모델별로 분리되므로, 한 모델이 429(쿼터 소진)면
    다음 모델로 넘어가면 계속 검토할 수 있다. GEMINI_MODEL_FALLBACKS 로 폴백 목록을
    커스터마이즈할 수 있다(쉼표 구분).
    """
    chain = [primary]
    env_fb = (os.environ.get("GEMINI_MODEL_FALLBACKS") or "").strip()
    fallbacks = (
        [m.strip() for m in env_fb.split(",") if m.strip()]
        if env_fb
        else ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    )
    for m in fallbacks:
        if m not in chain:
            chain.append(m)
    return chain


def generate_with_retry(client, model, contents, config, attempts: int = 3, base_delay: float = 5.0):
    """Gemini 호출을 일시적 서버 오류(503/500 등)에 대해 지수 백오프로 재시도.

    429/쿼터·모델 불가 오류는 재시도하지 않고 즉시 raise 하여, 호출부의 모델 폴백이
    다음 모델로 넘어가도록 한다.
    """
    delay = base_delay
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # noqa: BLE001 - 재시도 판단 후 마지막에 재발생
            last_exc = exc
            code = getattr(exc, "code", None)
            msg = str(exc)
            retriable = code in (500, 502, 503, 504) or any(m in msg for m in _RETRIABLE_MARKERS)
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

    # 기본값은 'gemini-flash-latest' 별칭 — 항상 최신 Flash 버전으로 검토 품질을 확보한다.
    # (별칭이 실제로 어떤 버전으로 해석됐는지는 응답의 model_version 으로 확인해 출력한다.)
    # 빈 문자열(예: 미설정 GitHub 변수 vars.GEMINI_MODEL)도 기본값으로 대체되도록 `or` 사용.
    model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    fields = parse_issue_body(body)
    name = derive_dataset_name(title, fields)

    # ── 입력 사전 검증 (Gemini 무료 쿼터 절약) ─────────────────────────────
    # 데이터셋 명칭도 URL 도 전혀 없는 이슈는 의미 있는 검토가 불가능하므로,
    # API 를 호출하지 않고 즉시 실패 처리하여 무료 쿼터 낭비를 막는다.
    if not name and not any(
        fields.get(k)
        for k in ("related_datasets", "paper_urls", "homepage_url", "litigation_url")
    ):
        raise RuntimeError(
            "검토할 데이터셋 정보가 없습니다 (명칭·URL 모두 미입력). "
            "Gemini API 를 호출하지 않고 종료했습니다. "
            "이슈 폼 항목을 채워 이슈를 수정한 뒤 'rerun-review' 라벨을 붙여 재시도하세요."
        )

    user_prompt = build_user_prompt(title, fields)

    client = genai.Client(api_key=api_key)
    # Google 검색 그라운딩만 사용한다. 과거 url_context 도구(대용량 논문 PDF 직접 읽기)와
    # arXiv 초록 프롬프트 주입을 시도했으나, 각각 빈 응답·출력 반복 루프를 유발해 무료 티어
    # 검토가 실패했다. 검색 그라운딩 단독이 가장 안정적이라 이 방식으로 고정한다.
    tools = [types.Tool(google_search=types.GoogleSearch())]
    base_config = dict(
        system_instruction=system_prompt,
        tools=tools,
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

    # 현재 사용 가능한 모델을 순서대로 시도한다: 기본 모델(최신 Flash)이 429(쿼터 소진)
    # 이거나 사용 불가하면 무료 쿼터가 더 큰 구세대 모델로 자동 폴백한다.
    # 각 모델에서 출력이 MAX_TOKENS 로 잘리면(대시/반복 폭주) 같은 모델로 최대 1회 재생성한다.
    model_chain = build_model_chain(model)
    print(f"[diag] model_chain={model_chain}", file=sys.stderr)
    response = None
    text = ""
    finish_reason = ""
    used_model = model
    gen_error: Exception | None = None

    for ci, cand in enumerate(model_chain):
        used_model = cand
        try:
            for attempt in range(2):
                response = generate_with_retry(client, cand, user_prompt, config)
                text = (response.text or "").strip()
                finish_reason = ""
                try:
                    finish_reason = str(response.candidates[0].finish_reason or "")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    um = response.usage_metadata
                    print(
                        f"[diag] model={cand} attempt={attempt + 1} finish_reason={finish_reason} "
                        f"prompt={getattr(um, 'prompt_token_count', '?')} "
                        f"thoughts={getattr(um, 'thoughts_token_count', '?')} "
                        f"output={getattr(um, 'candidates_token_count', '?')} "
                        f"total={getattr(um, 'total_token_count', '?')} "
                        f"text_chars={len(text)}",
                        file=sys.stderr,
                    )
                except Exception:  # noqa: BLE001
                    pass
                if text and "MAX_TOKENS" not in finish_reason:
                    break
                if attempt == 0:
                    print(f"출력이 잘려(MAX_TOKENS) {cand} 로 1회 재생성합니다.", file=sys.stderr)
            gen_error = None
            break  # 이 모델로 응답(텍스트) 확보 → 폴백 중단
        except Exception as exc:  # noqa: BLE001 - 폴백 판단
            gen_error = exc
            if is_fallbackable(exc) and ci < len(model_chain) - 1:
                nxt = model_chain[ci + 1]
                print(
                    f"모델 `{cand}` 호출 실패({type(exc).__name__}: {str(exc)[:80]}) "
                    f"→ 다음 모델 `{nxt}` 로 폴백합니다.",
                    file=sys.stderr,
                )
                continue
            raise  # 폴백 불가 오류이거나 마지막 모델까지 실패 → 그대로 전파

    if gen_error is not None:
        raise gen_error
    if not text:
        raise RuntimeError(
            f"Gemini 응답이 비어 있습니다 (finish_reason={finish_reason or '알 수 없음'}). "
            "모델이 답변 없이 종료했거나 thinking 예산을 모두 소진했을 수 있습니다. "
            "'rerun-review' 라벨로 재시도하세요."
        )

    truncated = "MAX_TOKENS" in finish_reason

    # 실제 사용된 모델 버전 확인(별칭 해석 + 폴백 결과 반영)
    resolved_model = ""
    try:
        resolved_model = (response.model_version or "").strip()
    except Exception:  # noqa: BLE001
        pass
    if not resolved_model:
        resolved_model = used_model

    # 서비스 티어: 응답 메타데이터의 실제 값 우선, 없으면 환경변수/Standard
    service_tier = (os.environ.get("GEMINI_SERVICE_TIER") or "").strip()
    if not service_tier:
        try:
            tv = getattr(response.usage_metadata, "service_tier", None)
            if tv and str(tv).lower() != "none":
                service_tier = str(tv).capitalize()
        except Exception:  # noqa: BLE001
            pass
    service_tier = service_tier or "Standard"
    print(f"[diag] requested={model} used={used_model} resolved={resolved_model} tier={service_tier}", file=sys.stderr)

    # 검토 결과 최상단에 표시할 모델/티어 정보 헤더
    if used_model != model:
        model_line = f"**모델 정보:** `{resolved_model}` (요청 `{model}` 쿼터 소진/불가 → 폴백)"
    elif resolved_model != model:
        model_line = f"**모델 정보:** `{resolved_model}` (요청: `{model}`)"
    else:
        model_line = f"**모델 정보:** `{resolved_model}`"
    model_header = f"{model_line}\n**서비스 티어:** {service_tier}\n"

    text = strip_preamble(text)
    text = sanitize_markdown(text)
    sources = get_grounding_sources(response)
    text = linkify_citations(text, sources)
    text = restructure_review(text, name)
    parts = [model_header, text]
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
        f"<sub>🤖 자동 생성 (model: <code>{resolved_model}</code>, Google Search grounding) · "
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
