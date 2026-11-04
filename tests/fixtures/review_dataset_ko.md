# 🛡️ 오픈 데이터셋 법적 리스크 검토 결과

> **대상 데이터셋** &nbsp;`Books3`
> **내부 검토 결과** &nbsp;⛔ **사용 비권고**

---

## 🧭 요약 결론

### 내부 검토 결과

**사용 비권고**

| 검토 항목 | 확인 결과 | 내부 판단 | 판단 근거 |
| --- | --- | --- | --- |
| 라이선스 | 라이선스 없음 (저작권 침해 소지 다분) | **사용 비권고** | `Books3`는 저작권이 있는 서적을 불법 복제 사이트에서 수집하여 구성되었으며, 저작권자의 허락 없이 AI 모델 학습에 사용되어 소송의 대상이 되고 있음. |
| 데이터 생성·수집 방식 | 불법 복제 사이트(`Bibliotik`)에서 웹 스크래핑 | **사용 비권고** | 데이터셋 자체가 저작권 침해 소지가 있는 방식으로 수집되었으며, 원본 데이터셋(`The Pile`)의 구성요소로 포함되었음. |
| 개인정보 포함 여부 | 확인 불가 (포함 가능성 높음) | **잠재적 법적 리스크** | 서적 데이터의 특성상 개인을 식별할 수 있는 정보(이름, 위치 등)가 포함될 가능성이 높으나, 수집 동의 및 활용 범위에 대한 공식적인 확인이 불가함. |

<details open>
<summary><b>🔍 2. 항목별 상세 분석</b></summary>

### 라이선스

*   **확인 결과:** `Books3` 데이터셋 자체에는 명시적인 라이선스가 없으며, 저작권이 있는 서적들을 무단으로 수집하여 구성되었다. 상위 데이터셋인 `The Pile`은 EleutherAI에 의해 `MIT License`로 공개되었으나, 이는 `The Pile`의 구조나 메타데이터에 대한 라이선스로 보이며, `Books3` 구성요소의 저작권 문제와는 별개이다.
*   **라이선스:** 라이선스 없음 (저작권 침해 소지 다분)
*   **사용 조건:** `Books3`는 저작권이 있는 서적을 포함하고 있어, 저작권자의 허락 없이 사용될 수 없다.
*   **상업적 이용 가능 여부:** **불가능**. 저작권 침해 소지가 매우 높아 상업적 이용은 불가능하다.
*   **AI 모델 학습 가능 여부:** **불가능**. `Books3`는 AI 모델 학습에 사용되어 저작권 침해 소송의 대상이 되고 있다. 법원은 특정 소송에서 AI 학습을 공정 이용으로 판단한 사례가 있으나, 이는 개별 사안의 사실관계에 따라 달라질 수 있으며, `Books3`의 불법적인 수집 경위는 여전히 중대한 리스크이다.
*   **내부 판단:** **사용 비권고**
*   **판단 근거:** `Books3`는 저작권이 있는 수십만 권의 서적을 저작권자의 허락 없이 불법 복제 사이트에서 수집하여 구성되었으며, 이로 인해 여러 건의 저작권 침해 소송에 연루되어 있다.

### 데이터 생성·수집 방식

*   **확인 결과:** `Books3`는 Shawn Presser가 2020년에 생성한 데이터셋으로, 약 191,000~197,000권의 서적 텍스트를 포함한다. 이 서적들은 `Bibliotik`이라는 "해적 웹사이트" 또는 "그림자 도서관"에서 스크래핑되거나 수집되었다. `Books3`는 이후 EleutherAI가 2020년에 구축하고 공개한 `The Pile` 데이터셋의 22개 구성요소 중 하나로 포함되었다.
*   **생성 방식:** 웹 스크래핑 (불법 복제 사이트)
*   **생성 도구:** 확인 불가 (일반적인 웹 스크래핑 도구 사용 추정)
*   **생성 과정:** `Books3`는 OpenAI가 사용하는 데이터셋과 유사한 오픈 액세스 버전을 제공하여 AI 학습 데이터에 대한 접근을 민주화하려는 목적으로 생성되었다. EleutherAI는 `The Pile`을 구성하는 과정에서 데이터 정제 및 처리를 거쳤으며, 이를 미국 내 공정 이용(fair use)으로 간주했으나, 이는 법적으로 다툼의 여지가 있다.
*   **생성형 AI 모델 또는 소프트웨어:** 해당 없음 (사람이 직접 수집)
*   **Upstream Dataset:** `Bibliotik` (불법 복제 사이트)
*   **내부 판단:** **사용 비권고**
*   **판단 근거:** 데이터셋의 핵심 구성요소인 `Books3`가 저작권이 있는 자료를 불법 복제 사이트에서 무단으로 수집하여 생성되었으므로, 데이터 수집 과정 자체가 심각한 법적 리스크를 내포한다.

