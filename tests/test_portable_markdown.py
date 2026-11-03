"""GitHub 전용 HTML → 순수 Markdown 변환 회귀 테스트."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dataset_review as R  # noqa: E402
from portable_markdown import is_review_result_body, to_portable_markdown  # noqa: E402

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
        self.assertNotIn("beagle", out)  # 마스코트 이미지는 출력하지 않는다

    def test_review_result_detection(self) -> None:
        self.assertTrue(is_review_result_body(R.REVIEW_TITLE + "\n> 🤖 **검토 모델** `m`"))
        self.assertTrue(is_review_result_body("> 🤖 **검토 모델** &nbsp;`m`\n논문 본문"))  # 논문 검토
        self.assertTrue(is_review_result_body("**모델 정보:** `gemini-3.6-flash`\n## 종합의견"))  # 예전 형식
        self.assertFalse(is_review_result_body("🤖 자동 논문 법무 검토를 시작합니다. 잠시만 기다려 주세요"))
        self.assertFalse(is_review_result_body("🤖 자동 법적 리스크 검토를 시작합니다."))
        self.assertFalse(is_review_result_body("## ⚠️ 자동 법적 리스크 검토 실패\n\n오류"))
        self.assertFalse(is_review_result_body("## ⚠️ 자동 논문 법무 검토 실패\n\n오류"))

    def test_js_converter_mirrors_python(self) -> None:
        # 홈페이지(docs/app.js)의 변환기가 같은 규칙을 쓰는지(핵심 정규식이 존재하는지) 확인.
        js = (Path(__file__).resolve().parents[1] / "docs" / "app.js").read_text(encoding="utf-8")
        for needle in ("function toPortableMarkdown", "function isReviewResultBody",
                       'class="btn small md-copy"', "**검토 모델", "검토를 시작합니다"):
            self.assertIn(needle, js)

    def test_rich_clipboard_support_is_present(self) -> None:
        # 리치 편집기(SunEditor 등)용 HTML + 일반 텍스트용 Markdown 을 함께 복사하는 경로.
        js = (Path(__file__).resolve().parents[1] / "docs" / "app.js").read_text(encoding="utf-8")
        for needle in (
            "function toPortableHtml",          # GitHub 렌더 HTML 정리
            'querySelectorAll("hr")',           # <hr> 뒤 내용이 버려지는 편집기 대응
            "application/vnd.github.full+json",  # body_html 수신
            "new ClipboardItem",                # text/html + text/plain 동시 복사
            '"text/html"', '"text/plain"',
            "markdown-accessiblity",            # GitHub 전용 래퍼 언급(제거 대상)
        ):
            self.assertIn(needle, js)


if __name__ == "__main__":
    unittest.main()
