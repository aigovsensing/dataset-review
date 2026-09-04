"""Regression checks for issue-label review workflow wiring."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "dataset-review.yml",
    ROOT / ".github" / "workflows" / "paper-review.yml",
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
                mapped = set(
                    re.findall(
                        r"^\s+(GEMINI_API_KEY(?:_[A-Z0-9_]+)?):\s*"
                        r"\$\{\{\s*secrets\.\1\s*\}\}$",
                        text,
                        flags=re.MULTILINE,
                    )
                )
                self.assertIn("GEMINI_API_KEY", mapped)
                self.assertIn("GEMINI_API_KEY_AIGOVSENSING", mapped)
                self.assertIn("GEMINI_API_KEY_AITSEC2025", mapped)
                self.assertIn("GEMINI_API_KEY_LEEMGS", mapped)
                self.assertIn(
                    "GEMINI_API_KEY_ORDER: GEMINI_API_KEY,GEMINI_API_KEY_LEEMGS,"
                    "GEMINI_API_KEY_GEUNSIKLIM,GEMINI_API_KEY_AIGOVSENSING,"
                    "GEMINI_API_KEY_AITSEC2025",
                    text,
                )


if __name__ == "__main__":
    unittest.main()
