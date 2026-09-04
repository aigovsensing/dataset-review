<div align="center">

<img src="docs/beagle-sniff.gif" alt="똘똘이 비글(Beagle) 마스코트" width="150" height="150" />

# 🐶 똘똘이 비글 · Beagle

**오픈 데이터셋 법적 리스크 검토 에이전트**

<em>데이터셋을 <b>킁킁</b>대며 라이선스·수집방식·개인정보·소송 <b>리스크를 찾아내는 탐지견</b> 🔍</em>

</div>

오픈 데이터셋의 **라이선스 · 데이터 생성/수집 방식 · 개인정보 포함 여부 · 소송 리스크**를
GitHub 이슈로 요청하면 **Gemini(구글 검색 그라운딩)** 가 자동 검토해 결과를 이슈 댓글로 등록합니다.
백엔드 서버 없이 **GitHub Pages + Actions + Google AI Studio 무료 API** 만으로 동작합니다.

> 본 검토는 **회사 내부의 사전 리스크 검토용 참고 자료**이며, 법률 자문이나 법적 판단을 대체하지 않습니다.

---

## 🚀 빠른 시작 (Getting Started)

배포·운영에 필요한 최소 단계입니다. 각 단계의 상세·확인 방법은 **[설정 가이드](documents/setup.md)** 를 보세요.

### 1. Gemini API 키 등록
[AI Studio](https://aistudio.google.com/apikey) 에서 무료 키를 발급받아(카드 등록 불필요),
저장소 **Settings → Secrets and variables → Actions → Secrets** 에 등록합니다.
- Name: `GEMINI_API_KEY` / Value: 발급받은 키

무료 쿼터 자동 전환을 위해 추가 키를 `GEMINI_API_KEY_<이름>` 형식(예:
`GEMINI_API_KEY_AIGOVSENSING`, `GEMINI_API_KEY_LEEMGS`)으로 등록할 수 있습니다. Actions는
`GEMINI_API_KEY_ORDER`에 지정된 순서로 시도하고, 한 키의 쿼터가 소진되면 다음 키로 자동 전환합니다.
실패 댓글에는 **Secret 변수명만** 남기며 API 키 값은 노출하지 않습니다.
같은 키 값이 여러 Secret 이름에 등록되어 있어도 설정된 슬롯을 빠짐없이 점검할 수 있도록
각 이름을 순서대로 시도합니다.

> 모델은 기본값 `gemini-flash-latest`(최신 Flash)로 자동 동작합니다. 그 외 변수는 전부 **선택**입니다 →
> [모델·쿼터 가이드](documents/models-and-quota.md). 무료 티어에서 3.x 결과를 받는
> [하이브리드 2패스](documents/models-and-quota.md#무료로-3x-결과-받기--하이브리드-2패스-gemini_writer_model)도 여기 있습니다.

### 2. 라벨 생성 (필수 ⚠️)
이슈 폼은 **이미 존재하는 라벨만** 자동 적용합니다. `dataset-review` 라벨이 없으면 워크플로가 `Skipped` 됩니다.
`gh` CLI로 한 번에 생성:

```bash
R=<owner>/<repo>
gh label create dataset-review --repo $R --color 1d76db --description "데이터셋 검토 요청 (트리거)" --force
gh label create paper-review   --repo $R --color 8250df --description "연구논문 검토 요청 (트리거)" --force
gh label create reviewing      --repo $R --color fbca04 --description "검토 진행 중" --force
gh label create reviewed       --repo $R --color 0e8a16 --description "검토 완료" --force
gh label create review-failed  --repo $R --color d73a4a --description "검토 실패" --force
gh label create rerun-review   --repo $R --color 5319e7 --description "재검토 강제 실행" --force
```

### 3. Pages · Actions 권한
- **Settings → Pages → Deploy from a branch → `main` / `/docs`** (입력·결과 홈페이지 배포)
- **Settings → Actions → General → Workflow permissions → Read and write** (이슈 댓글·라벨용)

### 4. 검토 요청 → 자동 검토
배포된 홈페이지(`https://<owner>.github.io/<repo>/`)의 **검토 요청** 탭에서 데이터셋 정보를 입력하면
GitHub 이슈가 생성되고, Actions 가 **1~3분 내** 검토 보고서를 이슈 댓글로 등록합니다.
→ 자세한 사용법·결과 열람·재검토는 **[사용 가이드](documents/usage.md)**.

### 로컬에서 한 번 실행해 보기

```bash
pip install -r scripts/requirements.txt
export GEMINI_API_KEY=...            # AI Studio 키
export ISSUE_TITLE="[데이터셋검토] CelebA"
export ISSUE_BODY="### 데이터셋 명칭

CelebA

### 공식 홈페이지 / 저장소 URL

https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html"
python scripts/dataset_review.py     # review.md 생성
```

키가 정상인지 먼저 확인: `./tools/gemini_api_key_test.sh <API_KEY>` → 초록색 ✓.

---

## 📚 문서 (Documentation)

세부 내용은 [`documents/`](documents/) 폴더로 분리했습니다.

| 문서 | 내용 |
| --- | --- |
| [설정 (Setup)](documents/setup.md) | API 키·라벨·Pages·Actions 권한·접근 암호·재배포 등 1회 설정 상세 |
| [사용 (Usage)](documents/usage.md) | 검토 요청·결과 열람·대시보드·재검토, 입력 팁, 논문(arXiv) 분석 방식, CSV 내보내기, 라벨 |
| [구조와 동작 (Architecture)](documents/architecture.md) | 데이터 흐름·동작 흐름 다이어그램, 설계 특징, 자의적 해석 금지 원칙, 구성 요소 |
| [모델·무료 쿼터·비용 (Models & Quota)](documents/models-and-quota.md) | 무료 운영 설계, 모델 선택/폴백, 무료 티어 모델, 503 자동 복구, **하이브리드 2패스**, 예상 비용 |
| [소송 리스크 검토](documents/litigation.md) | AI 학습 데이터 무단 활용 소송 조사·근거 강도 분류 방식 |
| [트러블슈팅](documents/troubleshooting.md) | 검토 미실행·`review-failed`·GitHub API 403 등 문제 해결 |
| [로컬 실행 / 개발](documents/development.md) | 로컬 실행법, 시스템 프롬프트 수정, 진단 로그 |

**검토 유형 2가지:** 데이터셋 검토(`dataset-review` 라벨)와 연구논문 법무 검토(`paper-review` 라벨)를
제공하며, 홈페이지 상단의 **🗂️ 데이터셋 / 📄 논문** 전환 버튼으로 각 요청 폼·결과 목록을 이용합니다.

## 🔗 링크

- 공식 홈페이지(데모): <https://aigovsensing.github.io/dataset-review/>
- 저장소: <https://github.com/aigovsensing/dataset-review>

## 라이선스

이 프로젝트는 [Apache License 2.0](LICENSE) 하에 배포됩니다.

> 🍺 **The Beer Clause (선택 사항, 법적 효력 없음):**
> 이 프로젝트가 마음에 들고 언젠가 제작자를 만나게 된다면, 맥주 한잔 사주셔도 좋습니다.
> 물론 의무는 아닙니다 — 정식 라이선스는 위의 Apache 2.0 입니다. 🍻
> _("법적 리스크 검토" 도구가 법적으로 모호한 Beerware를 쓸 수는 없어, 안전한 Apache 2.0 에 재미만 얹었습니다.)_
