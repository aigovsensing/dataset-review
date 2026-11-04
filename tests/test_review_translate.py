"""영어 요청 지원(scripts/review_translate.py) 회귀 테스트.

핵심 검증: 영어 본문 + 접힌 한국어 원문으로 합성한 댓글을, 대시보드 집계 파서(export_*.py)가
한국어 원문만 있을 때와 **똑같이** 읽는지(영어 요청 때문에 대시보드 집계가 깨지지 않는지).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dataset_review as R  # noqa: E402
import export_dataset_reviews as XD  # noqa: E402
import export_paper_reviews as XP  # noqa: E402
import paper_review as P  # noqa: E402
import review_translate as RT  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
KO_DATASET = (FIX / "review_dataset_ko.md").read_text(encoding="utf-8")
KO_PAPER = (FIX / "review_paper_ko.md").read_text(encoding="utf-8")

EN_DATASET = """# 🐶 Smarty Beagle · Open Dataset Legal Risk Review Result

> **Target dataset** `Books3`
> **Internal review result** ⚠️ **Needs further review**

## 📌 Overall opinion

| Review item | Result | Internal judgment | Rationale |
| :-- | :-- | :-- | :-- |
| ⚖️ **License** | Unable to verify | Risk present | Source: https://example.com/license |

<details>
<summary><b>⚖️ Lawsuit risk</b></summary>

Strength of evidence: Strong · direct admission. Plaintiff v. Defendant.

</details>
"""

EN_PAPER = """> 🤖 **Review model** `gemini-3.6-flash`

## Overall opinion

