#!/usr/bin/env python3
"""오픈 데이터셋 법적 리스크 검토 에이전트 (GitHub Actions 실행용).

GitHub 이슈 폼으로 입력된 데이터셋 정보를 읽어, Google AI Studio(Gemini) API를
Google 검색 그라운딩과 함께 호출하여 법적 리스크 검토 보고서를 생성한다.
결과 Markdown은 --output 경로(기본: review.md)로 저장되며, 워크플로가 이를
이슈 댓글로 등록한다.

환경 변수
----------
GEMINI_API_KEY        : (필수) Google AI Studio API 키
GEMINI_DEFAULT_MODEL  : (선택) 기본(1차) 검토 모델. 기본값 gemini-flash-latest(항상 최신 Flash 별칭)
GEMINI_DEFAULT_FALLBACKS: (선택) 쉼표 구분 폴백 목록. 미설정 시 3.7→3.6→3.5→…→2.5 순 기본 체인
GEMINI_WRITER_MODEL    : (선택) 하이브리드 2패스 활성화. 설정하면 1차로 그라운딩 가능 모델
                        (무료 티어는 2.5 계열)로 웹검색 근거·출처를 수집한 뒤, 그 근거를
                        이 모델(예: gemini-3.7-flash)에 넘겨 그라운딩 없이 최종 검토문을
                        작성한다. 무료 티어에서 3.x 품질 + 출처 링크를 동시에 얻는다.
                        (무료 티어는 3.x 에 검색 그라운딩 쿼터가 없어 직접 그라운딩 호출은
                        429 가 나므로, 근거 수집만 2.5 에 위임하는 구조다.)
GEMINI_WRITER_FALLBACKS: (선택) 최종 작성 모델의 쉼표 구분 폴백. 미설정 시 3.7→3.6→3.5→3.5-lite
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
REPO_ROOT = SCRIPT_DIR.parent
# 시스템 프롬프트(검토 지침)는 prompt-book/ 폴더에서 일관되게 관리한다.
SYSTEM_PROMPT_PATH = REPO_ROOT / "prompt-book" / "system_prompt_dataset_review.md"

# 비글 마스코트 이미지(이슈 댓글용). GitHub 댓글은 camo 프록시가 SVG 를 잘 렌더링하지
# 못하므로 PNG(raw URL)를 사용한다. 저장소/브랜치는 GITHUB_REPOSITORY 로부터 유도.
_REPO = os.environ.get("GITHUB_REPOSITORY") or "aigovsensing/dataset-review"
BEAGLE_IMG = (
    os.environ.get("BEAGLE_IMG_URL")
    or f"https://raw.githubusercontent.com/{_REPO}/main/docs/beagle.png"
)

# 이슈 폼(dataset-review.yml)의 라벨 → 내부 필드 키 매핑
FIELD_LABELS = {
    "데이터셋 명칭": "dataset_name",
    "관련 / 원본 데이터셋": "related_datasets",
    "논문 주소 (URL)": "paper_urls",
    "데이터셋 저장소 URL": "dataset_repo_url",
    "소스코드 저장소 URL": "code_repo_url",
    # 구버전 폼 호환: 과거 이슈의 "공식 홈페이지 / 저장소 URL" 도 계속 인식
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
        name = re.sub(r"^\s*\[(?:데이터셋검토|검토)\]\s*", "", title).strip()
    return name


def parse_courtlistener_url(url: str) -> dict[str, str]:
    """CourtListener docket URL 에서 사건명(슬러그)·docket id 를 추출한다.

    모델은 URL 을 직접 읽지 못하고 Google 검색만 사용하므로, URL 슬러그에서 사건명을
    복원해 프롬프트에 넘겨주면 검색으로 사건을 특정할 확률이 크게 올라간다.

    예: .../docket/73339261/nassif-v-samsung-electronics-co-ltd/
        → {"docket_id": "73339261", "case_name": "Nassif v. Samsung Electronics Co Ltd"}
    """
    info: dict[str, str] = {}
    m = re.search(r"courtlistener\.com/docket/(\d+)/([a-z0-9-]+)", url or "", re.I)
    if not m:
        return info
    info["docket_id"] = m.group(1)
    slug = m.group(2).strip("-")

    def _cap(s: str) -> str:
        return " ".join(w.capitalize() for w in s.split("-") if w)

    parts = re.split(r"-v-", slug, maxsplit=1)
    if len(parts) == 2:
        info["case_name"] = f"{_cap(parts[0])} v. {_cap(parts[1])}"
    elif slug:
        info["case_name"] = _cap(slug)
    return info


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
    if fields.get("dataset_repo_url"):
        lines.append(f"- 데이터셋 저장소(라이선스 1차 근거): {fields['dataset_repo_url']}")
    if fields.get("code_repo_url"):
        lines.append(f"- 소스코드 저장소(참고 — 코드 라이선스, 데이터셋 라이선스와 구분): {fields['code_repo_url']}")
    if fields.get("homepage_url"):  # 구버전 폼 호환
        lines.append(f"- 공식 홈페이지 / 저장소: {fields['homepage_url']}")
    if fields.get("dataset_repo_url") or fields.get("code_repo_url"):
        lines.append(
            "\n[라이선스 판정 기준] 라이선스는 반드시 **데이터셋 저장소/데이터셋 자체의 라이선스**를 기준으로 "
            "판정한다. 소스코드 저장소(GitHub 등)의 라이선스는 코드에만 적용될 수 있어 데이터셋 라이선스와 "
            "다를 수 있으므로, 둘이 다르면 **데이터셋 라이선스를 우선**하고 코드 라이선스는 참고로만 언급한다. "
            "데이터셋 저장소에 라이선스가 명시돼 있으면 그 원문을 인용한다."
        )
    if fields.get("litigation_url"):
        lines.append(f"- 관련 소송 (CourtListener): {fields['litigation_url']}")
        cl = parse_courtlistener_url(fields["litigation_url"])
        if cl.get("case_name"):
            docket = f" (docket #{cl['docket_id']})" if cl.get("docket_id") else ""
            lines.append(f"  · URL 에서 파악되는 사건명(추정): {cl['case_name']}{docket}")
    if fields.get("extra_notes"):
        lines.append(f"- 추가 참고 사항: {fields['extra_notes']}")
    if fields.get("litigation_url"):
        lines.append(
            "\n[중요] 관련 소송 URL 이 제공되었다. 이 데이터셋은 해당 소송과 연관된 것으로 검토 요청되었으므로, "
            "출력의 '3. 소송 리스크' 섹션을 **절대 '해당 없음'으로 표기하지 말 것.** 위 사건명(추정)으로 Google 검색을 "
            "수행해 사건 개요(사건명·법원·사건번호·원고·피고·상태)와, 이 데이터셋이 소송에서 어떻게 문제되는지를 "
            "조사·보고하라. 검색으로 소장 원문을 확인하지 못한 항목은 그 항목만 '확인 불가'로 표기하되, "
            "**사건 개요와 '근거 강도'(강/중/약, 판단 불가 시 '확인 불가')는 반드시 포함한다.** "
            "조사 결과 이 데이터셋과 소송의 연관성이 실제로 확인되지 않으면 '해당 없음'이 아니라 "
            "'소송과의 직접 연관성 미확인 — 근거: …'로 사유를 명시하고, 제공된 사건 개요는 그대로 보고한다."
        )
    lines += [
        "",
        "[소송 리스크 — 필수] 소송 URL 제공 여부와 무관하게, 이 데이터셋(및 원본 데이터셋)이 "
        "'저작권자 허가 없이 AI 모델 학습에 무단 사용되어 제기된 소송'에 연루됐는지 Google 검색으로 "
        "반드시 조사하라(예: \"<데이터셋명>\" lawsuit / copyright infringement / AI training lawsuit). "
        "확인되면 '3. 소송 리스크'에 사건 개요·근거 강도와 함께 보고하고, 검색으로도 확인되지 않으면 "
        "'해당 없음 (검색 결과 관련 소송 미확인)'으로 표기한다(검색 없이 '해당 없음' 단정 금지).",
        "",
        "[데이터 생성·수집 방식 — 자기 재검증 필수] '데이터 생성·수집 방식' 항목은 초안 결론을 그대로 "
        "확정하지 말고, 시스템 지침의 「🔁 필수 자기 재검증」에 따라 근거 원문을 다시 읽고 재확인한 뒤 "
        "확정 내용만 기재하라(무지성 반복 금지, 불일치 시 수정, 근거 부족 시 '확인 불가').",
        "",
        "[자의적 해석 금지 — 신뢰성 필수] 근거 없는 해석·요약을 사실처럼 쓰지 말 것. 큰따옴표 원문 인용은 "
        "출처에 그 문장이 실제로 있을 때만 사용하고, 없으면 지어내지 말고 '확인 불가'로 둔다. 사용자 입력"
        "(prompt)은 근거가 아니다. **사실을 주장하는 모든 문장(확인 결과 포함) 끝에 실제 출처 URL 을 "
        "`([출처](URL))` 로 붙여** 근거를 밝힌다(뒷받침 출처 없으면 '확인 불가').",
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


# 이미 링크가 아닌 맨 `[N]` 인용 표기(예: "[3]")를 잡되, `[3](...)` 처럼 이미 링크된 것은 제외.
_BRACKET_CITE_RE = re.compile(r"\[(\d{1,3})\](?!\()")


def linkify_bracket_citations(text: str, sources: list[tuple[str, str]]) -> str:
    """본문의 맨 `[N]` 표기를 출처 URL 로 가는 마크다운 링크 `[N](url)` 로 변환.

    하이브리드 2패스에서 최종 작성 모델(그라운딩 없음)은 그라운딩 메타데이터가 없으므로,
    1차 패스에서 확정된 출처 번호를 본문에 `[N]` 으로 표기하게 하고 여기서 링크로 만든다.
    N 이 출처 개수 범위를 벗어나면 원문(`[N]`)을 그대로 둔다. 이미 링크된 `[N](...)` 는 건드리지 않는다.
    """
    if not sources:
        return text

    def _repl(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(sources):
            return f"[{n}]({sources[n - 1][1]})"
        return m.group(0)

    return _BRACKET_CITE_RE.sub(_repl, text)


def render_sources(sources: list[tuple[str, str]]) -> str:
    """인용 번호와 일치하는 번호 매김 출처 목록을 마크다운으로 렌더링."""
    return "\n".join(
        f"{i + 1}. [{title}]({uri})" for i, (title, uri) in enumerate(sources)
    )


# 본문의 `[출처 N]` / `[출처 N, M]` 참조(예: "([출처 1])", "높음 [출처 19]").
# 뒤에 '(' 가 오면(이미 마크다운 링크 `[출처 1](url)`) 건드리지 않는다.
_SRC_REF_RE = re.compile(r"\[출처\s*(\d+(?:\s*,\s*\d+)*)\](?!\()")


def link_source_refs(text: str, sources: list[tuple[str, str]]) -> str:
    """본문의 `[출처 N]` 을 실제 출처 URL 로 가는 클릭 가능한 링크로 변환한다.

    N 은 그라운딩 출처(=아래 '참고 출처' 목록·본문 `[N]` 각주)의 번호와 같은 체계다.
    범위를 벗어나는 N 은 링크로 만들지 않고 원문(`[출처 N]`)을 그대로 둔다.
    """
    if not sources:
        return text

    def repl(m: re.Match) -> str:
        out = []
        for p in re.split(r"\s*,\s*", m.group(1)):
            idx = int(p)
            if 1 <= idx <= len(sources):
                out.append(f"[출처 {idx}]({sources[idx - 1][1]})")
            else:
                out.append(f"[출처 {idx}]")
        return ", ".join(out)

    return _SRC_REF_RE.sub(repl, text)


def number_source_list(text: str) -> str:
    """'## 5. 근거 및 출처' 섹션의 불릿 목록에 `1) 2) 3)` 번호를 매긴다."""
    m = re.search(r"^##\s+5\.\s*근거\s*및\s*출처\s*$", text, re.MULTILINE)
    if not m:
        return text
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    seg = text[start:end]

    counter = {"n": 0}

    def repl_bullet(bm: re.Match) -> str:
        counter["n"] += 1
        return f"{bm.group(1)}{counter['n']}) {bm.group(2)}"

    seg = re.sub(r"^([ \t]*)[*\-]\s+(.*)$", repl_bullet, seg, flags=re.MULTILINE)
    return text[:start] + seg + text[end:]


# 모델이 직접 단 '[출처](url)' · '[출처 N](url)' · '[출처 1, 2](url)' 형태의 인라인 링크.
_SRC_WORD_LINK_RE = re.compile(r"\[출처[^\]]*\]\((https?://[^)\s]+)\)")


def unify_citations(text: str, sources: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
    """인용 표기를 모두 번호 `[N]` 로 통일한다.

    그라운딩 자동 각주는 이미 `[N]`(하단 목록의 N 번과 연결) 이지만, 모델이 종합한 판단
    근거 문장에는 자동 각주가 안 붙어 모델이 직접 `[출처](URL)` 링크를 단다. 이 '출처'
    단어 링크를 같은 번호 체계의 `[N]` 로 바꿔 표기를 일관되게 만든다.

    모델이 인용한 URL 이 그라운딩 출처 목록에 이미 있으면 그 번호를, 없으면 목록 끝에
    새 번호로 추가한다. 반환: (치환된 text, 통합 출처 목록[(제목, URL)…]).
    """
    order = list(sources)                       # 그라운딩 출처가 1..K 번을 차지
    num: dict[str, int] = {}
    for i, (_title, uri) in enumerate(order):
        num.setdefault(uri, i + 1)

    def repl(m: re.Match) -> str:
        url = m.group(1).strip()
        n = num.get(url)
        if n is None:                           # 목록에 없는 URL → 끝에 새 번호로 등록
            dom = re.match(r"https?://([^/]+)", url)
            order.append((dom.group(1) if dom else url, url))  # 라벨은 도메인(가독성)
            n = len(order)
            num[url] = n
        return f"[{n}]({url})"

    return _SRC_WORD_LINK_RE.sub(repl, text), order


# 번호 인용 링크가 구분자 없이 붙은 경우: '](url)[N](' 경계.
_ADJACENT_CITE_RE = re.compile(r"(\]\(https?://[^)\s]+\))(\[\d)")


def separate_adjacent_citations(text: str) -> str:
    """붙어 있는 번호 인용 링크(…](u)[11](u)[12](u)…)를 콤마로 분리한다.

    구분자가 없으면 링크 텍스트 '11','12',… 가 이어져 '111213…' 처럼 하나의 큰 숫자로
    보인다. 3개 이상 연속도 모두 분리되도록 더 이상 바뀌지 않을 때까지 반복 적용한다.
    """
    prev = None
    while prev != text:
        prev = text
        text = _ADJACENT_CITE_RE.sub(r"\1, \2", text)
    return text


def insert_grounding_citations(raw_text: str, response) -> str:
    """근거가 있는 문장 끝에 출처 링크 `[N]` 을 자동 삽입한다.

    Gemini 의 그라운딩 메타데이터(`grounding_supports`)는 각 지원 구간(segment)의
    바이트 오프셋과 그 구간을 뒷받침하는 `grounding_chunks` 인덱스를 제공한다.
    이를 이용해 해당 문장 끝에 `[N](출처 URL)` 형태의 클릭 가능한 각주를 삽입한다.
    N 은 chunk 인덱스+1 로, '참고 출처' 목록(render_sources)의 번호와 일치한다.

    모델이 스스로 인용 번호를 매기는 방식은 그라운딩 청크의 최종 순서를 알 수 없어
    부정확하다. 반면 이 메타데이터는 "어느 문장이 어느 출처에 근거하는가"를 API 가
    정확히 알려주므로, 문장→출처 매핑이 신뢰할 수 있다.

    주의: segment 오프셋은 원본 응답 텍스트(response.text) 기준이므로, strip_preamble·
    sanitize 등 전처리로 텍스트가 바뀌기 **전에** raw_text 에 적용해야 한다.
    """
    if not raw_text:
        return raw_text
    try:
        cand = (response.candidates or [None])[0]
        meta = getattr(cand, "grounding_metadata", None) if cand else None
    except Exception:  # noqa: BLE001 - 그라운딩 메타데이터는 부가 정보
        return raw_text
    if not meta:
        return raw_text
    supports = getattr(meta, "grounding_supports", None) or []
    chunks = getattr(meta, "grounding_chunks", None) or []
    print(f"[diag] grounding supports={len(supports)} chunks={len(chunks)}", file=sys.stderr)
    if not supports or not chunks:
        return raw_text

    # 멀티 파트 대비: segment.end_index 는 segment.part_index 파트 기준의 바이트 오프셋.
    try:
        parts = list(getattr(getattr(cand, "content", None), "parts", None) or [])
    except Exception:  # noqa: BLE001
        parts = []
    part_prefix: list[int] = []
    acc = 0
    for p in parts:
        part_prefix.append(acc)
        acc += len((getattr(p, "text", None) or "").encode("utf-8"))

    data = raw_text.encode("utf-8")
    at: dict[int, list[tuple[int, str]]] = {}  # 바이트 위치 -> [(번호, uri), ...]
    for s in supports:
        seg = getattr(s, "segment", None)
        if not seg:
            continue
        end = getattr(seg, "end_index", None)
        if end is None:
            continue
        pi = getattr(seg, "part_index", None) or 0
        base = part_prefix[pi] if 0 <= pi < len(part_prefix) else 0
        pos = base + int(end)
        if pos < 0 or pos > len(data):
            continue
        for ci in (getattr(s, "grounding_chunk_indices", None) or []):
            if 0 <= ci < len(chunks):
                web = getattr(chunks[ci], "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    at.setdefault(pos, []).append((ci + 1, uri))

    print(f"[diag] citation insert positions={len(at)} data_bytes={len(data)}", file=sys.stderr)
    if not at:
        return raw_text
    # 뒤에서부터 삽입해 앞쪽 오프셋을 보존한다.
    for pos in sorted(at.keys(), reverse=True):
        seen: set[int] = set()
        marks: list[str] = []
        # 번호 오름차순으로 정렬해 표기(11,12,…) — 한 문장에 여러 출처가 붙을 때 가독성.
        for n, uri in sorted(at[pos], key=lambda t: t[0]):
            if n in seen:
                continue
            seen.add(n)
            marks.append(f"[{n}]({uri})")
        if not marks:
            continue
        # 문장 끝에 이미 공백/개행이 있으면 앞 공백을 넣지 않아 이중 공백을 피한다.
        # 여러 각주는 콤마+공백으로 분리해 '111213…' 처럼 한 덩어리로 보이지 않게 한다.
        lead = b"" if (pos > 0 and data[pos - 1:pos] in (b" ", b"\n", b"\t")) else b" "
        data = data[:pos] + lead + ", ".join(marks).encode("utf-8") + data[pos:]
    return data.decode("utf-8", errors="ignore")


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


# 프롬프트가 요구하는 고정 판정 줄: "**판정: 추가 검토 필요**" (볼드/공백 변형 허용)
_VERDICT_MARKER_RE = re.compile(
    r"판정\s*[:：]\s*\**\s*(사용\s*비권고|추가\s*검토\s*필요|사용\s*가능)"
)


def detect_verdict(text: str) -> tuple[str | None, str]:
    """'내부 검토 결과' 판정을 추출. 못 찾으면 (None, 📋).

    탐색 순서(가장 신뢰할 수 있는 것부터):
      1) 프롬프트가 강제하는 고정 마커 `판정: <판정>` — 가장 명확하므로 최우선.
      2) '내부 검토 결과' 헤딩 바로 다음(비어 있지 않은) 몇 줄에서 판정 문구 탐색.
      3) 폴백: 본문 전체에서 가장 보수적인 판정을 탐색.
    """
    # 1) 고정 판정 마커 우선(공백 변형은 정규화해 매칭)
    m = _VERDICT_MARKER_RE.search(text)
    if m:
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        # 매칭 결과의 공백을 표준 라벨(공백 없는 형태)로 되돌려 이모지 조회
        normalized = label.replace(" ", "")
        for lbl, emoji in _VERDICTS:
            if lbl.replace(" ", "") == normalized:
                return lbl, emoji

    # 2) '내부 검토 결과' 헤딩 다음 줄들(공백 줄 건너뛰고 최대 3줄)에서 탐색
    m = re.search(r"내부\s*검토\s*결과[^\n]*\n+((?:[^\n]*\n?){0,3})", text)
    region = m.group(1) if m else text[:500]
    for label, emoji in _VERDICTS:
        if label in region:
            return label, emoji

    # 3) 폴백: 본문 전체에서 가장 보수적인(먼저 오는) 판정 탐색
    for label, emoji in _VERDICTS:
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
    """(라벨, 확인 결과, 내부 판단, 판단 근거) 목록으로 종합의견 4열 표를 렌더.

    판정('내부 검토 결과')은 표 바로 위 배너(`> **내부 검토 결과** …`)에 이미
    노출되므로, 표 안에 별도 판정 행을 두지 않는다(중복 제거). `verdict_line` 은
    호출부 호환을 위해 시그니처에만 남긴다.
    """
    del verdict_line  # 배너에서 이미 표시 — 표 행으로 중복 출력하지 않음
    rows: list[str] = []
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


# 접이식 상세 본문 안의 마크다운 헤딩(#..######)을 잡아 볼드 라벨로 낮춘다.
# (details 의 summary 는 볼드라, 본문에 H3 등이 오면 자식이 부모보다 커 보이는 역전이 생김)
_BODY_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$", re.MULTILINE)


def demote_body_headings(body: str) -> str:
    """상세 섹션 본문의 헤딩을 볼드 텍스트로 낮춰, summary 보다 커 보이지 않게 한다.

    예) '### 라이선스' → '**라이선스**'. 목록·인용 등 다른 서식은 그대로 둔다.
    """
    return _BODY_HEADING_RE.sub(lambda m: f"**{m.group(1).strip()}**" if m.group(1).strip() else "", body)


def restructure_review(text: str, name: str) -> str:
    """모델 출력을 스캔하기 쉬운 형태로 재구성.

    - 상단에 데이터셋명 + 판정 배지 배너를 붙인다.
    - 배너 바로 아래에 '종합의견' 표(복사·붙여넣기용 요약)를 펼친 상태로 노출.
    - '1. 요약 결론' 은 이 표의 원천이라 내용이 겹치므로, 표를 그 섹션에서 만든 경우
      별도 블록으로 다시 보여주지 않는다(중복 제거).
    - 상세/소송/근거 섹션은 앞 번호 없이 아이콘+제목의 접이식(<details>)으로 정리하고
      첫 상세 섹션만 펼친다(번호가 2부터 시작해 보이는 혼란 방지).
    - 예상 형식(## N. 제목)이 아니면 원문을 그대로 두어 안전하게 처리한다.
    """
    text = ensure_detail_section_header(text)
    verdict, emoji = detect_verdict(text)
    verdict_line = f"{emoji} **{verdict}**" if verdict else "📋 (판정 확인 불가)"
    banner = (
        f'<img src="{BEAGLE_IMG}" align="right" width="76" alt="비글(Beagle)" />\n\n'
        "# 🐶 비글 · 오픈 데이터셋 법적 리스크 검토 결과\n\n"
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
    table = summary_from_yoyak(text[matches[0].end():sec1_end], verdict_line)
    table_from_section1 = bool(table)  # 표를 '1. 요약 결론' 에서 만들었는가(=그 섹션은 중복)
    if not table:
        table = summary_from_opinion(lead_raw, verdict_line)
    if table:
        conclusion = opinion_conclusion(lead_raw)
        lead = table + (f"\n\n> 💬 **결론** — {conclusion}" if conclusion else "")
    else:
        lead = lead_raw  # 표를 못 만들면 원문 유지(안전)

    icons = {"1": "🧭", "2": "🔍", "3": "⚖️", "4": "🎓", "5": "📚"}
    blocks: list[str] = []
    for i, m in enumerate(matches):
        num, sec_title = m.group(1), m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip().strip("-").strip()
        icon = icons.get(num, "📄")
        if num == "1":
            # '1. 요약 결론' = 상단 종합의견 표의 원천. 표를 이 섹션에서 만들었으면 중복이라 생략.
            if table_from_section1:
                continue
            blocks.append(f"## {icon} 요약 결론\n\n{body}")  # 폴백(표 원천이 아닐 때만) — 안전
            continue
        if "출처" in sec_title:
            # 모델이 쓴 '근거 및 출처' 섹션은 생략한다. 코드가 하단에 본문 [N] 번호와 정확히
            # 일치하는 통합 '근거 및 출처' 목록을 자동으로 붙이므로, 번호 체계가 다른 모델
            # 목록을 함께 두면 중복·혼란을 유발한다.
            continue
        # 상세/소송: 앞 번호 없이 아이콘+제목만. 전부 기본 접힘(<details>) 상태로 둔다.
        # 본문 헤딩은 볼드로 낮춰 summary(라이선스 등 하위 제목이 더 커 보이는 역전) 방지.
        blocks.append(
            f"<details>\n<summary><b>{icon} {sec_title}</b></summary>\n\n"
            f"{demote_body_headings(body)}\n\n</details>"
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


def is_transient(exc: Exception) -> bool:
    """일시적 서버 오류(503/500 등)인지 판단.

    같은 모델 재시도로도, 다른 모델 폴백으로도 회복될 수 있는 카테고리다.
    특정 모델의 'high demand' 503 은 그 모델 고유의 과부하일 때가 많아, 재시도가
    소진되면 다른 모델로 넘어가는 것이 성공 확률이 높다.
    """
    code = getattr(exc, "code", None)
    msg = str(exc)
    return code in (500, 502, 503, 504) or any(m in msg for m in _RETRIABLE_MARKERS)


def is_fallbackable(exc: Exception) -> bool:
    """다른(구세대) 모델로 폴백하면 해결될 수 있는 오류인지 판단.

    - 429/쿼터·404/미지원: 그 모델로는 더 진행 불가 → 폴백.
    - 503/500 등 일시적 서버 오류: 같은 모델 재시도가 소진된 뒤라도, 다른 모델은
      과부하가 아닐 수 있으므로 폴백 대상에 포함한다.
    """
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    return code in (429, 404) or any(m in msg for m in _FALLBACK_MARKERS) or is_transient(exc)


def fallback_reason_tag(exc: Exception) -> str:
    """폴백 사유를 사람이 읽기 쉬운 짧은 태그로 분류(결과 헤더·로그 표기용)."""
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    if code == 429 or any(m in msg for m in ("resource_exhausted", "quota", "rate limit")):
        if "prepayment credits" in msg:
            return "429 선불 크레딧 소진"
        return "429 무료 쿼터 소진"
    if code == 404 or any(m in msg for m in ("not_found", "not found", "not supported")):
        return "404 모델 미지원/불가"
    if is_transient(exc):
        return "503 일시 과부하"
    return type(exc).__name__


def build_model_chain(primary: str) -> list[str]:
    """사용자 지정 모델을 최우선으로, 품질→안정성 순으로 내려가는 폴백 체인.

    무료 티어 일일 쿼터(RPD)는 모델별로 분리되므로, 한 모델이 429(쿼터 소진)면
    다음 모델로 넘어가면 계속 검토할 수 있다. GEMINI_DEFAULT_FALLBACKS 로 폴백 목록을
    커스터마이즈할 수 있다(쉼표 구분).

    기본 폴백 체인은 **품질 우선(최신 3.x부터) → 안정성(무료 쿼터가 큰 2.5로 하강)**
    으로 구성한다. 무료 티어에서는 최신 모델의 일일 쿼터가 작아 상시 소진되기 쉬우므로,
    끝을 무료 쿼터가 가장 큰 gemini-2.5-flash-lite 로 두어 어떤 경우에도 답변을 보장한다.

    ⭐ 첫 폴백을 최신 세대 gemini-3.7-flash 로 둔다. 주 모델 별칭 gemini-flash-latest
    가 3.7 로 해석되기 전이거나 별칭 호출이 일시적 오류·빈 응답을 반환해도, 3.7 을 명시적
    으로 한 번 시도한 뒤 곧바로 직전 stable 인 3.6 으로 이어가 구세대(2.5)로 급락하지
    않게 한다. (별칭 라우팅과 명시 엔드포인트는 장애 지점이 달라 재시도 가치가 크다.)
    3.7 Flash 는 도입가(유료) 기준으로 안내된 신규 모델이라, 무료 티어에 아직 개방되지
    않은 키에서는 404/403/429 를 반환할 수 있는데, 이 경우 체인이 자동으로 3.6 으로
    내려가므로 무료 키에서도 검토가 끊기지 않는다. 이어서 3.5 → 3.x-lite 로 같은 세대를
    소진한 뒤에야 2.5 로 하강한다. stable 모델 ID 는
    https://ai.google.dev/gemini-api/docs/models 기준이며, 3.1 은 풀 flash 가 없어
    flash-lite 만 존재한다. (프리뷰/실험 모델은 불안정하여 제외)
    """
    chain = [primary]
    env_fb = (os.environ.get("GEMINI_DEFAULT_FALLBACKS") or "").strip()
    fallbacks = (
        [m.strip() for m in env_fb.split(",") if m.strip()]
        if env_fb
        else [
            "gemini-3.7-flash",       # 최신 세대 Flash (코딩·에이전트 품질 향상). 무료 티어 미개방 시
                                       #   404/403/429 로 즉시 다음 후보(3.6)로 폴백된다.
            "gemini-3.6-flash",       # 직전 stable Flash (별칭 실패 시에도 3.6 을 한 번 더 명시 시도)
            "gemini-3.5-flash",       # 이전 세대 풀 Flash
            "gemini-3.5-flash-lite",  # 3.5 세대 경량
            "gemini-3.1-flash-lite",  # 3.x 세대 경량
            "gemini-2.5-flash",       # 안정성 축 (무료 쿼터 넉넉)
        ]
    )
    for m in fallbacks:
        if m not in chain:
            chain.append(m)
    return chain


def generate_with_retry(client, model, contents, config, attempts: int = 4, base_delay: float = 5.0):
    """Gemini 호출을 일시적 서버 오류(503/500 등)에 대해 지수 백오프로 재시도.

    429/쿼터·모델 불가 오류는 재시도하지 않고 즉시 raise 하여, 호출부의 모델 폴백이
    다음 모델로 넘어가도록 한다. 지속되는 503 도 여기서 소진되면 호출부가 다음 모델로
    폴백한다(is_fallbackable 가 일시적 오류를 폴백 대상에 포함).

    기본 4회(대기 5s→10s→20s, 최대 ~35s)로 짧은 데모 과부하 스파이크를 흡수한다.
    """
    delay = base_delay
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # noqa: BLE001 - 재시도 판단 후 마지막에 재발생
            last_exc = exc
            if not is_transient(exc) or i == attempts - 1:
                raise
            print(
                f"일시적 오류로 재시도 ({i + 1}/{attempts - 1}), {delay:.0f}s 대기: {str(exc)[:120]}",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, 40.0)
    assert last_exc is not None  # 도달하지 않음
    raise last_exc


def build_final_model_chain() -> list[str]:
    """하이브리드 2패스의 '최종 작성' 모델 체인(그라운딩 없이 호출).

    GEMINI_WRITER_MODEL 을 최우선으로, GEMINI_WRITER_FALLBACKS(또는 기본 3.x 목록)를 잇는다.
    무료 티어에서 3.x 는 그라운딩만 429 이고 본문 생성은 정상이므로, 여기서는 그라운딩을
    붙이지 않고 1차에서 수집한 근거만으로 작성한다.
    """
    primary = (os.environ.get("GEMINI_WRITER_MODEL") or "").strip()
    if not primary:
        return []
    env_fb = (os.environ.get("GEMINI_WRITER_FALLBACKS") or "").strip()
    fallbacks = (
        [m.strip() for m in env_fb.split(",") if m.strip()]
        if env_fb
        else ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    )
    chain: list[str] = []
    for m in [primary, *fallbacks]:
        if m and m not in chain:
            chain.append(m)
    return chain


def run_final_pass(client, types, final_models, system_prompt, base_user_prompt,
                   grounded_draft, sources):
    """하이브리드 2패스: 그라운딩 없이 최종 검토문을 재작성한다.

    1차(그라운딩) 패스가 만든 근거 초안(grounded_draft, `[N](url)` 인용 포함)과 확정된
    출처 목록을 사실 근거로 넘겨, 최종 모델(3.x)이 [출력 형식]에 맞춰 최종 검토를 쓴다.
    성공하면 (텍스트, 사용모델), 전 모델 실패하면 (None, "") 를 반환한다(→ 1차 결과로 폴백).
    """
    if not final_models:
        return None, ""
    src_list = render_sources(sources) if sources else "(수집된 출처 없음)"
    instruction = (
        base_user_prompt
        + "\n\n[하이브리드 최종 작성 지침]\n"
        "이번 호출에는 검색 도구가 없다. 아래 '1차 근거 초안'과 '확인된 출처'만을 사실 "
        "근거로 삼아, 시스템 지침의 [출력 형식]에 정확히 맞춰 최종 검토를 작성하라.\n"
        "- 초안 문장 끝의 인용 표기 `[N]`(및 `[N](URL)`) 을 보존하라. 출처 번호 N 과 URL 을 "
        "바꾸거나 새로 지어내지 마라.\n"
        "- 아래 목록에 없는 URL·사실을 추가하지 마라(환각 금지). 근거가 없으면 '확인 불가'로 남겨라.\n"
        "- 초안의 사실관계를 검증·정리·보강하되, 형식(섹션 구성·표)은 시스템 지침을 따른다.\n\n"
        "── 1차 근거 초안 ──\n" + grounded_draft + "\n\n"
        "── 확인된 출처(번호=인용 N) ──\n" + src_list
    )
    base = dict(system_instruction=system_prompt, temperature=0.2, max_output_tokens=32768)
    try:
        cfg = types.GenerateContentConfig(
            **base, thinking_config=types.ThinkingConfig(thinking_budget=8192))
        cfg_min = types.GenerateContentConfig(
            **base, thinking_config=types.ThinkingConfig(thinking_budget=512))
    except Exception:  # noqa: BLE001 - 구버전 SDK 호환
        cfg = types.GenerateContentConfig(**base)
        cfg_min = cfg

    for cand in final_models:
        try:
            for attempt in range(2):
                c = cfg if attempt == 0 else cfg_min
                resp = generate_with_retry(client, cand, instruction, c)
                t = (resp.text or "").strip()
                fr = ""
                try:
                    fr = str(resp.candidates[0].finish_reason or "")
                except Exception:  # noqa: BLE001
                    pass
                print(
                    f"[diag] final_pass model={cand} attempt={attempt + 1} "
                    f"finish_reason={fr} text_chars={len(t)}",
                    file=sys.stderr,
                )
                if t:  # 잘렸더라도(text 존재) 채택 — 1차 결과보다 신세대 품질 우선.
                    return t, cand
            # text 가 계속 비면 다음 모델로.
        except Exception as exc:  # noqa: BLE001 - 실패 시 다음 최종 모델로 폴백
            print(
                f"[diag] final_pass model={cand} 실패({type(exc).__name__}: {str(exc)[:80]})",
                file=sys.stderr,
            )
            continue
    return None, ""


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
    # 빈 문자열(예: 미설정 GitHub 변수 vars.GEMINI_DEFAULT_MODEL)도 기본값으로 대체되도록 `or` 사용.
    model = os.environ.get("GEMINI_DEFAULT_MODEL") or "gemini-flash-latest"
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    fields = parse_issue_body(body)
    name = derive_dataset_name(title, fields)

    # ── 입력 사전 검증 (Gemini 무료 쿼터 절약) ─────────────────────────────
    # 데이터셋 명칭도 URL 도 전혀 없는 이슈는 의미 있는 검토가 불가능하므로,
    # API 를 호출하지 않고 즉시 실패 처리하여 무료 쿼터 낭비를 막는다.
    if not name and not any(
        fields.get(k)
        for k in ("related_datasets", "paper_urls", "dataset_repo_url", "code_repo_url", "homepage_url", "litigation_url")
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

    # 재생성(2차 시도)용 보조 config: thinking 예산을 최소화해 '답변' 토큰을 최대한 확보한다.
    # gemini 2.5/3.x 계열이 thinking 에 예산을 소진하고 답변 없이 STOP 으로 종료해 빈 응답이
    # 나오는 경우(finish_reason=STOP, text 없음)를 완화하기 위함이다. (thinking_config 필드는
    # 위 config 와 동일 타입이라 생성은 안전하며, 미지원 SDK/모델이면 기본 config 로 대체한다.)
    try:
        config_min_think = types.GenerateContentConfig(
            **base_config,
            thinking_config=types.ThinkingConfig(thinking_budget=512),
        )
    except Exception:  # noqa: BLE001 - 구버전 SDK 호환
        config_min_think = config

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
    requested_fail_reason = ""  # 요청 모델이 왜 사용되지 못했는지(429/404/503/빈 응답)
    attempts: list[tuple[str, bool]] = []  # 시도한 모델과 성공 여부(헤더에 폴백 경로 표기)

    for ci, cand in enumerate(model_chain):
        used_model = cand
        try:
            for attempt in range(2):
                # 2차 시도는 thinking 을 최소화한 config 로 답변 토큰을 최대 확보(빈 응답 완화).
                cfg = config if attempt == 0 else config_min_think
                response = generate_with_retry(client, cand, user_prompt, cfg)
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
                    why = "빈 응답(STOP)" if not text else "출력 잘림(MAX_TOKENS)"
                    print(
                        f"{cand}: {why} → thinking 최소화 config 로 1회 재생성합니다.",
                        file=sys.stderr,
                    )
            # 텍스트가 있으면(잘렸더라도) 이 응답을 채택하고 폴백 중단.
            if text:
                attempts.append((cand, True))
                gen_error = None
                break
            # 예외는 없었지만 답변이 완전히 비었다(STOP인데 text 없음).
            # → 같은 config 재시도로는 동일 결과일 가능성이 크므로 다음(더 안정적인) 모델로 폴백.
            attempts.append((cand, False))
            if ci < len(model_chain) - 1:
                nxt = model_chain[ci + 1]
                if cand == model and not requested_fail_reason:
                    requested_fail_reason = "빈 응답(STOP)"
                print(
                    f"모델 `{cand}` 가 답변 없이 종료(빈 응답, finish_reason={finish_reason or '?'}) "
                    f"→ 다음 모델 `{nxt}` 로 폴백합니다.",
                    file=sys.stderr,
                )
                gen_error = None
                continue
            gen_error = None  # 마지막 모델까지 빈 응답 → 아래에서 RuntimeError
        except Exception as exc:  # noqa: BLE001 - 폴백 판단
            gen_error = exc
            attempts.append((cand, False))
            if is_fallbackable(exc) and ci < len(model_chain) - 1:
                nxt = model_chain[ci + 1]
                if cand == model and not requested_fail_reason:
                    requested_fail_reason = fallback_reason_tag(exc)
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
            "폴백 체인의 모든 모델이 답변 없이 종료했습니다(대개 thinking 예산 소진). "
            "잠시 후 'rerun-review' 라벨로 재시도하세요."
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

    # 서비스 티어(표시용 라벨): 환경변수 GEMINI_SERVICE_TIER 우선 → 없으면 응답 메타데이터로
    # 자동 판별 → 그래도 없으면 무료 티어 앱 기본값 "Free". (변수를 안 만들어도 라벨이 뜨도록.)
    service_tier = (os.environ.get("GEMINI_SERVICE_TIER") or "").strip()
    if not service_tier:
        try:
            tv = getattr(response.usage_metadata, "service_tier", None)
            if tv and str(tv).lower() != "none":
                service_tier = str(tv).capitalize()
        except Exception:  # noqa: BLE001
            pass
    service_tier = service_tier or "Free"
    print(f"[diag] requested={model} used={used_model} resolved={resolved_model} tier={service_tier}", file=sys.stderr)

    # 그라운딩 출처와, 근거 문장 끝에 [N] 을 삽입한 '근거 초안'을 만든다.
    # (그라운딩 supports 의 바이트 오프셋은 원본 response.text 기준이므로 전처리 전에 적용.)
    sources = get_grounding_sources(response)
    grounded_draft = insert_grounding_citations(response.text or text, response)

    # ── 하이브리드 2패스(선택) ─────────────────────────────────────────────
    # GEMINI_WRITER_MODEL 이 설정되면, 위에서 수집한 그라운딩 근거를 3.x 모델에 넘겨
    # 그라운딩 없이 최종 검토문을 재작성한다(무료 티어 3.x 품질 + 출처 링크 동시 확보).
    # 최종 패스가 실패하면 hybrid_text=None → 아래에서 1차(그라운딩) 결과를 그대로 쓴다.
    final_models = build_final_model_chain()
    hybrid_text: str | None = None
    final_used = ""
    if final_models:
        hybrid_text, final_used = run_final_pass(
            client, types, final_models, system_prompt, user_prompt, grounded_draft, sources
        )
        if hybrid_text:
            print(f"[diag] hybrid final pass used={final_used}", file=sys.stderr)
        else:
            print("[diag] hybrid final pass 전 모델 실패 → 1차(그라운딩) 결과 사용", file=sys.stderr)

    # 검토 결과 최상단 정보 박스 — 한눈에 읽히도록 '무엇을/무슨 모델로/어느 티어' 를
    # 아이콘+라벨로 한 줄씩 분리해 블록쿼트로 감싼다. (역할이 헷갈리지 않게 명시)
    ground_model = resolved_model or used_model
    hdr: list[str] = []
    if final_used:
        # 하이브리드 2패스: 근거 수집(그라운딩) 모델과 최종 작성 모델을 역할별로 분리 표기.
        hdr.append("🤖 **검토 모델** — 하이브리드 2패스")
        hdr.append(f"&nbsp;&nbsp;🔎 근거 수집 (웹검색 그라운딩) &nbsp;`{ground_model}`")
        hdr.append(f"&nbsp;&nbsp;✍️ 최종 작성 (그라운딩 없음) &nbsp;`{final_used}`")
    else:
        hdr.append(f"🤖 **검토 모델** &nbsp;`{ground_model}`")
    # 요청 모델이 폴백된 경우에만 사유를 작게 한 줄(평소엔 노출 안 함).
    if used_model != model and requested_fail_reason:
        hdr.append(
            f"<sub>⚠️ 요청 `{model}` → 폴백({requested_fail_reason}), 실제 사용 `{used_model}`</sub>"
        )
    hdr.append(f"🏷️ **서비스 티어** &nbsp;`{service_tier}`")
    # 블록쿼트로 상단 정보 박스처럼, 각 줄 끝 두 칸으로 줄바꿈(<br>) 처리.
    model_header = "\n".join(f"> {ln}  " for ln in hdr) + "\n"

    # 최종 본문: 하이브리드가 성공했으면 그 결과를, 아니면 1차(그라운딩) 근거 초안을 쓴다.
    # (sources·grounded_draft 는 위 하이브리드 블록에서 이미 계산됨.)
    if hybrid_text is not None:
        # 최종 패스(그라운딩 없음)는 본문에 [N]/[출처 N] 만 남기므로, 확정 출처로 링크를 만든다.
        text = strip_preamble(hybrid_text)
        text = sanitize_markdown(text)
        text = linkify_citations(text, sources)          # 잔여 `cite: N` 표기(있으면)
        text = linkify_bracket_citations(text, sources)  # 맨 `[N]` → `[N](url)`
        text = link_source_refs(text, sources)           # 본문 `[출처 N]` 을 실제 출처 URL 링크로
        text, sources = unify_citations(text, sources)   # '출처' 단어 링크 → 번호 [N] 로 통일
        text = separate_adjacent_citations(text)         # 붙은 번호 인용을 콤마로 분리
        text = number_source_list(text)                  # '5. 근거 및 출처' 목록 번호 매김
        text = restructure_review(text, name)
    else:
        # 근거가 있는 문장 끝에 출처 링크([N])를 자동 삽입한다(그라운딩 supports 오프셋 기준).
        text = strip_preamble(grounded_draft)
        text = sanitize_markdown(text)
        text = linkify_citations(text, sources)  # 모델이 남긴 잔여 `cite: N` 도 링크로(있으면)
        text = link_source_refs(text, sources)   # 본문 `[출처 N]` 을 실제 출처 URL 링크로 변환
        text, sources = unify_citations(text, sources)  # '출처' 단어 링크 → 번호 [N] 로 통일
        text = separate_adjacent_citations(text)  # 붙은 번호 인용을 콤마로 분리
        text = number_source_list(text)          # '5. 근거 및 출처' 목록에 1) 2) 3) 번호 매김
        text = restructure_review(text, name)
    parts = [model_header, text]
    if sources:
        # 본문 [N] 각주와 번호가 일치하는 단일 '근거 및 출처' 목록. (모델이 쓴 동명 섹션은
        # restructure_review 에서 생략 — 번호 체계가 달라 중복·혼란을 유발하므로.)
        parts.append(
            f"\n<details>\n<summary><b>📚 근거 및 출처 — {len(sources)}건</b></summary>\n\n"
            "본문 문장 끝의 `[N]` 링크가 아래 같은 번호의 출처로 연결됩니다 "
            "(Google 검색 그라운딩 + 모델이 인용한 공식 자료).\n\n"
            + render_sources(sources)
            + "\n\n</details>"
        )
    if truncated:
        parts.append(
            "\n> ⚠️ 모델 출력이 토큰 한도로 중간에 잘렸을 수 있습니다. "
            "`rerun-review` 라벨로 재검토하거나 입력 범위를 좁혀 다시 시도하세요."
        )
    if final_used:
        gen_note = (
            f"근거 수집: <code>{resolved_model}</code>+Google Search grounding → "
            f"최종 작성: <code>{final_used}</code>(그라운딩 없음, 하이브리드 2패스)"
        )
    else:
        gen_note = f"model: <code>{resolved_model}</code>, Google Search grounding"
    parts.append(
        "\n---\n"
        f"<sub>🤖 자동 생성 ({gen_note}) · "
        "본 검토는 회사 내부 사전 리스크 검토용 참고 자료이며 법률 자문을 대체하지 않습니다.</sub>"
    )
    return enforce_length_limit("\n".join(parts))


def classify_failure(exc: Exception) -> str:
    """실패 오류를 원인 카테고리별로 분류해 정확한 조치 안내 문구를 반환.

    503(일시 과부하)에 '키/쿼터를 확인하라'고 안내하던 기존 catch-all 오진을 없앤다.
    상태 코드는 원인 카테고리가 서로 다르므로(503≠429≠401), 실제 원인에 맞는 안내만 남긴다.
    """
    code = getattr(exc, "code", None)
    msg = str(exc).lower()

    if is_transient(exc):
        return (
            "**원인: Gemini 서버의 일시적 과부하(503/500).** API 키·쿼터 문제가 아니라 "
            "구글 측 일시 장애로, 자동 재시도와 폴백 모델까지 모두 소진된 상태입니다. "
            "보통 몇 분 뒤 회복되므로 잠시 후 `rerun-review` 라벨로 재시도하세요. "
            "지속되면 [Google Cloud/AI 상태 페이지](https://status.cloud.google.com/)를 확인하거나, "
            "저장소 변수 `GEMINI_DEFAULT_MODEL`/`GEMINI_DEFAULT_FALLBACKS` 를 안정 버전(GA) 모델로 바꿔 보세요."
        )
    if code in (401, 403) or any(
        m in msg for m in ("unauthenticated", "permission_denied", "api key", "api_key_invalid")
    ):
        return (
            "**원인: 인증/권한 오류(401/403).** `GEMINI_API_KEY` Secret 이 없거나 잘못됐거나 "
            "권한이 없습니다. 저장소 Settings → Secrets → Actions 에서 키를 재확인·재발급한 뒤 "
            "`rerun-review` 라벨로 재시도하세요."
        )
    if code == 429 or any(m in msg for m in ("resource_exhausted", "quota", "rate limit")):
        return (
            "**원인: 쿼터/레이트리밋 초과(429).** 폴백 모델들의 무료 일일 쿼터까지 모두 "
            "소진됐을 수 있습니다. 쿼터가 회복되는 다음 날 재시도하거나, 유료 티어/다른 키로 "
            "전환한 뒤 `rerun-review` 라벨로 재시도하세요."
        )
    return (
        "관리자에게 문의하거나, 저장소 설정(GEMINI_API_KEY Secret, API 쿼터)을 확인 후 "
        "`rerun-review` 라벨을 추가해 재시도하세요."
    )


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
            + classify_failure(exc)
        )
        output_path.write_text(result, encoding="utf-8")
        print(result, file=sys.stderr)
        return 1

    output_path.write_text(result, encoding="utf-8")
    print(f"검토 결과를 {output_path} 에 저장했습니다 ({len(result)} chars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
