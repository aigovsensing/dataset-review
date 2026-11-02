#!/usr/bin/env python3
"""검토 결과(GitHub 이슈 댓글 Markdown)를 '어디서나 렌더링되는 순수 Markdown' 으로 변환.

GitHub 은 Markdown 안의 일부 HTML(<details>/<summary>/<sub>/<code>/<b>/<br>/<img>, &nbsp;)
을 허용하지만, 많은 일반 Markdown 렌더러(위키·블로그·노트 앱 등)는 보안상 원시 HTML 을
막아 태그가 글자 그대로 보인다. 또 복사·붙여넣기 과정에서 따옴표가 “ ” 로 바뀌면 HTML
속성이 깨져 HTML 을 허용하는 렌더러에서도 해석되지 않는다.

이 모듈은 검토 결과에 쓰이는 HTML 을 같은 의미의 순수 Markdown 으로 바꾼다.
  <img src=… alt=…>            → ![alt](src)
  <details><summary>제목</summary> … </details>  → ### 제목 (본문은 그대로, 접기만 사라짐)
  <sub>…</sub>                 → *…*
  <code>…</code>               → `…`
  <b>/<strong>, <i>/<em>       → **…**, *…*
  <br>                         → 줄바꿈(인용문 안이면 '>' 접두어 유지)
  &nbsp;                       → 공백

사용법
  python scripts/portable_markdown.py review.md            > portable.md
  python scripts/portable_markdown.py -  < review.md       > portable.md
  python scripts/portable_markdown.py --issue 350          > 350.md   # 최신 검토 댓글을 받아 변환
  (비공개 저장소이거나 호출이 많으면 GITHUB_TOKEN / GH_TOKEN 환경변수를 설정)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

DEFAULT_REPO = os.environ.get("GITHUB_REPOSITORY") or "aigovsensing/dataset-review"
# 검토 결과 댓글 식별 문자열(데이터셋 검토·논문 검토 공통으로 포함되는 문구).
REVIEW_MARKERS = ("법적 리스크 검토 결과", "법무 검토 결과", "검토 결과")
START_NOTICE = "검토를 시작합니다"

_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "″": '"', "‘": "'", "’": "'", "′": "'"})
_TAG_RE = re.compile(r"<[^<>\n]+>")
_ATTR_RE = re.compile(r'([a-zA-Z-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_IMG_RE = re.compile(r"<img\b[^>]*?/?>", re.I)
_DETAILS_TOKEN_RE = re.compile(
    r"<details\b[^>]*>\s*(?:<summary\b[^>]*>(?P<summary>.*?)</summary>)?|</details\s*>", re.I | re.S
)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.I | re.S)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_QUOTE_PREFIX_RE = re.compile(r"^(\s*(?:>\s*)+)")


def _normalize_tag_quotes(text: str) -> str:
    """HTML 태그 안의 둥근 따옴표(“ ” ‘ ’)만 곧은 따옴표로 되돌린다(본문 문장은 건드리지 않음)."""
    return _TAG_RE.sub(lambda m: m.group(0).translate(_SMART_QUOTES), text)


def _attrs(tag: str) -> dict[str, str]:
    return {k.lower(): (a if a is not None else b if b is not None else c)
            for k, a, b, c in _ATTR_RE.findall(tag)}


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _img_to_md(m: re.Match) -> str:
    at = _attrs(m.group(0))
    src = at.get("src", "").strip()
    if not src:
        return ""
    alt = at.get("alt", "").strip().replace("[", "(").replace("]", ")")
    return f"![{alt}]({src})"


def _convert_details(text: str) -> str:
    """<details><summary>제목</summary> 를 중첩 깊이에 맞춘 제목(### / ####)으로 바꾼다."""
    out: list[str] = []
    depth = 0
    pos = 0
    for m in _DETAILS_TOKEN_RE.finditer(text):
        out.append(text[pos:m.start()])
        pos = m.end()
        if m.group(0).lower().startswith("</details"):
            depth = max(0, depth - 1)
            out.append("\n")
            continue
        summary = m.group("summary")
        level = min(3 + depth, 6)
        depth += 1
        if summary is not None:
            title = re.sub(r"\s+", " ", _strip_tags(summary)).strip()
            if title:
                out.append(f"\n\n{'#' * level} {title}\n\n")
    out.append(text[pos:])
    # <details> 없이 단독으로 남은 <summary> 도 굵은 글씨로.
    return _SUMMARY_RE.sub(lambda m: f"**{_strip_tags(m.group(1)).strip()}**", "".join(out))


def _inline(text: str) -> str:
    def code(m: re.Match) -> str:
        inner = _strip_tags(m.group(1))
        fence = "``" if "`" in inner else "`"
        pad = " " if fence == "``" else ""
        return f"{fence}{pad}{inner}{pad}{fence}"

    def wrap(mark: str):
        def _w(m: re.Match) -> str:
            inner = m.group(1).strip()
            return f"{mark}{inner}{mark}" if inner else ""
        return _w

    text = re.sub(r"<code\b[^>]*>(.*?)</code>", code, text, flags=re.I | re.S)
    text = re.sub(r"<(?:b|strong)\b[^>]*>(.*?)</(?:b|strong)>", wrap("**"), text, flags=re.I | re.S)
    text = re.sub(r"<(?:i|em)\b[^>]*>(.*?)</(?:i|em)>", wrap("*"), text, flags=re.I | re.S)
    text = re.sub(r"<(?:sub|sup|small)\b[^>]*>(.*?)</(?:sub|sup|small)>", wrap("*"), text, flags=re.I | re.S)
    return text


def _convert_br(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        if _BR_RE.search(line):
            m = _QUOTE_PREFIX_RE.match(line)
            prefix = m.group(1).rstrip() + " " if m else ""
            parts = [p.strip() for p in _BR_RE.split(line)]
            first = parts[0]
            rest = [prefix + p for p in parts[1:] if p]
            line = "  \n".join([first] + rest) if rest else first
        lines.append(line)
    return "\n".join(lines)


def to_portable_markdown(md: str) -> str:
    """GitHub 전용 HTML 을 걷어낸 순수 Markdown 문자열을 반환한다."""
    text = md.replace("\r\n", "\n")
    text = _normalize_tag_quotes(text)
    text = _IMG_RE.sub(_img_to_md, text)
    text = _convert_details(text)
    text = _inline(text)
    text = _convert_br(text)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    text = re.sub(r"[ \t]+\n", lambda m: "  \n" if m.group(0).startswith("  ") else "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def fetch_latest_review(issue: int, repo: str = DEFAULT_REPO) -> str:
    """이슈의 가장 최근 '검토 결과' 댓글 본문을 GitHub REST API 로 가져온다."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "portable-markdown"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = ""
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/issues/{issue}/comments?per_page=100&page={page}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            items = json.load(r)
        for c in items:
            b = c.get("body") or ""
            if START_NOTICE not in b and any(k in b for k in REVIEW_MARKERS):
                body = b  # 마지막(최신) 검토 결과를 사용
        if len(items) < 100:
            break
        page += 1
    if not body:
        raise SystemExit(f"#{issue} 에서 검토 결과 댓글을 찾지 못했습니다.")
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="검토 결과 Markdown → 순수(포터블) Markdown 변환")
    ap.add_argument("input", nargs="?", default="-", help="입력 파일 경로(기본 '-' = 표준입력)")
    ap.add_argument("--issue", type=int, help="이 이슈 번호의 최신 검토 결과 댓글을 받아 변환")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"저장소(기본 {DEFAULT_REPO})")
    ap.add_argument("-o", "--output", help="출력 파일(기본 표준출력)")
    args = ap.parse_args(argv)

    if args.issue:
        src = fetch_latest_review(args.issue, args.repo)
    elif args.input == "-":
        src = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as fh:
            src = fh.read()
    out = to_portable_markdown(src)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
