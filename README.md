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

### 4. 라벨 생성 (필수) ⚠️
> **중요:** 이슈 폼 템플릿은 저장소에 **이미 존재하는 라벨만** 자동 적용합니다.
> `dataset-review` 라벨이 저장소에 없으면 검토 요청 이슈에 라벨이 붙지 않아 워크플로가
> `Skipped` 됩니다. 아래 라벨을 **미리 생성**해 두어야 합니다.

`gh` CLI로 한 번에 생성:
```bash
R=<owner>/<repo>
gh label create dataset-review --repo $R --color 1d76db --description "검토 요청 (트리거)" --force
gh label create reviewing      --repo $R --color fbca04 --description "검토 진행 중" --force
gh label create reviewed       --repo $R --color 0e8a16 --description "검토 완료" --force
gh label create review-failed  --repo $R --color d73a4a --description "검토 실패" --force
gh label create rerun-review   --repo $R --color 5319e7 --description "재검토 강제 실행" --force
```

### 5. 다른 저장소로 재배포하는 경우
- `docs/config.js` 의 `owner` / `repo` 값을 수정합니다.
- 위 4번의 라벨 생성을 새 저장소에서도 수행합니다.

## 라벨

| 라벨 | 의미 |
| --- | --- |
| `dataset-review` | 검토 요청 이슈 (트리거). **사전 생성 필요** — 이슈 폼이 이 라벨을 부여 |
| `reviewing` | 검토 진행 중 (워크플로가 자동 부여/제거) |
| `reviewed` | 검토 완료 (워크플로가 자동 부여) |
| `review-failed` | 검토 실패 — API 키/쿼터 등 확인 필요 (워크플로가 자동 부여) |
| `rerun-review` | 이 라벨을 추가하면 재검토를 강제 실행 |

## Gemini API 쿼터 보호

검토 1건 = Gemini API 호출 1회이므로, 무분별한 이슈 생성은 무료 티어 쿼터를 빠르게 소진시킬 수 있습니다.
이 프로젝트는 다음 장치로 쿼터를 보호합니다.

- **트리거 권한 제한 (핵심):** 워크플로는 이슈 작성자가 저장소 `OWNER` / `MEMBER` / `COLLABORATOR`
  인 경우에만 검토를 실행합니다(`author_association` 검사). 외부인이 이슈를 열어도 검토(=Gemini 호출)가
  실행되지 않습니다. 사외 사용자에게도 개방하려면 `.github/workflows/dataset-review.yml` 의 `if`
  조건에서 이 검사를 완화하세요.
- **중복 실행 방지:** `reviewed` 라벨이 붙은 이슈는 재검토되지 않습니다(재검토는 `rerun-review` 라벨로만).
- **동시 실행 직렬화:** `concurrency` 설정으로 같은 이슈의 중복 이벤트를 취소해 이중 호출을 막습니다.

> ⚠️ 참고: 저장소 설정의 **"Allow GitHub Actions to create and approve pull requests"** 옵션은
> `GITHUB_TOKEN` 의 PR 생성/승인 권한만 제어하며, **워크플로 실행 횟수나 Gemini 호출과 무관**하므로
> 쿼터 보호에는 효과가 없습니다. (이 프로젝트는 PR을 만들지 않으므로 꺼도 무방합니다.)

## 소송 리스크 검토 (AI 학습 데이터 무단 활용)

데이터셋이 AI 학습 데이터 무단 활용 소송의 대상인 경우, 검토 요청 시
**관련 소송(CourtListener 등) URL** 을 함께 입력할 수 있습니다. 입력하면 검토 결과에
`3. 소송 리스크` 섹션이 추가되어 다음을 정리합니다.

- **원고가 침해를 어떻게 입증했는가**를 근거 강도 **강 / 중 / 약** 으로 분류
  - **강(强)** — 피고의 논문·법정 문서 자인, 법원 사실인정·디스커버리
  - **중(中)** — 제3자 조사, 모델 자기 진술, "on information and belief" 등 논증적 추론
  - **약(弱)** — 명칭만 언급, 본문 근거 부재
- 근거가 된 **소장 원문 문장 직접 인용 + 항 번호** 표기 후 한국어 요약

## 알려진 이슈 / 트러블슈팅

### "검토 결과" 목록에 `GitHub API 403` 이 표시되는 경우 ⚠️ (운영 필독)

홈페이지의 **검토 결과** 탭 목록은 브라우저에서 **비인증(토큰 없이)** GitHub REST API를 호출합니다.
비인증 요청은 **IP당 시간당 60회**로 제한됩니다.

- 결정적으로, **회사 프록시/NAT 때문에 사내 모든 사용자가 같은 공용 IP를 공유**합니다.
  그래서 60회/시간 한도가 **사무실 전체에서 순식간에 소진되어 403(rate limit exceeded)** 이 발생합니다.
- 인증을 붙이면(시간당 5,000회) 해결되지만, 그러려면 **토큰을 브라우저에 노출**해야 하므로
  보안상 부적절합니다. 따라서 인증은 적용하지 않습니다.

이는 코드 버그가 아니라 GitHub의 정상적인 비인증 API 한도이며, 공용 IP 환경 특성상 자주 발생합니다.
대신 다음과 같이 견고하게 처리합니다.

- **한도 초과를 명확히 안내** — 원인과 **리셋 예상 시각**(`X-RateLimit-Reset`)을 표시
- **마지막 목록 캐시** — 마지막으로 성공한 목록을 `localStorage` 에 저장해 실패 시 "최신이 아닐 수 있음"
  표기와 함께 보여줌
- **GitHub 이슈 페이지 직접 링크** 제공 — 웹 이슈 페이지는 API 한도와 무관하므로 언제든 조회 가능

> **대처:** 목록이 안 보이면 잠시(최대 1시간, 리셋 시각까지) 기다리거나, "GitHub에서 이슈 보기" 링크로
> 직접 확인하세요. 상세 검토 결과(이슈 댓글)는 이 한도와 무관하게 항상 열람할 수 있습니다.

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
- API 키 동작 확인은 `tools/gemini_api_key_test.sh` 로 테스트할 수 있습니다.
- 검토 결과 맨 위에는 요청자에게 바로 복사·회신할 수 있는 **`종합의견`**(라이선스·수집방법·개인정보
  3줄 요약 + 리스크 결론)이 표시되며, 상세 분석은 그 아래 접이식 섹션으로 정리됩니다.

## 라이선스

이 프로젝트는 [Apache License 2.0](LICENSE) 하에 배포됩니다.

> 🍺 **The Beer Clause (선택 사항, 법적 효력 없음):**
> 이 프로젝트가 마음에 들고 언젠가 제작자를 만나게 된다면, 맥주 한잔 사주셔도 좋습니다.
> 물론 의무는 아닙니다 — 정식 라이선스는 위의 Apache 2.0 입니다. 🍻
> _("법적 리스크 검토" 도구가 법적으로 모호한 Beerware를 쓸 수는 없어, 안전한 Apache 2.0 에 재미만 얹었습니다.)_