The paper is a water-treatment engineering study and uses no external AI dataset.
"""


def fake_translate(heading: str):
    """구조·URL 을 보존하면서 한글만 영어 단어로 바꾸는 가짜 번역기(검증 통과용)."""
    import re

    def _translate(api_key, model, markdown):
        return heading + "\n\n" + re.sub(r"[가-힣]+", "word", markdown)

    return _translate


class DetectLanguageTest(unittest.TestCase):
    def test_english_form_headings_mean_english(self) -> None:
        self.assertEqual(RT.detect_language("### Dataset name\n\nCelebA\n\n### Description\n\n_No response_"), "en")
        self.assertEqual(RT.detect_language("### Paper title\n\nResNet\n\n### Paper PDF / website URL\n\nhttps://x"), "en")

    def test_korean_form_headings_mean_korean(self) -> None:
        self.assertEqual(RT.detect_language("### 데이터셋 명칭\n\nCelebA\n\n### 설명 (Description)\n\nhi"), "ko")
        self.assertEqual(RT.detect_language(""), "ko")

    def test_user_text_containing_an_english_heading_is_not_mistaken(self) -> None:
        # 한국어 양식 본문 안에서 사용자가 쓴 줄이 '### Description' 이어도, 정확히 그 제목일 때만 영어로 본다.
        self.assertEqual(RT.detect_language("### 데이터셋 명칭\n\nfoo\n\n### 설명 (Description)\n\nsee ### notes"), "ko")

    def test_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"REVIEW_LANG": "en"}):
            self.assertEqual(RT.detect_language("### 데이터셋 명칭\n\nx"), "en")
        with mock.patch.dict(os.environ, {"REVIEW_LANG": "ko"}):
            self.assertEqual(RT.detect_language("### Dataset name\n\nx"), "ko")


class EnglishFormParsingTest(unittest.TestCase):
    def test_dataset_fields_from_english_form(self) -> None:
        body = ("### Dataset name\n\nCelebA\n\n### Description\n\n_No response_\n\n"
                "### Dataset repository URL\n\nhttps://huggingface.co/datasets/x\n\n"
                "### Related lawsuit (CourtListener URL)\n\nhttps://www.courtlistener.com/docket/1/a/\n\n"
                "### Select system prompt\n\nHeejin — system_prompt_dataset_review_heejin.md")
        f = R.parse_issue_body(body)
        self.assertEqual(f["dataset_name"], "CelebA")
        self.assertEqual(f["extra_notes"], "")
        self.assertEqual(f["dataset_repo_url"], "https://huggingface.co/datasets/x")
        self.assertTrue(f["litigation_url"].startswith("https://www.courtlistener.com"))
        self.assertEqual(R.get_system_prompt_path(f).name, "system_prompt_dataset_review_heejin.md")

    def test_english_title_prefix_and_default_prompt(self) -> None:
        self.assertEqual(R.derive_dataset_name("[Dataset Review] MyData", {}), "MyData")
        self.assertEqual(R.derive_dataset_name("[DatasetReview] MyData", {}), "MyData")
        self.assertEqual(R.derive_dataset_name("[데이터셋검토] 내데이터", {}), "내데이터")
        f = R.parse_issue_body("### Select system prompt\n\nNone (Base is used)")
        self.assertEqual(R.get_system_prompt_path(f).name, "system_prompt_dataset_review_base.md")

    def test_paper_fields_from_english_form(self) -> None:
        f = P.parse_paper_body("### Paper title\n\nResNet\n\n### Paper PDF / website URL\n\nhttps://arxiv.org/abs/1512.03385")
        self.assertEqual(f["paper_title"], "ResNet")
        self.assertEqual(f["paper_url"], "https://arxiv.org/abs/1512.03385")
        self.assertEqual(P.derive_paper_title("[Paper Review] My Paper", {}), "My Paper")


class ValidateTranslationTest(unittest.TestCase):
    KO = "## 종합의견\n\n| 항목 | 결과 |\n| :-- | :-- |\n| 라이선스 | CC BY | \n\n근거 https://a.example/x 입니다.\n\n<details>\n<summary><b>소송</b></summary>\n\n없음\n\n</details>\n"
    GOOD = "## Overall opinion\n\n| Item | Result |\n| :-- | :-- |\n| License | CC BY |\n\nBasis: https://a.example/x.\n\n<details>\n<summary><b>Lawsuit</b></summary>\n\nNone\n\n</details>\n"

    def test_good_translation_passes(self) -> None:
        self.assertEqual(RT.validate_translation(self.KO, self.GOOD), [])

    def test_missing_url_detected(self) -> None:
        bad = self.GOOD.replace("https://a.example/x", "the link")
        self.assertTrue(any("URL" in p for p in RT.validate_translation(self.KO, bad)))

    def test_lost_details_and_table_detected(self) -> None:
        self.assertTrue(any("details" in p for p in RT.validate_translation(self.KO, self.GOOD.replace("<details>", ""))))
        no_table = "## Overall opinion\n\nBasis: https://a.example/x. License CC BY.\n\n<details>\n<summary><b>Lawsuit</b></summary>\n\nNone\n\n</details>\n"
        self.assertTrue(any("표" in p for p in RT.validate_translation(self.KO, no_table)))

    def test_untranslated_korean_detected(self) -> None:
        self.assertTrue(any("한글" in p for p in RT.validate_translation(self.KO, self.KO)))

    def test_empty_detected(self) -> None:
        self.assertEqual(RT.validate_translation(self.KO, "  "), ["빈 응답"])


class TranslateFlowTest(unittest.TestCase):
    def test_invalid_first_answer_falls_through_to_next_model(self) -> None:
        calls: list[str] = []
        answers = iter(["", ValidateTranslationTest.GOOD])  # 첫 모델: 빈 응답 → 둘째 모델: 정상 번역

        def fake(api_key, model, markdown):
            calls.append(model)
            return next(answers)

        with mock.patch.object(RT, "_call_model", fake):
            en, model = RT.translate_to_english(ValidateTranslationTest.KO, [("K", "x")])
        self.assertEqual(en, ValidateTranslationTest.GOOD.strip())
        self.assertEqual(len(calls), 2)
        self.assertEqual(model, calls[1])

    def test_korean_particle_glued_to_url_does_not_cause_false_missing(self) -> None:
        ko = "근거는 https://a.example/x를 참고하세요. 그리고 (https://b.example/y)도 있습니다."
        en = "See https://a.example/x for the basis. Also (https://b.example/y) exists."
        self.assertEqual(RT.validate_translation(ko, en), [])

    def test_returns_none_when_every_model_fails(self) -> None:
        def boom(api_key, model, markdown):
            raise RuntimeError("boom")

        with mock.patch.object(RT, "_call_model", boom):
            self.assertEqual(RT.translate_to_english(KO_DATASET, [("K", "x")]), (None, ""))

    def test_code_fence_is_stripped(self) -> None:
        self.assertEqual(RT._strip_code_fence("```markdown\n# T\n\nbody\n```"), "# T\n\nbody")
        self.assertEqual(RT._strip_code_fence("# T"), "# T")


class ComposeAndExportCompatibilityTest(unittest.TestCase):
    def test_composition_layout(self) -> None:
        out = RT.compose_bilingual(EN_DATASET, KO_DATASET)
        self.assertTrue(out.startswith("# 🐶 Smarty Beagle"))
        self.assertIn("<details>\n<summary>🇰🇷", out)
        self.assertLess(out.index("Smarty Beagle"), out.index("오픈 데이터셋 법적 리스크 검토 결과"))
        self.assertTrue(out.rstrip().endswith("</details>"))

    def test_composition_respects_comment_length_limit(self) -> None:
        out = RT.compose_bilingual(EN_DATASET, KO_DATASET * 8, limit=20000)
        self.assertLessEqual(len(out), 20000)

    def test_dataset_export_parses_bilingual_comment_identically(self) -> None:
        bilingual = RT.compose_bilingual(EN_DATASET, KO_DATASET)
        self.assertIn(XD.REVIEW_MARKER, bilingual)  # 집계가 이 댓글을 검토 결과로 식별한다
        self.assertEqual(XD.parse_review(bilingual), XD.parse_review(KO_DATASET))
        self.assertEqual(XD.parse_litigation_detail(bilingual), XD.parse_litigation_detail(KO_DATASET))
        self.assertEqual(XD.parse_review(KO_DATASET)["litigation"], "있음")  # 소송 정보가 실제로 파싱되는 자료인지

    def test_paper_export_parses_bilingual_comment_identically(self) -> None:
        bilingual = RT.compose_bilingual(EN_PAPER, KO_PAPER)
        self.assertEqual(XP.parse_paper(bilingual), XP.parse_paper(KO_PAPER))

    def test_english_part_alone_would_not_be_identified_as_a_dataset_review(self) -> None:
        # 한국어 원문을 빼면 집계 대상에서 빠진다 → 원문 동봉이 필요한 이유.
        self.assertNotIn(XD.REVIEW_MARKER, EN_DATASET)


class MainFlowTest(unittest.TestCase):
    """main() 전체 흐름(키 순회 → 검토 → 번역 → 합성 → review.md 저장)을 가짜 Gemini 로 검증."""

    def run_main(self, module, runner_name: str, ko_result: str, issue_body: str, translate):
        import tempfile

        out = Path(tempfile.mkstemp(suffix=".md")[1])
        self.addCleanup(lambda: out.unlink(missing_ok=True))
        env = {"REVIEW_OUTPUT": str(out), "ISSUE_TITLE": "t", "ISSUE_BODY": issue_body}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(R, "collect_api_keys", lambda *a, **k: [("GEMINI_API_KEY", "k")]), \
                mock.patch.object(module, runner_name, lambda *a, **k: ko_result), \
                mock.patch.object(RT, "_call_model", translate):
            rc = module.main()
        self.assertEqual(rc, 0)
        return out.read_text(encoding="utf-8")

    def test_english_dataset_request_gets_english_on_top_and_korean_original_folded(self) -> None:
        text = self.run_main(R, "run_review", KO_DATASET, "### Dataset name\n\nBooks3",
                             fake_translate("# 🐶 Smarty Beagle · Open Dataset Legal Risk Review Result"))
        self.assertTrue(text.startswith("# 🐶 Smarty Beagle"))
        self.assertIn("<summary>🇰🇷", text)
        self.assertIn(XD.REVIEW_MARKER, text)                       # 대시보드가 이 댓글을 인식
        self.assertEqual(XD.parse_review(text), XD.parse_review(KO_DATASET))

    def test_korean_dataset_request_is_unchanged(self) -> None:
        called = []
        text = self.run_main(R, "run_review", KO_DATASET, "### 데이터셋 명칭\n\nBooks3",
                             lambda *a: called.append(1) or EN_DATASET)
        self.assertEqual(text, KO_DATASET)  # 번역 호출 없음, 본문 그대로(전환 내역 없음)
        self.assertEqual(called, [])

    def test_translation_failure_falls_back_to_korean_with_english_notice(self) -> None:
        def boom(*a):
            raise RuntimeError("down")

        text = self.run_main(R, "run_review", KO_DATASET, "### Dataset name\n\nBooks3", boom)
        self.assertTrue(text.startswith("> ℹ️ **English translation was unavailable"))
        self.assertIn(KO_DATASET.strip(), text)

    def test_english_paper_request(self) -> None:
        text = self.run_main(P, "run_paper_review", KO_PAPER, "### Paper title\n\nResNet\n\n### Paper PDF / website URL\n\nhttps://x",
                             fake_translate("# Paper legal review result"))
        self.assertTrue(text.startswith("# Paper legal review result"))
        self.assertIn("<summary>🇰🇷", text)
        self.assertEqual(XP.parse_paper(text), XP.parse_paper(KO_PAPER))


class NoticeTest(unittest.TestCase):
    def test_key_rotation_note_shows_names_only(self) -> None:
        note = RT.key_rotation_note_en(["GEMINI_API_KEY", "GEMINI_API_KEY_LEEMGS"], "GEMINI_API_KEY_AITSEC2025")
        self.assertIn("`GEMINI_API_KEY_LEEMGS`", note)
        self.assertIn("switched to `GEMINI_API_KEY_AITSEC2025`", note)
        self.assertNotIn("AIza", note)
        self.assertEqual(RT.key_rotation_note_en([]), "")

    def test_failure_notice_by_cause(self) -> None:
        class E(Exception):
            def __init__(self, code, msg):
                super().__init__(msg)
                self.code = code

        self.assertIn("quota", RT.english_failure_notice(E(429, "RESOURCE_EXHAUSTED")))
        self.assertIn("authentication", RT.english_failure_notice(E(403, "PERMISSION_DENIED")))
        self.assertIn("overload", RT.english_failure_notice(E(503, "UNAVAILABLE")))
        self.assertIn("rerun-review", RT.english_failure_notice(RuntimeError("x")))


if __name__ == "__main__":
    unittest.main()
