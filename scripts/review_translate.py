#!/usr/bin/env python3
"""영어 요청 지원: 이슈 언어 판별 · 검토 결과의 영어 번역 · 영어+한국어 원문 합성.

동작 방식
---------
검토 엔진(dataset_review.py / paper_review.py)은 **한국어 정본**을 만든다. 시스템 프롬프트·섹션 번호·
판정 어휘('사용 가능' 등)가 한국어에 묶여 있고, 대시보드/CSV 집계(export_*.py)도 그 한국어 형식을 파싱하기 때문이다.
영어로 요청된 이슈(영어 이슈 양식으로 생성)에는 정본을 영어로 번역(그라운딩 없는 1회 호출)해 **영어 본문을 위에**
두고, **한국어 원문을 접힌 <details> 안에** 그대로 함께 게시한다. 그러면 영어 사용자는 영어로 읽고, 집계 코드는
한국어 원문을 그대로 읽는다(검증: tests/test_review_translate.py).

번역이 실패하거나 검증(URL·구조 보존)을 통과하지 못하면 한국어 정본만 게시하고 영어 안내 한 줄을 덧붙인다.
"""
from __future__ import annotations

import os
import re
import sys

# 영어 이슈 양식(.github/ISSUE_TEMPLATE/*-en.yml)이 만드는 '### 라벨' 제목들. 하나라도 있으면 영어 요청이다.
EN_HEADINGS = {
    "Dataset name",
    "Description",
    "Dataset repository URL",
    "Related / source datasets",
    "Paper URL",
    "Source code repository URL",
    "Related lawsuit (CourtListener URL)",
    "Select system prompt",
    "Paper title",
    "Paper PDF / website URL",
}

# 영어 이슈 양식 라벨 → 내부 필드 키 (dataset_review.FIELD_LABELS / paper_review.PAPER_FIELD_LABELS 에 병합)
EN_DATASET_FIELD_LABELS = {
    "Dataset name": "dataset_name",
    "Related / source datasets": "related_datasets",
    "Paper URL": "paper_urls",
    "Dataset repository URL": "dataset_repo_url",
    "Source code repository URL": "code_repo_url",
    "Related lawsuit (CourtListener URL)": "litigation_url",
    "Description": "extra_notes",
    "Select system prompt": "system_prompt",
}
EN_PAPER_FIELD_LABELS = {
    "Paper title": "paper_title",
    "Paper PDF / website URL": "paper_url",
    "Description": "extra_notes",
}

TRANSLATE_SYSTEM_PROMPT = """You are a precise Korean-to-English translator for legal-risk review reports.
Translate the Korean Markdown document the user sends into natural, professional English.

Rules:
1. Output ONLY the translated Markdown. No preface, no explanation, and do not wrap the whole document in a code fence.
2. Preserve the document structure exactly: headings (#, ##, ###), tables (same columns and rows), lists, blockquotes (>),
   horizontal rules, and the HTML tags <details>, <summary>, <sub>, <code>, <b>, <br> and &nbsp;, plus every emoji.
3. Never change, translate or drop: URLs and link targets, citation markers such as [1] or [3](https://...), numbers,
   version strings, license names/identifiers (e.g. CC BY 4.0, AGPL-3.0), dataset/model/company/person names, file names,
   and text inside backticks.
4. Translate link text and all other prose. Keep quotations from source documents that are already in English as they are.
5. Use these fixed terms: 확인 불가 -> "Unable to verify"; 사용 가능 -> "Usable"; 추가 검토 필요 -> "Needs further review";
   사용 비권고 -> "Not recommended"; 리스크 낮음 -> "Low risk"; 리스크 있음 -> "Risk present"; 주의 -> "Caution";
   해당 없음 -> "Not applicable"; 똘똘이 비글 -> "Smarty Beagle".
6. This is a faithful translation: do not add, remove, summarize or reinterpret content.
"""

# URL 은 ASCII 문자만 인정한다: 한국어 조사가 바로 붙은 `https://x.com/a를` 에서 한글까지 URL 로 잡으면,
# 정상 번역(조사 제거)이 'URL 누락'으로 오판된다. 괄호·따옴표·꺾쇠는 URL 끝으로 본다.
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%]+")
HANGUL_RE = re.compile(r"[가-힣]")
LETTER_RE = re.compile(r"[A-Za-z가-힣]")


def detect_language(body: str) -> str:
    """이슈 본문이 영어 이슈 양식으로 만들어졌으면 'en', 아니면 'ko'. REVIEW_LANG=en|ko 로 강제할 수 있다."""
    forced = (os.environ.get("REVIEW_LANG") or "").strip().lower()
    if forced in ("en", "ko"):
        return forced
    for m in re.finditer(r"^###\s+(.+?)\s*$", body or "", flags=re.MULTILINE):
        if m.group(1) in EN_HEADINGS:
            return "en"
    return "ko"


def _urls(text: str) -> set[str]:
    return {u.rstrip(".,;:") for u in URL_RE.findall(text)}


def validate_translation(ko: str, en: str) -> list[str]:
    """번역이 구조·링크를 보존했는지 점검한다. 문제 목록(비어 있으면 통과)을 반환."""
    problems: list[str] = []
    if not en or not en.strip():
        return ["빈 응답"]
    missing = sorted(u for u in _urls(ko) if u not in en)
    if missing:
        problems.append(f"URL {len(missing)}개 누락 (예: {missing[0][:80]})")
    for tag in ("<details", "</details>", "<summary>"):
        if ko.count(tag) != en.count(tag):
            problems.append(f"{tag} 개수 불일치({ko.count(tag)}→{en.count(tag)})")
    ko_rows = sum(1 for ln in ko.splitlines() if ln.lstrip().startswith("|"))
    en_rows = sum(1 for ln in en.splitlines() if ln.lstrip().startswith("|"))
    if ko_rows and en_rows < ko_rows * 0.8:
        problems.append(f"표 행 소실({ko_rows}→{en_rows})")
    letters = LETTER_RE.findall(en)
    if letters and len(HANGUL_RE.findall(en)) / len(letters) > 0.2:
        problems.append("한글 비율이 높음(번역되지 않음)")
    ratio = len(en) / max(len(ko), 1)
    if not 0.4 <= ratio <= 3.5:
        problems.append(f"길이 비율 비정상({ratio:.2f})")
    return problems


