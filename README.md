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
        [GitHub Actions] 이슈 감지 → scripts/review.py 실행 (Gemini 호출 1회)
                    │  Google AI Studio(Gemini)
                    │   + Google 검색 그라운딩 (공식 자료 검색)
                    │   + URL 컨텍스트 (논문 PDF·홈페이지 원문을 직접 열어 읽음)
                    ▼
        검토 결과를 해당 이슈에 댓글로 등록 → 'reviewed' 라벨
                    │
                    ▼
[사용자] ──▶ 홈페이지 "검토 결과" 탭 또는 GitHub 이슈에서 결과 열람
```

- **백엔드 서버 없음**: 정적 홈페이지 + GitHub 이슈 폼 + GitHub Actions로만 동작합니다.
- **API 키 노출 없음**: Gemini API 키는 GitHub Secrets에만 저장됩니다.
- **완전 무료**: GitHub Pages / Actions 무료 티어 + Google AI Studio 무료 API.
- **AI 호출 최소화 설계**: 검토 1건당 Gemini 호출은 **정확히 1회**이며, 그 외 모든 기능
  (이슈 파싱, 보고서 정리, 인용 링크, 결과 목록 등)은 AI 없이 일반 코드로 동작합니다.
  → 자세한 내용은 [무료 Gemini API 안정 운영](#-무료-gemini-api-안정-운영-호출-최소화-설계) 참고.
- **논문 원문 직접 분석**: 이슈에 arXiv 논문 주소(`arxiv.org/abs/...`)를 입력하면 PDF 원문
  URL 로 자동 변환되어, 모델이 URL 컨텍스트 도구로 **논문 전문을 직접 읽고** 라이선스·데이터
  수집 방법 조항을 원문 그대로 인용합니다.

## 구성 요소

| 경로 | 설명 |
| --- | --- |
| `docs/` | GitHub Pages로 배포되는 입력 홈페이지 (`index.html`, `app.js`, `style.css`, `config.js`) |
| `.github/ISSUE_TEMPLATE/dataset-review.yml` | 검토 요청 이슈 폼 (홈페이지가 이 폼을 prefill) |
| `.github/workflows/dataset-review.yml` | 이슈 생성 시 검토를 실행하는 GitHub Actions 워크플로 |
| `scripts/review.py` | Gemini 호출 + 검토 보고서 생성 스크립트 |
| `scripts/system_prompt.md` | 법적 리스크 검토 에이전트 시스템 프롬프트(검토 지침) |
| `tools/gemini_api_key_test.sh` | Gemini API 키 동작을 curl 로 확인하는 진단 스크립트 |

## 설정 방법 (1회)

> 아래 1~4단계를 마치면 바로 사용할 수 있습니다. 각 단계 끝의 ✅ 확인 방법으로 검증하세요.

### 1. Google AI Studio API 키 발급
1. <https://aistudio.google.com/apikey> 에서 무료 API 키 발급 (Google 계정만 있으면 무료·카드 등록 불필요)
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: 발급받은 키
3. (선택) 모델 변경 시 **Variables** 탭에서 `GEMINI_MODEL` 추가 (기본값 `gemini-2.5-flash`)
   - 무료 티어에서 일일 검토 가능 건수를 늘리려면 `gemini-2.5-flash-lite` 를 고려하세요.
     ([무료 티어 한도](#무료-티어-한도와-하루-검토-가능-건수) 참고)

✅ 확인: `./tools/gemini_api_key_test.sh <API_KEY>` 실행 → 초록색 ✓ 가 나오면 키 정상.

### 2. GitHub Pages 활성화
- **Settings → Pages → Source: Deploy from a branch**
- Branch: `main` / 폴더: `/docs` 선택 후 저장
- 배포 URL: `https://<owner>.github.io/<repo>/` (본 저장소: <https://aigovsensing.github.io/dataset-review/>)

✅ 확인: 배포 URL 접속 시 "검토 요청" 입력 폼이 보이면 정상 (반영까지 1~2분 소요).

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

✅ 확인: 저장소 **Issues → Labels** 에 위 5개 라벨이 보이면 정상.

