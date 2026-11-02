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
        # 남은 본문은 비글 이미지 → 대상 데이터셋 순서로 시작한다.
        self.assertLess(rest.index("beagle"), rest.index("대상 데이터셋"))

    def test_hoist_without_title_is_noop(self) -> None:
        self.assertEqual(R.hoist_review_title("plain text"), ("", "plain text"))

    def test_title_precedes_warning_and_model_header(self) -> None:
        title, rest = R.hoist_review_title(R.restructure_review(SAMPLE, "NAB"))
        out = "\n\n".join((title.strip(), "> ⚠️ 경고", "> 🤖 **검토 모델**", rest))
        self.assertTrue(out.startswith(R.REVIEW_TITLE))
        self.assertLess(out.index("⚠️ 경고"), out.index("검토 모델"))
        self.assertLess(out.index("검토 모델"), out.index("beagle"))
        self.assertLess(out.index("beagle"), out.index("대상 데이터셋"))
        self.assertEqual(out.count(R.REVIEW_TITLE), 1)


if __name__ == "__main__":
    unittest.main()
