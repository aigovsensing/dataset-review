#!/usr/bin/env python3
"""논문 법무 검토 결과(GitHub 이슈)를 CSV/JSON 으로 내보낸다 (논문 대시보드용).

`paper-review` 라벨이 붙은 이슈들을 모아, 각 이슈의 최신 검토 댓글(## 종합의견 포함)에서
구조화 필드(실험논문 여부·데이터 유형·개인정보·저작권·요약 등)를 파싱해
docs/data/papers.csv 와 docs/data/papers.json 을 생성한다.

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
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"

CSV_FIELDS = [
    "issue", "title", "status",
    "experiment", "data_type", "privacy", "copyright", "summary",
    "model", "author", "created_at", "updated_at", "url", "state", "comments",
]

_MODEL_RE = re.compile(r"모델 정보:\*\*\s*`([^`]+)`")


def gh_get(url: str, token: str, attempts: int = 4):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "paper-review-export",
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


def list_paper_issues(repo: str, token: str) -> list[dict]:
    issues: list[dict] = []
    page = 1
    while True:
        url = (
            f"{API}/repos/{repo}/issues?labels=paper-review&state=all"
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


def latest_result_comment(repo: str, number: int, token: str) -> str:
    """결과 댓글(‘종합의견’ 포함) 중 최신 것을 반환. '검토 시작' 안내 댓글은 제외."""
    comments = gh_get(f"{API}/repos/{repo}/issues/{number}/comments?per_page=100", token)
    body = ""
    for c in comments:
        b = c.get("body") or ""
        if "종합의견" in b:
            body = b  # 마지막(최신) 결과 댓글 사용
    return body


def status_from_labels(labels: list[str]) -> str:
    for name in ("review-failed", "reviewed", "reviewing"):
        if name in labels:
            return name
    return "pending"


def _field(body: str, key_regex: str) -> str:
    """'key : value'(또는 '**key:** value' / '**key: value**') 형태에서 값만 추출."""
    m = re.search(rf"{key_regex}\s*[:：]\s*(.+)", body)
    if not m:
        return ""
    val = m.group(1)
    val = val.replace("**", "")
    val = re.sub(r"\s*\[\d+\]\((?:https?:)?//[^)]*\)", "", val)  # 자동 각주 제거
    val = re.sub(r"\s*\(\[출처\][^)]*\)", "", val)
    return val.strip().strip(".·-  ")


def norm_experiment(s: str) -> str:
    s = (s or "").strip()
    if "예" in s and "아니오" not in s:
        return "예"
    if "아니오" in s:
        return "아니오"
    return "확인 불가"


def norm_data_type(s: str) -> str:
    s = (s or "")
    if "혼합" in s:
        return "혼합"
    if "외부" in s or "AI Dataset" in s:
        return "외부 Dataset"
    if "자체" in s or "생성" in s:
        return "자체 생성"
    if "미사용" in s or "없음" in s or "미포함" in s:
        return "미사용"
    return "확인 불가"


def norm_privacy(s: str) -> str:
    s = (s or "")
    if "미포함" in s or "없" in s:
        return "미포함"
    if "포함" in s:
        return "포함"
    return "확인 불가"


def norm_copyright(s: str) -> str:
    s = (s or "")
    if "문제없" in s or "문제 없" in s:
        return "문제없음"
    if "검토 필요" in s or "필요" in s:
        return "검토 필요"
    return "확인 불가"


def parse_paper(body: str) -> dict:
    """검토 댓글 본문(종합의견)에서 논문 대시보드용 필드 추출."""
    data = {k: "" for k in ("experiment", "data_type", "privacy", "copyright", "summary", "model")}
    if not body:
        return data
    m = _MODEL_RE.search(body)
    if m:
        data["model"] = m.group(1).strip()

    exp = _field(body, r"실험\s*데이터셋\s*사용\s*논문\s*여부")
    # 결론 섹션의 'Dataset을 이용한 실험 논문인가?'도 보조 근거로 사용
    if not exp:
        exp = _field(body, r"Dataset[^:：\n]*실험\s*논문인가")
    data["experiment"] = norm_experiment(exp)
    data["data_type"] = norm_data_type(_field(body, r"데이터\s*유형"))
    data["privacy"] = norm_privacy(_field(body, r"개인정보"))
    data["copyright"] = norm_copyright(_field(body, r"저작권"))
    data["summary"] = _field(body, r"한\s*줄\s*요약")
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

    issues = list_paper_issues(repo, token)
    rows: list[dict] = []
    for it in issues:
        num = it["number"]
        labels = [l["name"] for l in it.get("labels", [])]
        body = latest_result_comment(repo, num, token)
        parsed = parse_paper(body)
        title = re.sub(r"^\s*\[논문검토\]\s*", "", it.get("title", "")).strip()
        rows.append({
            "issue": num,
            "title": title,
            "status": status_from_labels(labels),
            "experiment": parsed["experiment"] if body else "",
            "data_type": parsed["data_type"] if body else "",
            "privacy": parsed["privacy"] if body else "",
            "copyright": parsed["copyright"] if body else "",
            "summary": parsed["summary"],
            "model": parsed["model"],
            "author": (it.get("user") or {}).get("login", ""),
            "created_at": it.get("created_at", ""),
            "updated_at": it.get("updated_at", ""),
            "url": it.get("html_url", ""),
            "state": it.get("state", ""),
            "comments": it.get("comments", 0),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "papers.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rows": rows,
    }
    (OUT_DIR / "papers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"논문 내보내기 완료: {len(rows)}건 → {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