### 5. 다른 저장소로 재배포하는 경우
- 이 저장소를 Fork(또는 Use this template)한 뒤, `docs/config.js` 의 `owner` / `repo` 값을 수정합니다.
- 위 1~4번(API 키 Secret, Pages, Actions 권한, 라벨 생성)을 새 저장소에서도 수행합니다.

## 사용 방법

1. **검토 요청** — 홈페이지(GitHub Pages)의 **검토 요청** 탭에서 데이터셋 명칭(필수)과
   논문 주소, 공식 홈페이지, 관련 소송 URL 등을 입력하고 **"검토 요청 (GitHub 이슈 생성)"**
   버튼을 누릅니다. 폼 내용이 미리 채워진 GitHub 이슈 작성 페이지가 열리며, 여기서
   **Create issue** 를 눌러야 이슈가 실제로 생성됩니다. (GitHub 로그인 필요)
2. **자동 검토** — 이슈가 생성되면 GitHub Actions 가 즉시 실행됩니다. 별도의 승인 절차는
   없으며, 보통 1~3분 뒤 검토 보고서가 이슈 댓글로 등록되고 `reviewed` 라벨이 붙습니다.
   - ⚠️ 단, **이슈 작성자가 저장소 소유자/멤버/협력자(collaborator)** 인 경우에만 검토가
     실행됩니다(무료 API 쿼터 보호). 외부 사용자의 이슈는 자동으로 건너뜁니다.
3. **결과 열람** — 홈페이지의 **검토 결과** 탭 또는 GitHub 이슈에서 직접 확인합니다.
   보고서 최상단의 **종합의견**은 요청자에게 그대로 복사·회신할 수 있는 요약문입니다.
4. **재검토** — 입력을 수정했거나 결과가 미흡하면 이슈에 `rerun-review` 라벨을 붙이세요.
   해당 이슈만 다시 검토됩니다. (Gemini 호출이 1회 추가되므로 필요할 때만 사용)

### 입력 팁: 논문 주소는 arXiv `abs` 주소로

논문 주소에 `https://arxiv.org/abs/xxxx.xxxxx` 형식을 입력하면 시스템이 PDF 원문 URL 을
자동 생성하여 모델이 **논문 전문을 직접 읽습니다**. 라이선스 조항·데이터 수집 방법·개인정보
처리 서술을 원문에서 직접 인용하므로 검토 품질이 크게 올라갑니다. 여러 논문은 줄바꿈으로
구분해 입력합니다.

## 라벨

| 라벨 | 의미 |
| --- | --- |
| `dataset-review` | 검토 요청 이슈 (트리거). **사전 생성 필요** — 이슈 폼이 이 라벨을 부여 |
| `reviewing` | 검토 진행 중 (워크플로가 자동 부여/제거) |
| `reviewed` | 검토 완료 (워크플로가 자동 부여) |
| `review-failed` | 검토 실패 — API 키/쿼터 등 확인 필요 (워크플로가 자동 부여) |
| `rerun-review` | 이 라벨을 추가하면 재검토를 강제 실행 |

## 💰 무료 Gemini API 안정 운영 (호출 최소화 설계)

이 프로젝트는 **Google AI Studio 무료 API 키**로 운영되는 것을 전제로 설계되었습니다.
핵심 원칙은 두 가지입니다.

1. **검토 1건 = Gemini API 호출 정확히 1회.** 그 이상은 어떤 경로로도 발생하지 않습니다.
2. **AI 없이 구현 가능한 기능은 전부 일반 코드로 구현.** Gemini 는 오직 "법적 리스크 판단"
   한 곳에만 사용합니다.

### AI 를 쓰지 않는 부분 (일반 코드로 구현된 기능)

