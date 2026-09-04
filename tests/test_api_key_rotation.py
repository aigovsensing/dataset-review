"""Gemini API key discovery and issue-comment audit regression tests."""

from __future__ import annotations

import json
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_review import (  # noqa: E402
    build_ungrounded_model_chain,
    build_external_search_query,
    collect_api_keys,
    key_rotation_note,
    load_api_key_order,
    google_custom_search,
    main,
    safe_exception_text,
    should_rotate_api_key,
    should_try_ungrounded_fallback,
)

# Isolate order-independent tests from the repo's real prompt-book order file.
NO_ORDER_FILE = ROOT / "tests" / "_no_such_order_file.json"


class ApiError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class ApiKeyRotationTest(unittest.TestCase):
    def _tmp_order_file(self, order: list[str]) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump({"order": order}, fh)
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return path

    def test_collects_secrets_in_ascending_name_order(self) -> None:
        # With no order file present, discovery falls back to ascending name order.
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
            collect_api_keys(env, order_file=NO_ORDER_FILE),
            [
                ("GEMINI_API_KEY", "key-base"),
                ("GEMINI_API_KEY_AIGOVSENSING", "key-a"),
                ("GEMINI_API_KEY_DUPLICATE", "key-a"),
                ("GEMINI_API_KEY_LEEMGS", "key-c"),
            ],
        )

    def test_order_file_takes_priority_over_alpha(self) -> None:
        # prompt-book/gemini-api-keys.json 의 순서가 알파벳 스캔보다 우선한다.
        order_path = Path(self._tmp_order_file(
            ["GEMINI_API_KEY", "GEMINI_API_KEY_LEEMGS", "GEMINI_API_KEY_AIGOVSENSING"]
        ))
        env = {
            # 알파벳 순이라면 AIGOVSENSING 이 LEEMGS 보다 앞서지만,
            # 파일 순서가 우선하므로 LEEMGS 가 먼저 와야 한다.
            "GEMINI_API_KEY": "base",
            "GEMINI_API_KEY_AIGOVSENSING": "aigov",
            "GEMINI_API_KEY_LEEMGS": "leemgs",
            # 파일에 없지만 매핑된 키는 파일 순서 뒤에 알파벳으로 편입된다.
            "GEMINI_API_KEY_ZULU": "zulu",
        }
        self.assertEqual(
            [name for name, _ in collect_api_keys(env, order_file=order_path)],
            [
                "GEMINI_API_KEY",
                "GEMINI_API_KEY_LEEMGS",
                "GEMINI_API_KEY_AIGOVSENSING",
                "GEMINI_API_KEY_ZULU",
            ],
        )

    def test_repo_order_file_matches_expected_slots(self) -> None:
        # 저장소에 실제로 커밋된 순서 파일이 워크플로가 매핑한 5개 슬롯과 일치하는지 검증.
        self.assertEqual(
            load_api_key_order(),
            [
                "GEMINI_API_KEY",
                "GEMINI_API_KEY_LEEMGS",
                "GEMINI_API_KEY_GEUNSIKLIM",
                "GEMINI_API_KEY_AIGOVSENSING",
                "GEMINI_API_KEY_AITSEC2025",
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

    def test_ungrounded_model_chain_is_configurable_and_deduplicated(self) -> None:
        with patch.dict(
            "os.environ",
            {"GEMINI_UNGROUNDED_MODELS": " gemini-3-a,gemini-3-b,gemini-3-a,,"},
        ):
            self.assertEqual(build_ungrounded_model_chain(), ["gemini-3-a", "gemini-3-b"])

    def test_external_search_query_includes_dataset_and_legal_topics(self) -> None:
        query = build_external_search_query("[Dataset Review] Example", {"dataset_name": "Example Data"})
        self.assertIn('"Example Data"', query)
        self.assertIn("license", query)
        self.assertIn("privacy", query)

    def test_google_custom_search_parses_and_deduplicates_safe_results(self) -> None:
        payload = io.BytesIO(json.dumps({"items": [
            {"title": " Official  page ", "link": "https://example.org/data", "snippet": " Terms  here "},
            {"title": "duplicate", "link": "https://example.org/data", "snippet": "ignored"},
            {"title": "unsafe", "link": "javascript:alert(1)", "snippet": "ignored"},
        ]}).encode())
        with patch("dataset_review.urllib.request.urlopen", return_value=payload):
            self.assertEqual(
                google_custom_search("example", "secret", "engine"),
                [("Official page", "https://example.org/data", "Terms here")],
            )

    def test_google_custom_search_error_does_not_expose_secret(self) -> None:
        with patch("dataset_review.urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "Google Custom Search 호출 실패") as raised:
                google_custom_search("example", "do-not-leak", "engine")
        self.assertNotIn("do-not-leak", str(raised.exception))

    def test_ungrounded_fallback_only_covers_service_availability(self) -> None:
        self.assertTrue(should_try_ungrounded_fallback(ApiError(429, "grounding quota")))
        self.assertTrue(should_try_ungrounded_fallback(ApiError(404, "model unavailable")))
        self.assertTrue(should_try_ungrounded_fallback(ApiError(503, "high demand")))
        self.assertFalse(should_try_ungrounded_fallback(ApiError(401, "invalid credential")))
        self.assertFalse(should_try_ungrounded_fallback(ValueError("bad issue input")))

    def test_main_uses_plain_fallback_after_all_grounded_keys_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ", {"REVIEW_OUTPUT": str(Path(tmp) / "review.md")}, clear=True
        ), patch("dataset_review.collect_api_keys", return_value=[("KEY_A", "a"), ("KEY_B", "b")]), \
                patch("dataset_review.run_review", side_effect=ApiError(429, "grounding quota")) as grounded, \
                patch("dataset_review.run_ungrounded_review", return_value="PLAIN WARNING") as plain:
            self.assertEqual(main(), 0)
            self.assertEqual(grounded.call_count, 2)
            plain.assert_called_once_with("", "", "a")
            self.assertIn("PLAIN WARNING", (Path(tmp) / "review.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
