"""Gemini API key discovery and issue-comment audit regression tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_review import collect_api_keys, key_rotation_note  # noqa: E402


class ApiKeyRotationTest(unittest.TestCase):
    def test_collects_secrets_in_ascending_name_order_and_deduplicates(self) -> None:
        env = {
            "SECRETS_CONTEXT": json.dumps({
                "GEMINI_API_KEY_LEEMGS": "key-c",
                "GEMINI_API_KEY": "key-base",
                "GEMINI_API_KEY_AIGOVSENSING": "key-a",
                "GEMINI_API_KEY_DUPLICATE": "key-a",
                "NOT_A_GEMINI_KEY": "ignored",
            })
        }
        self.assertEqual(
            collect_api_keys(env),
            [
                ("GEMINI_API_KEY", "key-base"),
                ("GEMINI_API_KEY_AIGOVSENSING", "key-a"),
                ("GEMINI_API_KEY_LEEMGS", "key-c"),
            ],
        )

    def test_rotation_note_contains_names_but_not_values(self) -> None:
        note = key_rotation_note(
            ["GEMINI_API_KEY", "GEMINI_API_KEY_AIGOVSENSING"],
            "GEMINI_API_KEY_LEEMGS",
        )
        self.assertIn("`GEMINI_API_KEY_AIGOVSENSING`", note)
        self.assertIn("`GEMINI_API_KEY_LEEMGS`", note)
        self.assertNotIn("AIza", note)


if __name__ == "__main__":
    unittest.main()