| 기능 | 구현 위치 | 방식 |
| --- | --- | --- |
| 이슈 폼 파싱 (명칭·URL 추출) | `scripts/review.py` `parse_issue_body()` | 정규식 |
| 입력 사전 검증 (빈 이슈 차단) | `scripts/review.py` `run_review()` | 필드 검사 — 검토할 정보가 없으면 **API 호출 없이** 즉시 실패 처리 |
| arXiv 논문 PDF URL 변환 | `scripts/review.py` `arxiv_pdf_variants()` | 정규식 (`/abs/` → `/pdf/`) |
| 인용 번호 → 출처 링크 변환 | `scripts/review.py` `linkify_citations()` | 정규식 |
| 보고서 재구성 (배지·접이식 섹션) | `scripts/review.py` `restructure_review()` | 문자열 처리 |
| 판정(✅/⚠️/⛔) 추출·배너 생성 | `scripts/review.py` `detect_verdict()` | 패턴 매칭 |
| 검토 결과 목록·홈페이지 | `docs/` | 정적 페이지 + GitHub REST API (Gemini 무관) |
| 라벨 관리·댓글 등록 | 워크플로 | `gh` CLI (Gemini 무관) |

### 호출 횟수를 줄이는 장치

- **트리거 권한 제한 (핵심):** 이슈 작성자가 저장소 `OWNER` / `MEMBER` / `COLLABORATOR`
  인 경우에만 검토를 실행합니다(`author_association` 검사). 외부인이 이슈를 열어도 검토(=Gemini 호출)가
  실행되지 않습니다. 사외 사용자에게도 개방하려면 `.github/workflows/dataset-review.yml` 의 `if`
  조건에서 이 검사를 완화하세요.
- **이벤트당 정확히 1회 실행:** 이슈 `opened` 시 1회, 이후에는 `rerun-review` 라벨을 붙였을
  때만 재실행됩니다. 워크플로가 스스로 붙이는 `reviewing`/`reviewed` 라벨 이벤트는 실행
  조건에서 제외되어 자기 자신을 재트리거하지 않습니다.
- **중복 실행 방지:** `reviewed` 라벨이 붙은 이슈는 재검토되지 않습니다(재검토는 `rerun-review` 라벨로만).
- **동시 실행 직렬화:** `concurrency` 설정으로 같은 이슈의 중복 이벤트를 취소해 이중 호출을 막습니다.
- **빈 입력 차단:** 데이터셋 명칭과 URL 이 모두 비어 있는 이슈는 Gemini 를 호출하지 않고
  실패 댓글만 남깁니다.
- **재시도는 일시 오류에만:** 503/429 등 일시 오류는 지수 백오프로 최대 3회 재시도합니다.
  거절된 요청은 무료 쿼터를 소진하지 않으므로 안전하며, 그 외 오류는 즉시 중단합니다.

### 무료 티어 한도와 하루 검토 가능 건수

