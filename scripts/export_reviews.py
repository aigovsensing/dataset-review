#!/usr/bin/env python3
"""검토 결과(GitHub 이슈)를 CSV/JSON 으로 내보낸다 (대시보드·집계용).

`dataset-review` 라벨이 붙은 이슈들을 모아, 각 이슈의 최신 검토 댓글에서 구조화된
필드(데이터셋·판정·모델·라이선스·수집방식·개인정보·소송 여부 등)를 파싱해
docs/data/reviews.csv 와 docs/data/reviews.json 을 생성한다.

환경 변수
----------
GITHUB_TOKEN        : (필수) GitHub API 토큰 (Actions 의 secrets.GITHUB_TOKEN)
GITHUB_REPOSITORY   : (선택) "owner/repo". 미지정 시 --repo 인자 사용
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
REVIEW_MARKER = "오픈 데이터셋 법적 리스크 검토 결과"  # 검토 결과 댓글 식별용
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"

CSV_FIELDS = [
    "issue", "dataset", "verdict", "model", "status",
    "review_confidence",
    "license_check", "license_judgment", "license_basis",
    "collection_check", "collection_judgment", "collection_basis",
    "privacy_check", "privacy_judgment", "privacy_basis",
    "litigation", "author", "created_at", "updated_at", "url",
    "state", "comments",
]

CONFIDENCE_LABELS = {
    "ai-review-confidence-high": "high",
    "ai-review-confidence-medium": "medium",
    "ai-review-confidence-low": "low",
}

_VERDICT_RE = re.compile(r"(사용 가능|추가 검토 필요|사용 비권고)")
_MODEL_RE = re.compile(r"모델 정보:\*\*\s*`([^`]+)`")
_DATASET_RE = re.compile(r"대상 데이터셋\*\*\s*&nbsp;\s*`([^`]+)`")
# '1. 요약 결론' 항목 불릿: "- **라벨** — 확인 결과: … / 내부 판단: … / 판단 근거: …"
# 들여쓰기 허용, 구분자는 em/en 대시만(하이픈 제외 — 다음 불릿의 '-' 를 삼키지 않도록),
# 대시 주변은 [ \t] 로 제한(줄바꿈을 넘지 않도록).
_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+\*\*(.+?)\*\*[ \t]*[—–][ \t]*(.+)$", re.MULTILINE)


def _field(rest: str, key: str, stop: str | None) -> str:
    if stop:
        m = re.search(rf"{key}\s*[:：]\s*(.+?)(?:\s*[/—–]\s*(?:{stop})\s*[:：]|$)", rest)
    else:
        m = re.search(rf"{key}\s*[:：]\s*(.+)$", rest)
    return m.group(1).strip() if m else ""


def gh_get(url: str, token: str, attempts: int = 4):
    import time
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "dataset-review-export",
        },
    )
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - 고정 api.github.com
                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001 - 일시적 네트워크 오류 재시도
            last = exc
            if i < attempts - 1:
                time.sleep(2 * (i + 1))
    raise last


def list_review_issues(repo: str, token: str) -> list[dict]:
    issues: list[dict] = []
    page = 1
    while True:
        url = (
            f"{API}/repos/{repo}/issues?labels=dataset-review&state=all"
            f"&per_page=100&page={page}&sort=created&direction=desc"
        )
        batch = gh_get(url, token)
        if not batch:
            break
        issues += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
        page += 1
    return issues


def latest_review_comment(repo: str, number: int, token: str) -> str:
    comments = gh_get(f"{API}/repos/{repo}/issues/{number}/comments?per_page=100", token)
    body = ""
    for c in comments:
        if REVIEW_MARKER in (c.get("body") or ""):
            body = c["body"]  # 마지막(최신) 검토 댓글을 사용
    return body


def clean(cell: str) -> str:
    """표 셀 정리: 굵게/이스케이프 제거."""
    cell = cell.replace("\\|", "|").replace("**", "").strip()
    return "" if cell in ("—", "-") else cell


def status_from_labels(labels: list[str]) -> str:
    for name in ("review-failed", "reviewed", "reviewing"):
        if name in labels:
            return name
    return "pending"


def confidence_from_labels(labels: list[str]) -> str:
    """이슈의 AI 자동리뷰 만족도 레이블을 정규화한다."""
    for label, value in CONFIDENCE_LABELS.items():
        if label in labels:
            return value
    return ""


def parse_review(body: str) -> dict:
    """검토 댓글 본문에서 구조화 필드 추출."""
    data = {k: "" for k in (
        "verdict", "model", "dataset",
        "license_check", "license_judgment", "license_basis",
        "collection_check", "collection_judgment", "collection_basis",
        "privacy_check", "privacy_judgment", "privacy_basis", "litigation",
    )}
    if not body:
        return data

    m = _MODEL_RE.search(body)
    if m:
        data["model"] = m.group(1).strip()
    m = _DATASET_RE.search(body)
    if m:
        data["dataset"] = m.group(1).strip()
    m = _VERDICT_RE.search(body)  # 첫 등장(배너)이 최종 판정
    if m:
        data["verdict"] = m.group(1)

    def key_of(label: str) -> str | None:
        if "라이선스" in label:
            return "license"
        if "수집" in label or "생성" in label:
            return "collection"
        if "개인정보" in label:
            return "privacy"
        return None

    # (1) 불릿 형식: "- **라벨** — 확인 결과: … / 내부 판단: … / 판단 근거: …"
    for label, rest in _BULLET_RE.findall(body):
        key = key_of(label.strip())
        if not key or data[f"{key}_check"]:
            continue
        data[f"{key}_check"] = clean(_field(rest, r"확인\s*결과", r"내부\s*판단|판단\s*근거") or rest)
        data[f"{key}_judgment"] = clean(_field(rest, r"내부\s*판단", r"판단\s*근거"))
        data[f"{key}_basis"] = clean(_field(rest, r"판단\s*근거", None))

    # (2) 표 형식(구버전 요약 결론/종합의견 표): | 라벨 | 확인 결과 | 내부 판단 | 근거 |
    #     불릿에서 못 채운 항목만 보완. 셀은 파이프로 안전하게 분리한다.
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        label = cells[0].replace("**", "").strip()
        if "내부 검토 결과" in label or re.match(r"^:?-{2,}:?$", cells[1]):
            continue  # 판정 행/구분선 제외
        key = key_of(label)
        if not key or data[f"{key}_check"]:
            continue
        data[f"{key}_check"] = clean(cells[1])
        data[f"{key}_judgment"] = clean(cells[2])
        if len(cells) >= 4:
            data[f"{key}_basis"] = clean(cells[3])

    # 소송: 소송 근거 강도(강/중/약) 표기가 있으면 '있음', 아니면 '해당 없음'
    data["litigation"] = "있음" if "근거 강도" in body else "해당 없음"
    return data


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    args = sys.argv[1:]
    if not repo and args:
        repo = args[0]
    if not token or not repo:
        print("GITHUB_TOKEN 과 GITHUB_REPOSITORY(또는 인자로 owner/repo) 가 필요합니다.", file=sys.stderr)
        return 2

    issues = list_review_issues(repo, token)
    rows: list[dict] = []
    for it in issues:
        num = it["number"]
        labels = [l["name"] for l in it.get("labels", [])]
        body = latest_review_comment(repo, num, token)
        parsed = parse_review(body)
        title = it.get("title", "")
        dataset = parsed["dataset"] or re.sub(r"^\s*\[검토\]\s*", "", title).strip()
        rows.append({
            "issue": num,
            "dataset": dataset,
            "verdict": parsed["verdict"],
            "model": parsed["model"],
            "status": status_from_labels(labels),
            "review_confidence": confidence_from_labels(labels),
            "license_check": parsed["license_check"],
            "license_judgment": parsed["license_judgment"],
            "license_basis": parsed["license_basis"],
            "collection_check": parsed["collection_check"],
            "collection_judgment": parsed["collection_judgment"],
            "collection_basis": parsed["collection_basis"],
            "privacy_check": parsed["privacy_check"],
            "privacy_judgment": parsed["privacy_judgment"],
            "privacy_basis": parsed["privacy_basis"],
            "litigation": parsed["litigation"] if body else "",
            "author": (it.get("user") or {}).get("login", ""),
            "created_at": it.get("created_at", ""),
            "updated_at": it.get("updated_at", ""),
            "url": it.get("html_url", ""),
            "state": it.get("state", ""),
            "comments": it.get("comments", 0),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "reviews.csv"
    # Excel 한글 호환을 위해 UTF-8 BOM
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rows": rows,
    }
    (OUT_DIR / "reviews.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"내보내기 완료: {len(rows)}건 → {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
