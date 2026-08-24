"""논문 검토 사용자 프롬프트의 필수 출력 지침 회귀 테스트."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from paper_review import build_paper_prompt  # noqa: E402


class BuildPaperPromptTest(unittest.TestCase):
    def test_requires_abstract_and_dataset_purpose(self) -> None:
        prompt = build_paper_prompt(
            "Example Paper",
            {},
            "url",
            "https://example.com/paper",
        )

        self.assertIn("논문 초록", prompt)
        self.assertIn("각 외부·자체 생성 데이터셋을 사용한 목적", prompt)
        self.assertIn("학습·미세조정·검증·평가·벤치마크·비교 실험", prompt)
        self.assertIn("근거 위치와 원문 인용", prompt)
        self.assertIn("'확인 불가'", prompt)


if __name__ == "__main__":
    unittest.main()
