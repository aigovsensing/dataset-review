[← README](../README.md)

# 소송 리스크 검토

<sub>문서: [architecture](architecture.md) · [setup](setup.md) · [usage](usage.md) · [models-and-quota](models-and-quota.md) · **litigation** · [troubleshooting](troubleshooting.md) · [development](development.md)</sub>

---

## 소송 리스크 검토 (AI 학습 데이터 무단 활용)

모든 데이터셋 검토는 `3. 소송 리스크` 섹션에서, 해당 데이터셋(및 원본 데이터셋)이
**저작권자 허가 없이 AI 모델 학습에 무단 사용되어 제기된 소송**에 연루됐는지를
**소송 URL 제공 여부와 무관하게 Google 검색으로 능동 조사**합니다. 검색으로 관련 소송이
확인되면 사건 개요·근거 강도와 함께 보고하고, 확인되지 않으면
`해당 없음 (검색 결과 관련 소송 미확인)` 으로 표기합니다(검색 없이 단정하지 않음).

추가로 **관련 소송(CourtListener 등) URL** 을 함께 입력하면(권장), 해당 사건을 반드시
조사·보고하며 검토 결과 `3. 소송 리스크` 섹션에 다음을 정리합니다.

- **원고가 침해를 어떻게 입증했는가**를 근거 강도 **강 / 중 / 약** 으로 분류
  - **강(强)** — 피고의 논문·법정 문서 자인, 법원 사실인정·디스커버리
  - **중(中)** — 제3자 조사, 모델 자기 진술, "on information and belief" 등 논증적 추론
  - **약(弱)** — 명칭만 언급, 본문 근거 부재
- 근거가 된 **소장 원문 문장 직접 인용 + 항 번호** 표기 후 한국어 요약