def _call_model(api_key: str, model: str, markdown: str) -> str:
    """그라운딩 없이 번역 1회 호출. (테스트에서 이 함수를 대체한다.)"""
    import dataset_review as R  # 순환 import 를 피하려고 지연 import
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    base = dict(system_instruction=TRANSLATE_SYSTEM_PROMPT, temperature=0.1, max_output_tokens=32768)
    try:
        cfg = types.GenerateContentConfig(**base, thinking_config=types.ThinkingConfig(thinking_budget=512))
    except Exception:  # noqa: BLE001 - 구버전 SDK 호환
        cfg = types.GenerateContentConfig(**base)
    resp = R.generate_with_retry(client, model, markdown, cfg)
    return (resp.text or "").strip()


def _strip_code_fence(text: str) -> str:
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", text.strip(), flags=re.S)
    return m.group(1).strip() if m else text.strip()


def translate_to_english(markdown: str, api_keys: list[tuple[str, str]]) -> tuple[str | None, str]:
    """한국어 검토 Markdown 을 영어로 번역. (번역문 또는 None, 사용 모델)을 반환한다.

    키 순서대로, 각 키에서 PLAIN 모델 체인을 순서대로 시도한다. 검증을 통과한 첫 결과를 채택한다.
    """
    import dataset_review as R

    for var_name, key in api_keys:
        for model in R.build_ungrounded_model_chain():
            try:
                en = _strip_code_fence(_call_model(key, model, markdown))
            except Exception as exc:  # noqa: BLE001 - 다음 모델/키로
                print(f"[diag] translate {var_name}/{model} 실패: {R.safe_exception_text(exc, key)[:160]}",
                      file=sys.stderr)
                if not R.should_rotate_api_key(exc) and not R.is_fallbackable(exc):
                    break
                continue
            problems = validate_translation(markdown, en)
            if problems:
                print(f"[diag] translate {model} 검증 실패 → 다음 모델: {'; '.join(problems)}", file=sys.stderr)
                continue
            print(f"[diag] translate ok model={model} chars={len(en)}", file=sys.stderr)
            return en, model
    return None, ""


KO_DETAILS_SUMMARY = (
    "🇰🇷 <b>한국어 원문 (Korean original)</b> — 대시보드·CSV 집계에 사용됩니다 · used for the dashboard & CSV export"
)


def compose_bilingual(en: str, ko: str, limit: int = 64000) -> str:
    """영어 본문 + 접힌 한국어 원문. 전체가 댓글 길이 제한을 넘으면 한국어 원문을 줄인다."""
    head = en.rstrip() + "\n\n---\n\n"
    open_tag = f"<details>\n<summary>{KO_DETAILS_SUMMARY}</summary>\n\n"
    close_tag = "\n\n</details>\n"
    budget = limit - len(head) - len(open_tag) - len(close_tag)
    ko_part = ko.strip()
    if len(ko_part) > budget:
        ko_part = ko_part[: max(budget - 80, 0)].rstrip() + "\n\n> ⚠️ 길이 제한으로 이후 내용이 생략되었습니다 (truncated)."
    return head + open_tag + ko_part + close_tag


def english_unavailable_notice() -> str:
    return (
        "> ℹ️ **English translation was unavailable this time**, so the original Korean review is shown below. "
        "Add the `rerun-review` label to retry.\n\n"
    )


def key_rotation_note_en(failed_names: list[str], active_name: str = "") -> str:
    """영어판 API 키 전환 내역(이름만 표기, 값은 절대 표시하지 않음)."""
    if not failed_names:
        return ""
    failed = ", ".join(f"`{n}`" for n in failed_names)
    outcome = f", then switched to `{active_name}` successfully." if active_name else ": all attempts failed."
    return f"\n\n> 🔑 **Gemini API key rotation:** {failed}{outcome} Secret values are never shown."


def english_failure_notice(exc: Exception) -> str:
    """실패 댓글의 영어 요약(원인 범주별). 상세 오류와 한국어 안내는 그 아래에 그대로 둔다."""
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    if code in (401, 403) or any(m in msg for m in ("unauthenticated", "permission_denied", "api key not valid")):
        cause = "**Cause: authentication/permission error (401/403).** The `GEMINI_API_KEY` secret is missing, wrong or lacks permission."
    elif code == 429 or any(m in msg for m in ("resource_exhausted", "quota", "rate limit")):
        cause = ("**Cause: quota / rate limit exceeded (429).** The free daily quota of every configured API key is used up. "
                 "Retry after the quota resets, or switch to a paid tier / another key.")
    elif code in (500, 502, 503, 504) or "unavailable" in msg:
        cause = "**Cause: temporary Google server overload (503/500).** Please retry in a few minutes."
    else:
        cause = "**Cause: unexpected error.** See the details below or ask the maintainer."
    return (
        "## ⚠️ Automated legal-risk review failed\n\n"
        f"{cause}\n\n"
        "After fixing the cause, add the `rerun-review` label to this issue to run the review again. "
        "(The original Korean error details follow.)\n\n---\n\n"
    )
