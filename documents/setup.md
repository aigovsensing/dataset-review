[← README](../README.md)

# 설정 방법 (Setup)

<sub>문서: [architecture](architecture.md) · **setup** · [usage](usage.md) · [models-and-quota](models-and-quota.md) · [litigation](litigation.md) · [troubleshooting](troubleshooting.md) · [development](development.md)</sub>

---

## 설정 방법 (1회)

> 아래 1~4단계를 마치면 바로 사용할 수 있습니다. 각 단계 끝의 ✅ 확인 방법으로 검증하세요.

### 1. Google AI Studio API 키 발급
1. <https://aistudio.google.com/apikey> 에서 무료 API 키 발급 (Google 계정만 있으면 무료·카드 등록 불필요)
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: 발급받은 키
3. (권장) 여러 계정의 무료 키를 쓰려면 `GEMINI_API_KEY_<이름>` 형식으로 추가합니다.
   예: `GEMINI_API_KEY_AIGOVSENSING`, `GEMINI_API_KEY_GEUNSIKLIM`, `GEMINI_API_KEY_LEEMGS`.
   - Actions에서는 `GEMINI_API_KEY` → `GEMINI_API_KEY_LEEMGS` →
     `GEMINI_API_KEY_GEUNSIKLIM` → `GEMINI_API_KEY_AIGOVSENSING` →
     `GEMINI_API_KEY_AITSEC2025` 순으로 시도합니다. 로컬 실행은
     `GEMINI_API_KEY_ORDER`가 없으면 변수명 영문 오름차순을 사용합니다.
   - 중복된 키 값은 한 번만 시도합니다.
   - 한 키의 모델 폴백 체인까지 **쿼터(429) 또는 인증(401/403) 오류**로 실패하면 다음 키로 전환합니다. 5xx·잘못된 입력 등 키와 무관한 오류는 추가 키를 소진하지 않도록 순회하지 않습니다.
   - 이슈 댓글에는 실패한 Secret **변수명만** 출력하고 키 값은 출력하지 않습니다.
4. (선택) 모델은 기본값 `gemini-flash-latest`(최신 Flash 자동)로 동작합니다. 버전 고정·변경은
   **Variables** 탭에 `GEMINI_DEFAULT_MODEL` 을 추가하세요. → [모델 선택과 무료 한도](models-and-quota.md#모델-선택과-무료-한도-gemini_default_model) 참고.

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
gh label create dataset-review --repo $R --color 1d76db --description "데이터셋 검토 요청 (트리거)" --force
gh label create paper-review   --repo $R --color 8250df --description "연구논문 검토 요청 (트리거)" --force
gh label create reviewing      --repo $R --color fbca04 --description "검토 진행 중" --force
gh label create reviewed       --repo $R --color 0e8a16 --description "검토 완료" --force
gh label create review-failed  --repo $R --color d73a4a --description "검토 실패" --force
gh label create rerun-review   --repo $R --color 5319e7 --description "재검토 강제 실행" --force
```

✅ 확인: 저장소 **Issues → Labels** 에 위 6개 라벨이 보이면 정상.

> **검토 유형 2가지:** 이 저장소는 **데이터셋 검토**(`dataset-review` 라벨 → `scripts/dataset_review.py`)와
> **연구논문 법무 검토**(`paper-review` 라벨 → `scripts/paper_review.py`) 두 워크플로를 제공합니다.
> 홈페이지 상단의 **🗂️ 데이터셋 리뷰 / 📄 논문 리뷰** 전환 버튼으로 각 요청 폼·결과 목록을 이용합니다.
> 논문 검토는 PDF 링크(원문 직접 판독) 또는 논문 웹페이지 URL 을 입력받아 **개인정보 · 저작권 ·
> 데이터셋 검증(외부 Dataset 사용 vs 자체 생성 데이터)** 을 논문 원문 기반으로 검토합니다.

### 5. 접근 암호 설정 (선택, 약한 게이트)

홈페이지에 아무나 접속하지 못하도록 최소한의 접근 암호를 걸 수 있습니다.
기본 암호는 `guest2848` 입니다. 암호를 바꾸려면 SHA-256 해시를 계산해 `docs/config.js` 의
`authHash` 값을 교체하세요.

```bash
printf '%s' '새암호' | sha256sum   # 출력된 해시를 docs/config.js 의 authHash 에 붙여넣기
```

- 게이트를 끄려면 `authHash` 를 `""` 로 둡니다.
- 인증되면 해당 브라우저(`localStorage`)에 기억되어 다시 묻지 않습니다.
- ⚠️ **이것은 실제 보안이 아닙니다.** 정적 페이지 특성상 소스(해시)가 공개되므로
  마음먹은 사용자는 우회할 수 있는 **단순 차단 장치**입니다. 민감 정보 보호 용도로는
  부적합하며, "아무나 우연히 접속" 을 막는 정도로만 사용하세요. (검토 내용 자체는 GitHub
  이슈에 있고, 결과 목록도 GitHub API 로 조회되므로 이 게이트로 보호되지 않습니다.)

### 6. 다른 저장소로 재배포하는 경우
- 이 저장소를 Fork(또는 Use this template)한 뒤, `docs/config.js` 의 `owner` / `repo` 값을 수정합니다.
- 위 1~4번(API 키 Secret, Pages, Actions 권한, 라벨 생성)을 새 저장소에서도 수행합니다.