### 개인정보 포함 여부

*   **확인 결과:** `Books3`는 서적 텍스트로 구성되어 있다. 서적의 특성상 (특히 비소설, 전기, 또는 실제 사건 기반의 소설 등) 실제 인물의 이름, 위치 정보, 직업, 사건 관련 정보 등 개인을 식별할 수 있는 정보가 포함될 가능성이 매우 높다.
*   **포함 항목:** 이름, 위치정보, 기타 개인을 식별할 수 있는 정보 (포함 가능성 높음)
*   **활용 범위:** `Books3`는 불법 복제 사이트에서 수집되었으므로, 데이터에 포함된 개인정보에 대한 수집 동의나 공개 및 재배포 동의, 제3자의 활용 범위에 대한 공식적인 확인이 **불가**하다.
*   **내부 판단:** **잠재적 법적 리스크**
*   **판단 근거:** 개인정보가 포함되어 있을 가능성이 높음에도 불구하고, 해당 정보의 수집 동의 여부 및 활용 범위에 대한 공식적인 근거를 확인할 수 없다. 이는 개인정보보호법 위반의 소지가 있어 심각한 법적 리스크로 작용할 수 있다.

</details>

<details>
<summary><b>⚖️ 3. 소송 리스크</b></summary>

*   **소송 개요:**
    *   **사건명:** `Kadrey v. Meta Platforms, Inc.`
    *   **법원:** U.S. District Court for the Northern District of California
    *   **사건번호:** 3:23-cv-03417 (N.D. Cal.)
    *   **원고 · 피고:** 원고: Sarah Silverman, Richard Kadrey, Christopher Golden 등 작가들 / 피고: Meta Platforms, Inc.
    *   **상태:** 법원은 대부분의 청구(파생 저작물, 간접 침해, DMCA, 주법상 청구)에 대한 Meta의 기각 신청을 인용했으나, AI 학습을 위한 복제 행위 자체에 대한 직접 저작권 침해 주장은 기각하지 않았다. 이후 법원은 Meta의 공정 이용(fair use) 주장에 대한 약식 판결을 인용하여, AI 학습을 위한 사용이 공정 이용에 해당한다고 판결했다. 그러나 이 결정은 해당 사건의 사실관계에 국한되며, 모든 유사 사례에 적용되는 선례는 아니라고 명시되었다.
*   **문제된 데이터셋 및 침해 주장 요지:** 원고들은 Meta가 자신들의 저작권이 있는 서적을 무단으로 복제하여 `LLaMA` AI 모델을 훈련시켰다고 주장했다. 특히 `LLaMA`의 훈련 데이터셋에 `Project Gutenberg`와 함께 `The Pile`의 `Books3` 섹션이 포함되었다고 명시되었다.
*   **원고의 침해 입증 근거 강도: 강**

| 근거 강도 | 판단 기준 (원고가 어떻게 알아냈는가) | 소장 항 번호 | 소장 원문 인용 | 요약 |
| --- | --- | --- | --- | --- |
| 강 | 피고 자신의 기술 논문·법정 제출문서에서의 자인(自認) 및 데이터셋의 공개적인 출처 | Complaint (가정) | "Meta disclosed that the LLaMA training dataset included training data from a category called 'Books,' which came from two internet sources: (1) Project Gutenberg, an online archive of approximately 70,000 books that are out of copyright, and (2) 'the Books3 section of ThePile … a publicly available dataset for training large language models.'" | Meta는 `LLaMA` 훈련 데이터셋에 `Books3`가 포함되었음을 스스로 공개했다. 또한, `Books3`는 `Bibliotik`이라는 불법 복제 사이트에서 수집되었음이 널리 알려져 있었다. |

*   **내부 판단:** **사용 비권고**
*   **판단 근거:** 피고인 Meta가 `LLaMA` 모델 학습에 `Books3`를 사용했음을 스스로 공개했으며, `Books3` 자체가 저작권 침해 소지가 있는 불법 복제물로 구성되어 있다는 사실이 널리 알려져 있었다. 비록 법원에서 AI 학습에 대한 공정 이용 판결이 있었으나, 이는 개별 사안에 국한되며, 데이터셋의 불법적인 출처와 관련된 소송 리스크는 여전히 매우 높다.

