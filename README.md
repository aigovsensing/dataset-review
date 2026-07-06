# 🛡️ 오픈 데이터셋 법적 리스크 검토 에이전트

오픈 데이터셋의 **라이선스 · 데이터 생성/수집 방식 · 개인정보 포함 여부**를 자동으로 검토하여
GitHub 이슈에 검토 결과를 등록하는 프로젝트입니다.

> 본 검토는 **회사 내부의 사전 리스크 검토용 참고 자료**이며, 법률 자문이나 법적 판단을 대체하지 않습니다.

## 동작 방식

```
[사용자] ──▶ GitHub Pages 홈페이지(docs/) : 데이터셋 정보 입력
        ──▶ "검토 요청" 클릭 → 이슈 폼이 자동 채워진 새 이슈 페이지 열림
        ──▶ Submit → GitHub 이슈 생성 ('dataset-review' 라벨 부여)
                    │
                    ▼
        [GitHub Actions] 이슈 감지 → scripts/review.py 실행
                    │  Google AI Studio(Gemini) + Google 검색 그라운딩
                    ▼
        검토 결과를 해당 이슈에 댓글로 등록 → 'reviewed' 라벨
                    │
                    ▼
[사용자] ──▶ 홈페이지 "검토 결과" 탭 또는 GitHub 이슈에서 결과 열람
```

- **백엔드 서버 없음**: 정적 홈페이지 + GitHub 이슈 폼 + GitHub Actions로만 동작합니다.
- **API 키 노출 없음**: Gemini API 키는 GitHub Secrets에만 저장됩니다.
- **완전 무료**: GitHub Pages / Actions 무료 티어 + Google AI Studio 무료 API.

## 구성 요소

| 경로 | 설명 |
| --- | --- |
| `docs/` | GitHub Pages로 배포되는 입력 홈페이지 (`index.html`, `app.js`, `style.css`, `config.js`) |
| `.github/ISSUE_TEMPLATE/dataset-review.yml` | 검토 요청 이슈 폼 (홈페이지가 이 폼을 prefill) |
| `.github/workflows/dataset-review.yml` | 이슈 생성 시 검토를 실행하는 GitHub Actions 워크플로 |
| `scripts/review.py` | Gemini 호출 + 검토 보고서 생성 스크립트 |
| `scripts/system_prompt.md` | 법적 리스크 검토 에이전트 시스템 프롬프트(검토 지침) |

## 설정 방법 (1회)

### 1. Google AI Studio API 키 발급
1. <https://aistudio.google.com/apikey> 에서 무료 API 키 발급
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: 발급받은 키
3. (선택) 모델 변경 시 **Variables** 탭에서 `GEMINI_MODEL` 추가 (기본값 `gemini-2.5-flash`)

### 2. GitHub Pages 활성화
- **Settings → Pages → Source: Deploy from a branch**
- Branch: `main` / 폴더: `/docs` 선택 후 저장
- 배포 URL: `https://<owner>.github.io/<repo>/` (본 저장소: <https://aigovsensing.github.io/dataset-review/>)

### 3. Actions 권한 확인
- **Settings → Actions → General → Workflow permissions**
- **Read and write permissions** 활성화 (이슈에 댓글/라벨을 달기 위해 필요)

### 4. 다른 저장소로 재배포하는 경우
- `docs/config.js` 의 `owner` / `repo` 값을 수정합니다.

## 라벨

워크플로가 자동으로 관리하는 라벨입니다(없으면 자동 생성됨).

| 라벨 | 의미 |
| --- | --- |
| `dataset-review` | 검토 요청 이슈 (트리거) |
| `reviewing` | 검토 진행 중 |
| `reviewed` | 검토 완료 |
| `review-failed` | 검토 실패 (API 키/쿼터 등 확인 필요) |
| `rerun-review` | 이 라벨을 추가하면 재검토를 강제 실행 |

## 로컬 실행 / 테스트

```bash
pip install -r scripts/requirements.txt
export GEMINI_API_KEY=...           # AI Studio 키
export ISSUE_TITLE="[검토] CelebA"
export ISSUE_BODY="### 데이터셋 명칭

CelebA

### 공식 홈페이지 / 저장소 URL

https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html"
python scripts/review.py            # review.md 생성
```

## 참고

- 검토 지침(시스템 프롬프트)은 `scripts/system_prompt.md` 에서 수정할 수 있습니다.
- Gemini의 Google 검색 그라운딩을 사용하므로 검토 결과에는 참조한 공식 출처 URL이 함께 첨부됩니다.
