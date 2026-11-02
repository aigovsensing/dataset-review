"""GitHub 전용 HTML → 순수 Markdown 변환 회귀 테스트."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dataset_review as R  # noqa: E402
from portable_markdown import to_portable_markdown  # noqa: E402

IMG = "https://raw.githubusercontent.com/aigovsensing/dataset-review/main/docs/beagle.png"
LEFTOVER_HTML = re.compile(r"<[a-zA-Z/][^>]*>|&[a-z]+;")


class PortableMarkdownTest(unittest.TestCase):
    def test_img_with_smart_quotes(self) -> None:
        src = f'<img src=“{IMG}” align=“right” width=“76” alt=“비글(Beagle)” />'
        self.assertEqual(to_portable_markdown(src).strip(), f"![비글(Beagle)]({IMG})")

    def test_details_become_headings(self) -> None:
        src = (
            "<details>\n<summary><b>⚖️ 소송 리스크</b></summary>\n\n해당 없음\n</details>\n"
            "<details open>\n<summary><b>🔍 상세</b></summary>\n\n"
            "<details>\n<summary>하위</summary>\n\n내용\n</details>\n</details>\n"
        )
        out = to_portable_markdown(src)
        self.assertIn("### ⚖️ 소송 리스크\n\n해당 없음", out)
        self.assertIn("### 🔍 상세", out)
        self.assertIn("#### 하위", out)  # 중첩은 한 단계 낮은 제목
        self.assertIsNone(LEFTOVER_HTML.search(out))

    def test_sub_code_nbsp(self) -> None:
        src = ("<sub>⚠️ 자동 생성 (model: <code>gemini-3-flash-preview</code>, PLAIN) · 참고</sub>\n"
               "> **대상 데이터셋** &nbsp;`NAB`")
        out = to_portable_markdown(src)
        self.assertIn("*⚠️ 자동 생성 (model: `gemini-3-flash-preview`, PLAIN) · 참고*", out)
        self.assertIn("> **대상 데이터셋**  `NAB`", out)

    def test_br_inside_blockquote_keeps_prefix(self) -> None:
        out = to_portable_markdown("> 🔑 **키:** `X` <br><sub>값은 숨김</sub>")
        self.assertEqual(out, "> 🔑 **키:** `X`  \n> *값은 숨김*\n")

    def test_plain_text_and_prose_quotes_untouched(self) -> None:
        src = "| a | b |\n| :-- | :-- |\n| “인용” | [링크](https://x.y) |\n"
        self.assertEqual(to_portable_markdown(src), src)

    def test_generated_review_has_no_html_left(self) -> None:
        body = R.restructure_review("## 1. 요약 결론\n내용\n## 2. 항목별 상세 분석\n상세\n", "NAB")
        out = to_portable_markdown(body)
        self.assertIsNone(LEFTOVER_HTML.search(out), out)
        self.assertIn(R.REVIEW_TITLE, out)
        self.assertIn(f"]({R.BEAGLE_IMG})", out)


if __name__ == "__main__":
    unittest.main()
