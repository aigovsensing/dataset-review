"""Gemini API key discovery and issue-comment audit regression tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_review import (  # noqa: E402
    collect_api_keys,
    key_rotation_note,
    safe_exception_text,
    should_rotate_api_key,
)


class ApiError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class ApiKeyRotationTest(unittest.TestCase):
    def test_collects_secrets_in_ascending_name_order(self) -> None:
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
                ("GEMINI_API_KEY_DUPLICATE", "key-a"),
                ("GEMINI_API_KEY_LEEMGS", "key-c"),
            ],
        )

    def test_configured_aliases_are_all_attempted_even_when_values_match(self) -> None:
        env = {
            "GEMINI_API_KEY_ORDER": (
                "GEMINI_API_KEY,GEMINI_API_KEY_LEEMGS,"
                "GEMINI_API_KEY_AIGOVSENSING"
            ),
            "GEMINI_API_KEY": "same-key",
            "GEMINI_API_KEY_LEEMGS": "same-key",
            "GEMINI_API_KEY_AIGOVSENSING": "same-key",
        }
        self.assertEqual(
            [name for name, _ in collect_api_keys(env)],
            [
                "GEMINI_API_KEY",
                "GEMINI_API_KEY_LEEMGS",
                "GEMINI_API_KEY_AIGOVSENSING",
            ],
        )

    def test_collects_secrets_in_explicit_rotation_order(self) -> None:
        env = {
            "GEMINI_API_KEY_ORDER": (
                "GEMINI_API_KEY,GEMINI_API_KEY_LEEMGS,"
                "GEMINI_API_KEY_GEUNSIKLIM,GEMINI_API_KEY_AIGOVSENSING,"
                "GEMINI_API_KEY_AITSEC2025"
            ),
            "GEMINI_API_KEY": "base",
            "GEMINI_API_KEY_AIGOVSENSING": "aigov",
            "GEMINI_API_KEY_AITSEC2025": "aitsec",
            "GEMINI_API_KEY_GEUNSIKLIM": "geunsik",
            "GEMINI_API_KEY_LEEMGS": "leemgs",
        }
        self.assertEqual(
            [name for name, _ in collect_api_keys(env)],
            [
                "GEMINI_API_KEY",
                "GEMINI_API_KEY_LEEMGS",
                "GEMINI_API_KEY_GEUNSIKLIM",
                "GEMINI_API_KEY_AIGOVSENSING",
                "GEMINI_API_KEY_AITSEC2025",
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

    def test_rotates_only_for_key_specific_failures(self) -> None:
        self.assertTrue(should_rotate_api_key(ApiError(429, "RESOURCE_EXHAUSTED")))
        self.assertTrue(should_rotate_api_key(ApiError(401, "invalid credential")))
        self.assertFalse(should_rotate_api_key(ApiError(503, "high demand")))
        self.assertFalse(should_rotate_api_key(ValueError("invalid issue input")))

    def test_exception_text_redacts_active_key(self) -> None:
        key = "AIzaSy-secret-value"
        rendered = safe_exception_text(RuntimeError(f"request with {key} failed"), key)
        self.assertNotIn(key, rendered)
        self.assertIn("[REDACTED]", rendered)


if __name__ == "__main__":
    unittest.main()
