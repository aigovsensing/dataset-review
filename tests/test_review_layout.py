"""Issue-comment layout regression: the review title must come first."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dataset_review as R  # noqa: E402

SAMPLE = "## 1. 요약 결론\n내용\n## 2. 항목별 상세 분석\n상세\n"


class ReviewLayoutTest(unittest.TestCase):
    def test_hoist_moves_title_out_of_banner(self) -> None:
        body = R.restructure_review(SAMPLE, "NAB")
        title, rest = R.hoist_review_title(body)
        self.assertEqual(title.strip(), R.REVIEW_TITLE)
        self.assertNotIn(R.REVIEW_TITLE, rest)
        # 남은 본문은 대상 데이터셋 배너로 시작하고, 비글 이미지(<img>)는 더 이상 출력하지 않는다.
        self.assertTrue(rest.lstrip().startswith("> **대상 데이터셋**"))
        self.assertNotIn("<img", body)
        self.assertNotIn("beagle", body)

    def test_hoist_without_title_is_noop(self) -> None:
        self.assertEqual(R.hoist_review_title("plain text"), ("", "plain text"))

    def test_title_precedes_warning_and_model_header(self) -> None:
        title, rest = R.hoist_review_title(R.restructure_review(SAMPLE, "NAB"))
        out = "\n\n".join((title.strip(), "> ⚠️ 경고", "> 🤖 **검토 모델**", rest))
        self.assertTrue(out.startswith(R.REVIEW_TITLE))
        self.assertLess(out.index("⚠️ 경고"), out.index("검토 모델"))
        self.assertLess(out.index("검토 모델"), out.index("대상 데이터셋"))
        self.assertEqual(out.count(R.REVIEW_TITLE), 1)


class NoCollapsibleHtmlTest(unittest.TestCase):
    """<details>/<summary> 는 GitHub 이슈에서만 접히므로 검토 결과에 쓰지 않는다(표준 Markdown 헤딩 사용)."""

    FULL = (
        "## 1. 요약 결론\n"
        "- 라이선스: 확인 결과: CC BY / 내부 판단: 사용 가능 / 판단 근거: 약관 명시\n"
        "## 2. 항목별 상세 분석\n### 라이선스\n* 확인 결과: CC BY\n"
        "## 3. 소송 리스크 (해당 시)\n해당 없음\n"
        "## 4. 논문 제출 예외 (Major Company 레퍼런스)\n해당 없음\n"
        "## 5. 근거 및 출처\n1. https://example.com\n"
    )

    def test_sections_are_plain_headings(self) -> None:
        out = R.restructure_review(self.FULL, "NAB")
        for tag in ("<details", "</details>", "<summary"):
            self.assertNotIn(tag, out)
        self.assertIn("## 🔍 항목별 상세 분석", out)
        self.assertIn("## ⚖️ 소송 리스크 (해당 시)", out)
        self.assertIn("해당 없음", out)

    def test_sources_block_is_plain_heading(self) -> None:
        import types as pytypes
        from unittest import mock
        out = R.restructure_review(self.FULL, "NAB")
        src = R.render_sources([("제목", "https://example.com/a")])
        block = f"\n## 📚 직접 조회한 근거 자료 — 1건\n\n{src}"
        self.assertNotIn("<details", out + block)

    def test_dashboard_parser_reads_new_format(self) -> None:
        """기존(<details>) 댓글과 새(## 헤딩) 댓글을 대시보드 파서가 똑같이 읽는다."""
        import re
        import export_dataset_reviews as XD
        legacy = (Path(__file__).parent / "fixtures" / "review_dataset_ko.md").read_text(encoding="utf-8")
        new = re.sub(r"<details[^>]*>\s*<summary><b>(.*?)</b></summary>\s*", r"## \1\n\n", legacy, flags=re.S)
        new = new.replace("</details>", "")
        self.assertNotIn("<details", new)
        self.assertEqual(XD.parse_review(new), XD.parse_review(legacy))
        self.assertTrue(XD.parse_review(new)["license_judgment"])


if __name__ == "__main__":
    unittest.main()
