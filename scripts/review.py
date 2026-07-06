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
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "system_prompt.md"

# 이슈 폼(dataset-review.yml)의 라벨 → 내부 필드 키 매핑
FIELD_LABELS = {
    "데이터셋 명칭": "dataset_name",
    "관련 / 원본 데이터셋": "related_datasets",
    "논문 주소 (URL)": "paper_urls",
    "공식 홈페이지 / 저장소 URL": "homepage_url",
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


def build_user_prompt(title: str, fields: dict[str, str]) -> str:
    name = fields.get("dataset_name", "").strip()
    if not name and title:
        # 제목에서 "[검토] " 접두어 제거하여 데이터셋명 추정
        name = re.sub(r"^\s*\[검토\]\s*", "", title).strip()

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
    if fields.get("extra_notes"):
        lines.append(f"- 추가 참고 사항: {fields['extra_notes']}")
    lines += [
        "",
        "출력은 시스템 지침의 [출력 형식]을 정확히 따른다.",
    ]
    return "\n".join(lines)


def extract_grounding_sources(response) -> list[str]:
    """Gemini 응답의 그라운딩 메타데이터에서 참조 URL 목록을 추출."""
    urls: list[str] = []
    try:
        for cand in response.candidates or []:
            meta = getattr(cand, "grounding_metadata", None)
            if not meta:
                continue
            for chunk in getattr(meta, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    title = getattr(web, "title", "") or web.uri
                    entry = f"- [{title}]({web.uri})"
                    if entry not in urls:
                        urls.append(entry)
    except Exception:  # noqa: BLE001 - 그라운딩 메타데이터는 부가 정보이므로 실패해도 무시
        pass
    return urls


def run_review(title: str, body: str) -> str:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다. "
            "저장소 Settings → Secrets → Actions 에 GEMINI_API_KEY 를 등록하세요."
        )

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    fields = parse_issue_body(body)
    user_prompt = build_user_prompt(title, fields)

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.2,
    )
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini 응답이 비어 있습니다. 모델/쿼터 상태를 확인하세요.")

    sources = extract_grounding_sources(response)
    parts = [text]
    if sources:
        parts.append("\n---\n\n### 🔎 Google 검색 그라운딩 출처\n\n" + "\n".join(sources))
    parts.append(
        "\n---\n"
        f"<sub>🤖 자동 생성 (model: `{model}`, Google Search grounding). "
        "본 검토는 회사 내부 사전 리스크 검토용 참고 자료이며 법률 자문을 대체하지 않습니다.</sub>"
    )
    return "\n".join(parts)


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
