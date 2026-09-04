"""Regression checks for issue-label review workflow wiring."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "dataset-review.yml",
    ROOT / ".github" / "workflows" / "paper-review.yml",
)
ORDER_FILE = ROOT / "prompt-book" / "gemini-api-keys.json"


def _mapped_secret_names(text: str) -> set[str]:
    return set(
        re.findall(
            r"^\s+(GEMINI_API_KEY(?:_[A-Z0-9_]+)?):\s*"
            r"\$\{\{\s*secrets\.\1\s*\}\}$",
            text,
            flags=re.MULTILINE,
        )
    )


class ReviewWorkflowTest(unittest.TestCase):
    def test_rerun_label_is_an_issue_trigger(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertRegex(text, r"types:\s*\[opened, labeled\]")
                self.assertIn("github.event.label.name == 'rerun-review'", text)
                self.assertIn('--body-file review.md', text)
                self.assertIn('--remove-label "rerun-review"', text)

    def test_gemini_secrets_are_explicitly_mapped(self) -> None:
        """Whole-context serialization causes runs with no jobs/action_required."""
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertNotRegex(text, r"toJson\(\s*secrets\s*\)")
                self.assertEqual(
                    _mapped_secret_names(text),
                    {
                        "GEMINI_API_KEY",
                        "GEMINI_API_KEY_AIGOVSENSING",
                        "GEMINI_API_KEY_AITSEC2025",
                        "GEMINI_API_KEY_GEUNSIKLIM",
                        "GEMINI_API_KEY_LEEMGS",
                    },
                )

    def test_dataset_workflow_maps_external_google_search_configuration(self) -> None:
        text = WORKFLOWS[0].read_text(encoding="utf-8")
        self.assertIn("GOOGLE_SEARCH_API_KEY: ${{ secrets.GOOGLE_SEARCH_API_KEY }}", text)
        self.assertIn("GOOGLE_SEARCH_ENGINE_ID: ${{ vars.GOOGLE_SEARCH_ENGINE_ID", text)

    def test_order_file_covers_every_mapped_slot(self) -> None:
        """시도 순서의 단일 출처(JSON 파일)와 yml 이 매핑한 secret 슬롯이 일치해야 한다.

        어느 한쪽에만 추가되면(파일에만 있고 yml 매핑 누락 → 값 없음으로 폴백,
        yml 에만 있고 파일 누락 → 알파벳 뒤로 밀림) 운영자가 의도한 순서가 깨지므로
        두 집합이 정확히 같은지 회귀 검증한다.
        """
        order = json.loads(ORDER_FILE.read_text(encoding="utf-8"))["order"]
        self.assertEqual(len(order), len(set(order)), "order 목록에 중복 이름이 있다")
        order_set = set(order)
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                mapped = _mapped_secret_names(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    order_set,
                    mapped,
                    "gemini-api-keys.json 의 order 와 yml 의 secret 매핑이 불일치",
                )


if __name__ == "__main__":
    unittest.main()
