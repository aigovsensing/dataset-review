[← README](../README.md)

# 로컬 실행 / 개발 (Development)

<sub>문서: [architecture](architecture.md) · [setup](setup.md) · [usage](usage.md) · [models-and-quota](models-and-quota.md) · [litigation](litigation.md) · [troubleshooting](troubleshooting.md) · **development**</sub>

---

## 로컬 실행 / 테스트

```bash
pip install -r scripts/requirements.txt
export GEMINI_API_KEY=...           # AI Studio 키
export ISSUE_TITLE="[데이터셋검토] CelebA"
export ISSUE_BODY="### 데이터셋 명칭

CelebA

### 공식 홈페이지 / 저장소 URL

https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html"
python scripts/dataset_review.py            # review.md 생성
```

## 참고

- 검토 지침(시스템 프롬프트)은 `prompt-book/system_prompt_dataset_review.md` 에서 수정할 수 있습니다.
- Gemini의 Google 검색 그라운딩을 사용하므로 검토 결과에는 참조한 공식 출처 URL이 함께 첨부됩니다.
- Actions 로그의 `[diag] finish_reason=... prompt=... output=...` 줄에서 토큰 사용량과 종료 사유를
  확인할 수 있어, 응답이 비거나 잘릴 때 원인을 진단할 수 있습니다.
- API 키 동작 확인은 `tools/gemini_api_key_test.sh` 로 테스트할 수 있습니다.
- 검토 결과 맨 위에는 요청자에게 바로 복사·회신할 수 있는 **`종합의견`**(라이선스·수집방법·개인정보
  3줄 요약 + 리스크 결론)이 표시되며, 상세 분석은 그 아래 접이식 섹션으로 정리됩니다.