</details>

<details>
<summary><b>📚 4. 근거 및 출처</b></summary>

*   **공식 홈페이지:**
    *   `The Pile`: `https://the-eye.eu/public/AI/the_pile/` (현재는 접근 불가 또는 다른 형태로 존재)
    *   `Books3`: `https://the-eye.eu/public/Books/Bibliotik/` (현재는 접근 불가)
*   **GitHub:**
    *   EleutherAI/the-pile: `https://github.com/EleutherAI/the-pile`
    *   psmedia/Books3Info: `https://github.com/psmedia/Books3Info`
*   **Hugging Face:** `The Pile`은 Hugging Face를 통해 접근 가능했음.
*   **LICENSE 문서:** `The Pile`은 `MIT License`를 사용함. `Books3`는 라이선스 문서 없음.
*   **Terms of Use:** 확인 불가 (원본 데이터셋인 `Bibliotik`이 불법 복제 사이트이므로 Terms of Use가 존재하지 않음)
*   **논문명:** `The Pile: An 800GB Dataset of Diverse Text for Language Modeling`
*   **논문 인용 문장:** "Recent work has demonstrated that increased training dataset diversity improves general cross-domain knowledge and downstream generalization capability for large-scale language models. With this in mind, we present \textit{the Pile}: an 825 GiB English text corpus targeted at training large-scale language models. The Pile is constructed from 22 diverse high-quality subsets -- both existing and newly constructed -- many of which derive from academic or professional sources."
*   **기타 공식 문서(URL):**
    *   Kadrey v. Meta Platforms, Inc. (CourtListener Docket): `https://www.courtlistener.com/docket/67569326/kadrey-v-meta-platforms-inc/`
    *   The Books3 Dataset: Controversy Surrounds Unauthorized Use in AI Training: `https://www.analyticsinsight.net/the-books3-dataset-controversy-surrounds-unauthorized-use-in-ai-training/`
    *   The Pile (dataset) - Wikipedia: `https://en.wikipedia.org/wiki/The_Pile_(dataset)`
    *   Bibliotik - Grokipedia: `https://grokipedia.org/wiki/Bibliotik`
    *   The Books3 Dataset: Controversy Surrounds Unauthorized Use in AI Training: `https://www.analyticsinsight.net/the-books3-dataset-controversy-surrounds-unauthorized-use-in-ai-training/`
    *   The Books3 case highlights the need for transparency in the training of artificial intelligence: `https://www.rettighedsalliancen.dk/the-books3-case-highlights-the-need-for-transparency-in-the-training-of-artificial-intelligence/`
    *   You Just Found Out Your Book Was Used to Train AI. Now What? - The Authors Guild: `https://www.authorsguild.org/industry-advocacy/you-just-found-out-your-book-was-used-to-train-ai-now-what/`
    *   Kadrey v. Meta: AI training found to be fair use, but it all depends on the facts: `https://www.lexology.com/library/detail.aspx?g=7691361c-8e3a-4416-a19c-0c14413e11f7`

</details>

<details>
<summary><b>🔎 참고 출처 (Google 검색 그라운딩) — 32건</b></summary>

본문의 `cite: N` 번호는 아래 동일 번호 출처로 연결됩니다.