검토 1건 = 1회 호출이므로, **하루 검토 가능 건수 ≈ 모델의 일일 요청 한도(RPD)** 입니다.
(한도는 변동될 수 있으니 [공식 문서](https://ai.google.dev/gemini-api/docs/rate-limits)에서 확인하세요.)

| 모델 (`GEMINI_MODEL`) | 분당 요청(RPM) | 일일 요청(RPD) | 비고 |
| --- | --- | --- | --- |
| `gemini-2.5-flash` (기본값) | ~10 | ~250 | 품질·쿼터 균형이 좋아 기본값으로 권장 |
| `gemini-2.5-flash-lite` | ~15 | ~1,000 | 검토량이 많을 때. 품질은 다소 낮아질 수 있음 |
| `gemini-2.5-pro` | ~5 | ~100 | 가장 정밀하지만 무료 한도가 작음 |

**운영 팁**

- 일반적인 사내 검토량(하루 수~수십 건)이라면 기본값 `gemini-2.5-flash` 무료 한도로 충분합니다.
- `rerun-review` 는 호출 1회를 추가로 소모하므로, 입력을 확실히 보완한 뒤에 사용하세요.
- `review-failed` 라벨이 붙고 오류 댓글에 `429` / `RESOURCE_EXHAUSTED` 가 보이면 일일 한도
  소진입니다. 다음 날(태평양 시간 자정 리셋) `rerun-review` 로 재시도하면 됩니다.

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

### 이슈를 만들었는데 검토가 실행되지 않는 경우

Actions 탭에서 워크플로가 `Skipped` 라면 실행 조건 미충족입니다. 순서대로 확인하세요.

1. **이슈에 `dataset-review` 라벨이 있는가?** — 없다면 저장소에 라벨이 미리 생성되지 않은
   것입니다. [설정 4번](#4-라벨-생성-필수-)으로 라벨을 만들고, 기존 이슈에 라벨을 수동으로
   붙인 뒤 `rerun-review` 라벨을 추가하세요.
2. **이슈 작성자가 소유자/멤버/협력자인가?** — 외부 사용자의 이슈는 쿼터 보호를 위해
   실행되지 않습니다(작성자 기준이므로, 관리자가 라벨을 대신 붙여도 실행되지 않습니다).
3. 워크플로가 실행됐는데 실패했다면 이슈의 오류 댓글과 Actions 로그를 확인하세요.

### `review-failed` 라벨이 붙은 경우

이슈의 오류 댓글에서 원인을 확인할 수 있습니다.

| 오류 메시지 | 원인 | 조치 |
| --- | --- | --- |
| `GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다` | Secret 미등록 | 설정 1번 수행 |
| `429` / `RESOURCE_EXHAUSTED` | 무료 일일 한도 소진 | 다음 날 `rerun-review` |
| `503` / `high demand` (재시도 후에도 실패) | Google 서버 혼잡 | 잠시 후 `rerun-review` |
| `검토할 데이터셋 정보가 없습니다` | 이슈 폼이 비어 있음 | 이슈 본문 수정 후 `rerun-review` |
| `Gemini 응답이 비어 있습니다` | 모델이 답변 없이 종료 | `rerun-review` 로 재시도 |

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

#### 선택: 본인 GitHub 토큰으로 한도 올리기 (60 → 5,000회/시간)

검토 결과 탭의 **🔑 인증** 버튼(한도 초과 시 자동으로 열림)에서 본인의 GitHub 토큰을 입력하면
해당 브라우저에서의 목록 조회 한도가 **시간당 5,000회**로 올라갑니다.

- **토큰 생성:** [github.com/settings/tokens/new](https://github.com/settings/tokens/new) —
  공개 저장소 조회에는 **권한(scope)이 필요 없으므로** 스코프를 선택하지 않은(read-only) 토큰이 가장 안전합니다.
- **저장 위치:** 토큰은 **사용자 브라우저의 `localStorage`(`dr_github_token`)에만** 저장되고 GitHub API
  호출의 `Authorization` 헤더로만 사용됩니다. **저장소에 커밋되거나 외부로 전송되지 않습니다.**
- **주의:** 토큰을 브라우저에 두는 것이므로 **공용 PC에서는 사용 후 반드시 "삭제"** 하세요. 잘못된/만료된
  토큰은 401로 안내되며, 다시 입력하거나 삭제할 수 있습니다.
- 이 방식은 개별 사용자가 스스로 선택하는 옵션입니다. 서버나 페이지에 공용 토큰을 심지 않는 이유는,
  정적 페이지에 토큰을 두면 누구나 열람·악용할 수 있어 보안상 부적절하기 때문입니다.

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
- URL 컨텍스트 도구로 이슈에 입력된 논문(arXiv PDF 포함)·홈페이지 원문을 모델이 직접 읽습니다.
  Actions 로그의 `[diag] url_context:` 줄에서 각 URL 의 조회 성공/실패 상태를 확인할 수 있습니다.
- API 키 동작 확인은 `tools/gemini_api_key_test.sh` 로 테스트할 수 있습니다.
- 검토 결과 맨 위에는 요청자에게 바로 복사·회신할 수 있는 **`종합의견`**(라이선스·수집방법·개인정보
  3줄 요약 + 리스크 결론)이 표시되며, 상세 분석은 그 아래 접이식 섹션으로 정리됩니다.

## 라이선스

이 프로젝트는 [Apache License 2.0](LICENSE) 하에 배포됩니다.

> 🍺 **The Beer Clause (선택 사항, 법적 효력 없음):**
> 이 프로젝트가 마음에 들고 언젠가 제작자를 만나게 된다면, 맥주 한잔 사주셔도 좋습니다.
> 물론 의무는 아닙니다 — 정식 라이선스는 위의 Apache 2.0 입니다. 🍻
> _("법적 리스크 검토" 도구가 법적으로 모호한 Beerware를 쓸 수는 없어, 안전한 Apache 2.0 에 재미만 얹었습니다.)_