1. [literaryagentmarkgottlieb.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHRTCZxohs7Q4aXkSdoMGJTrwzAb47lz7YEVKyHHyZREXoxMCw_l1GI_ZbTg7kErFQ5bPLkgeu0_d6Bcd8SSLgcwYH9qUlFY6e3AJEWIH-8SKy3cR6s4wKvCfAny6L_XraPLzWs12sI2CtBipTSM58Gf-NGJliD4nRmXoPgQ6OwPbdwGPwoDQezpRJsH6200eqOOOh3ecpc7lpQkGri0DoNMSIFaiNI6r8p71ad-BU=)
2. [wikipedia.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEo6Oq9AUREGW5z217hQ0EY_yQZmC7m9sFFfKZBBrRDcxz1HjRg_HE_ALvW7h8oMWMxDBY61USupmmVGlBvkQurttyj4uhg9O479MBDFxm2FcfvtKFW-YKp2ADce5QYQ3up6hD_-rvzNZ9hLA==)
3. [creativecommons.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFDQ1hhlfEVqDtgs8IQj5f39Lz0jZ-x3AgWKNh-gstD0wSqyHQnlrg4GES6yekMNWMBAUjYB1IM0R4j0h8xPd5eV90laaYfLIbNPyQ2RgC-xeD2yV49vT5XzWIDmHCbuHfatQIz9Ram1kxWnpKxkFvsNKiH0VkcCUjesZnjfxNxX6uvzGv-wc3BbAqcQDL0UaSI)
4. [grokipedia.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGEvEoBP-j754hGi7VOv2esZ1hciFN6DKhtZlTWDNZEz7AMKZX_Jv6ZO_habxPOoBLpKWadm3ihKf_Hviplcshl6H4V940vl4LWI42bCzTwPt_EhDbM5uS7xoE6SMyPRGg=)
5. [authorsguild.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH1sX5PeIdgV35lOEq6MQL5kXL6-I6X1ZO-LYcLBRvuyvcEutXr9aeDimYwO6uF_D2wc63-_78vjg3FWAmALNDQZqO55J2y8iPsSuuU1Wd2H5459Nf2ULRnsQX4BPi1hZU5bYWvcPvsSTZby_pXdrDgLXIzWdubTDWI6bs6kJN30Q4g4ED-N_a5uBUuFDKRV7SuVFY4)
6. [theweek.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFctLJ-6epoipj8runNjZi8BLgKdx5vQO0nQi9JjhcHl2yg6P-ng8-s-ybJXbQDkbHpMcJjxYn0gg8DjwqNOBihQGOSSFMUa-euPE6tG-e8PqsFHMKAM4YJHTBoNy8YlU0Z6uey9QyNVOnyZJYl5avk0xlXfKsV_xASkt5S)
7. [rettighedsalliancen.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFGM5J1JT2zMJFs0xDwPoxFBzOc07r8FELwfA2IYtakf4tDJUnxe5hP1desZf98OrvMeN8Ow85BZip4tKnwiKPXLOGW-3PTZaLPFB6OpDJqxe5QaJ8Bo2pTjUCJu-6QOfJ3hLTEWi0ThPLkZcuEGEaaMY5NQJNyzF_aX0smXAvAPQJWVxBPrASEYluYWafxxLxMvgCv8IiDYvS9x09vVYaaMOJ3KyQ4Z4_fjF5kYmEEy4efrW5WxnTiWDd1SA==)
8. [janefriedman.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHAI7-8x76zYA7u_wg5snLcdPwb0fhsjjW4tPMmFXkBWnwQ5GaHOKSsBRliOaRlpwH8Ds_bKg72IQ-i56U84iBCm2ue7xPVyBBNSaY9cKYQsvRaOaxtnRuGv-Nv6ugTlHJa0iM6_EXLPwZ9CdvDHRPlc2MZt6P-A6rPfpug6xxDluJ79IzS1xSIeORBqBkwkuvN_p8=)
9. [mashable.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGLOTu2iJhqiIpJB8O0InDW20He2gSaEjVlNDvnNiNbZ1njixbUjxta6-CM53MeKdDA7KM5lsLFGSzy9EbkMP0B4jx4U6UuWbPH52iGYmzbvDc99q1MC8NVaeXoxVx7c_rQDwWwQ5Ye_nuyd_7ay72wtJkI64y7B7U=)
10. [substack.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFr93nAZ_wQb62L_hYT49zcgxZXF197XpitkT6pH3oM15NiMXaIj4K_88cX6S370sz83xiEYMOSdu415klHCtFU9HaZhlnzjPCjCOpFLneij0PmTNoTyD8ukJUA67pglEK3oaqPKsJ5WJoh8tvCuiZ4Fpz9nP8dwm1ZpA==)
11. [substack.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF4tSxZSuflq4s1wDBoikZzCoofmw-VLhBzqlU5JP3B7V0FfgEQh4irp0tGGBc3yqt_grzaAsjHfP3wSX6Sbg8Jl971rD_19sWpYheTSqiIL1K7pM6x_uw1APei_KUyhype-kp0iKdjULuZ6utjK2NV_gZIqt3hisAsgUxQLwUJP4-C)
12. [ibm.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG_2BwpLVWX05jidcXFpReqdUTMVdbwD3-ZI88VSefBdsZQLlpMdkMiWCWO6thcVtkJzYxtqz0wlOuXvzYlQdzTDMypvT87Hlr1svmLbJFack1irdoJhqJy4Ov0_oaniw==)
13. [piwik.pro](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFuSb49c2aaTi4Q68DZmR4c-C9FFfBnfcJ7tAYLLOnxjLk1T1nHOLuKgW3KsCrD_8_UDuAxjoa7ZkX92HsQEhK3SN-ow51ZxKRRRhUMKOpovoYFf4TMX0AuEpTB5FucOerhjFwbU7rjcQvBiEs=)
14. [kaspersky.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEGwj_Am7QsqiRpmRa5Ikk9khs6wy-k6lmXdwVGq8Pc7wxv-xIGIE7dSmT-uSl1qt_NSkmoskXrNkx0eGdXsNbq4ZoBuADV8VmdxQSi3VHXDcK_kilTVCQiLkCRBE__JCwwULUkxHv1yI0AYqg1Dhx-GQ-WpzqWWNPrYoHAytNp_-YpiAXWGFS3U-0o-3cHaWB8)
15. [security.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEc4kR8jiSKSvbzgkXERaYn1K3lVKKMDqNXPYDLUv2T68PLEQV37cXtSNQrXN3e-byiI89LDCnsRJ4Zipyuv2phcnZpKbMlMwf4oQZ2x-ef_IRjmTaQd83TBvoDiAoE0-UypN9qf7kO62FWePO_fCg=)
16. [osano.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFAyadvvrjf0lRUJAjw0P5l1j1r7qPWUfACvZpkCMXYnBcycMnebuVrq-kQ1bMQKYRnguAKIOg1uTWCF244B3lUSyPGaBUPaUgVzpJNVPKSxGyjDult5l8636aAi9rz6oBFdKJtPs_qzA==)
17. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGxYg80RtcEE20AwgNPky4gx2etppnQeWGMwiLG05hnK7rm8GeNoBqu5JyuQttNC-zQq7-BWFgW9HaRAf6-MJasGC6hzJ3mTiapHshb9SBTxwc5skgbbJAMoXxRECHFrkv3GAFClOaficIQ1-nPOZ47AMM3yNU=)
18. [bakerlaw.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHWynvJmcpMd0umAqZMk_L3P6w1c1lfKsTPRRtWDq1HgMC_pSHsEEZL4uUJ2JLmswP4lWtKm-GopMhnpJg1mmUdUcOa97hu_kOzXgGw0sZPhmVjy6Z9GvOR-P7zWz4sDo9FJQ==)
19. [skadden.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFJ0Ox3bnh5a-v2ETQmflsvqG-zbBHuRs2HQpQhsjl9qwN5Hweg5Jt-AUPuIhjbhCjKuoXmbBkINgAvP4oJheonQhX0mB5ib1YNOOiQuwGNnG22I--_eWrw6u9IHaURR6ZiH16OEI8c-UMEonthSPSqukJhQWfWRwz_QnChNS88M9FjV-WLZ7gCBdNVaFQBsg==)
20. [loeb.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHtUj7h6RB-lwOxKHbW2sAYfdI9HqP3Ue-Se3q6brwG1ANwLzn3t3FVBpVLa9K16WXuvTP_BcxydeUldjwruU9MrjBeZDdNlpLymM2rfp-bg8FEigphH9WsrbTzM0y0Ot-yKl-_atiI7rfhPw77zgfQfvYKgqeNLz5GpJ1M-jOQHrgzAIuEvzsOljJqjz7MRjsnWg44)
21. [knowingmachines.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFZJPbcNrRuqKoOuZZt-zfVXsXZ4Mcq75HwXD0_sCqpxNfs6wmOOGj-xictT_5VoZIshvp3wuzPWxE6ao0ZUW1Z5N5eEmnz3bheykLQSagKVPT8d1IhHmgxK4HFLuv-tXKRuCea2bGSXsVTGixtBTCu5zFlAt3Hqh8QKZds1_N8m-sjKu5xKlotSHz68TdlwJpt)
22. [daveadr.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGkpx84UOrxhQrFO6rODWyO8tNoh8ssMUd9_digz98LER9pt6Zj4J6SHYA9jjOVoD7MLIY-XoW3O2s5wM5saehwL2oa-hkcglL2bKio0ho00AbRTX7E5MRpWDnwnP0KNRR89Awa3rwziA==)
23. [courthousenews.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHrvbZ7yGVKCt_bF9fNcxkteihLzNLGoImun9vPoPmvDqkfXpRmdX1NrzKc9mtmkl_yJQl0tpVus1kicNo-XZ9kVolEGYcRfbf0rwUKAhrASVnpXJk3E17baqK6A-IMCLpYoYi9xcqPdiiF4GCSUu4jAs4EQMP1DcX2OOwM7a2ufMGUV3H0zx-J7ZYxE8qxAGpH-GuQfnyLxTL5FUzZakcKgA8bcRutGEQ=)
24. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHZcJVBGl4oUEeu9nv7f35JAqA_7vq0SpYuhu2UoLWkQOAKCpjkWUHkIfBgv102_y2sCkhpr1PlVnN3QfsaPiovZRaAJ0W9ZIEJiBcO0rGdQ8s1T8b70gHzVZz8pMyR1RmWklUc9UvV1kRagMYzjYRn)
25. [reddit.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGNEO-ynvnUZpo1aQf5IHW3y7gZ205buSvx_T0VFjSIw4cScC2vCvHioJn8NeLOykrFwxmFjy-VkzjeTfuhX_wqQizAYheI7SNPtgp06lwTfG-esg--PEypluGcX3ijw0Vu2H4phT2fRYyFutIiMI9_h1H9lT_HIyZqtjeLUnluGiDwZ1faFHd4KcGgZRj1pDNQCKgvpqs8UR-7xNJ0SH6L)
26. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE2-tKy7yxDiF-4nTasPnJeOoVxOWtfOWqMxZFi0heaO8MyXYlvHu6U4pLHHs3InhGtitlmRhGQeaErH-NbqWANguNhdHytVC6aRFzeKgOGDZRUwK4eZtlrp_3xybFqbikR9xP-GgSfc1QXauGoRXI9eOtUsK37FJ-tv_WntYffES6X0d1rV2HjEEisXjLT6v55bLOILJFossR9OVIn6NiAZ_YaXTI=)
27. [eleuther.ai](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFSIfntpfIFpiv0HZ7w0p-7VGXsbazLKFbQdI22vzB87P43R06WPB3DCukJXNtXpylQCFPEz15SAORRUoafU6Fa-GnXPiHh5_UTm4V96lhBlmwmYSk=)
28. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHSGKFg2HOgMBteTBGOqR4jx-dVkLPykD0swwJEZg_36cGhN2FeNIYNPYXZyYnO2CTnvSEGztt6ZWvrCeHOqrYlEQ5U2GR_7th6kNoV46dVL8GfmrJE7dK64sgs)
29. [ycombinator.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH-Drzotyu4KfJbcBZDCuDrf9vAUs-TrYquVMM6oIWnESLKbCWYAyBhprRrJj4ze96mmv55NrgwIc-GgvFbB8FtQYsr0fwsSoD5OszCRzpsRQdbZkl6s6MUpZFd1MHudtuRIPQwctUK1Q==)
30. [lithub.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEs0VYDI9Hms2DxiUvkjlB_vo58wrwv-0bqwO6ZB2K3r-gehxviU48ufokf2-IFoKZm7fz16hr0YVG3ZKI8zSbyAhzIi-1RGOFnWYJtYAcjB9Kpxx4OgAHV2G-ZvbfTgSOG-fKfbDC1qc20knNIFF7ih7aEsNyKvFfXAHG9E9eHDYE=)
31. [reddit.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF5Dybvo82suQ8RcoMLNjoxLeyTDTZjOmwku8-YmC_QPgt6ULO34IGRvVvCz2cBrupGWlMp-ehstqFsM_jXMN4Aysp2JERzm-aQ0jkVKsbQQ6AVA3HVqsuynk4okZWYPgyGLqzKd51vUxI9f5IwJWl2hR5ZSZLrRWOG1ItUcO5Tz-64PafgnsSI_U5UMVTTMiFwEuQhaZBWadNodbEJa4gmoR9hRsU=)
32. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFQVKBbgZpX_evXzQ4tznbQHA8y11laxjRThwZNBeDuXVvwxyVMhZJZnss-hHEHBZ00J6Jf-k3pzBy8lyGLa9UG2XOOAXaOCCJelNkmsuKNOJrdc8Or0Bs34GjzMSXjKEs=)

</details>

---
<sub>🤖 자동 생성 (model: <code>gemini-2.5-flash</code>, Google Search grounding) · 본 검토는 회사 내부 사전 리스크 검토용 참고 자료이며 법률 자문을 대체하지 않습니다.</sub>