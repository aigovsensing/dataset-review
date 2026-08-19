[← README](../README.md)

# 사용 방법 · 결과 내보내기 · 라벨 (Usage)

<sub>문서: [architecture](architecture.md) · [setup](setup.md) · **usage** · [models-and-quota](models-and-quota.md) · [litigation](litigation.md) · [troubleshooting](troubleshooting.md) · [development](development.md)</sub>

---

## 사용 방법

1. **검토 요청** — 홈페이지(GitHub Pages)의 **검토 요청** 탭에서 데이터셋 명칭(필수)과
   논문 주소, 공식 홈페이지, 관련 소송 URL 등을 입력하고 **"검토 요청 (GitHub 이슈 생성)"**
   버튼을 누릅니다. 폼 내용이 미리 채워진 GitHub 이슈 작성 페이지가 열리며, 여기서
   **Create issue** 를 눌러야 이슈가 실제로 생성됩니다. (GitHub 로그인 필요)
   - ♻️ **중복 방지**: 같은 데이터셋 명칭이 이미 검토되어 이슈로 등록되어 있으면, 홈페이지가
     신규 이슈 작성 페이지를 열지 않고 **기존 이슈 주소**를 안내합니다. 다시 검토하려면
     안내된 이슈로 이동해 `rerun-review` 라벨을 추가(체크)하세요(중복 검토·쿼터 낭비 방지).
     동명의 다른 데이터셋이라면 안내창의 **‘그래도 새 이슈로 요청’** 으로 새로 등록할 수 있습니다.
2. **자동 검토** — 이슈가 생성되면 GitHub Actions 가 즉시 실행됩니다. 별도의 승인 절차나
   작성자 권한 제한이 **없으며**, 누구나 연 이슈가 자동으로 검토됩니다. 보통 1~3분 뒤
   검토 보고서가 이슈 댓글로 등록되고 `reviewed` 라벨이 붙습니다.
   - ⚠️ 개방형 운영이므로 외부인의 무분별한 이슈가 Gemini 무료 쿼터를 소진할 수 있습니다.
     제한이 필요하면 워크플로의 `author_association` 게이트를 복구하세요.
3. **결과 열람** — 홈페이지의 **검토 결과** 탭 또는 GitHub 이슈에서 직접 확인합니다.
   보고서 최상단의 **종합의견**은 요청자에게 그대로 복사·회신할 수 있는 요약문입니다.
   - 🔍 **검색**: 데이터셋 명칭·제목으로 목록을 필터링할 수 있습니다.
   - 📄 **게시판/페이지네이션**: 기본 한 페이지 10건씩 보이며, **페이지당 개수**를
     5·10·15·20·30·50·100 중에서 고르고 이전/다음으로 페이지를 넘길 수 있습니다.
   - 📊 **대시보드**: **대시보드** 탭에서 검토 현황을 한눈에 봅니다. 판정별 건수(사용 가능/
     추가 검토 필요/사용 비권고), **내부 판단 분포 도넛**, **검토 항목별(라이선스·수집·개인정보)
     리스크 스택 막대**, **검토 추이**, 그리고 데이터셋별 표에서 행을 펼치면 종합의견의
     **확인 결과 · 내부 판단 · 판단 근거**를 열람할 수 있습니다(판정 필터·검색·게시판 지원,
     기본 5건/페이지, 5·10·15·30·50·70·100 선택). 집계 데이터(`docs/data/reviews.json`)는
     만족도 레이블 변경 시 자동 반영되며, 매일 정기 갱신도 실행됩니다.
   - ⚖️ **소송이 걸려있는 데이터셋 현황**: 대시보드 상단에 소송·법적 분쟁 이력이 확인된
     데이터셋을 **사건명 · 사건번호 · 원고 · 피고 · 침해 입증 근거 강도(강/중/약)** 표로 모아
     보여줍니다. 행을 펼치면 **법원 · 사건 상태 · 침해 주장 요지 · 원고가 어떻게 알아냈는가(판단
     기준) · 소장 항 번호 · 소장 원문 인용 · 내부 판단 · 판단 근거**까지 열람할 수 있습니다.
     이 정보는 검토 보고서의 「3. 소송 리스크」 섹션에서 자동 파싱되어 집계됩니다.
   - 🔗 **메뉴별 공유 링크**: 탭 우측의 **🔗 공유** 버튼을 누르면 각 메뉴로 바로 열리는
     주소를 복사할 수 있습니다. 주소 끝의 해시로 메뉴가 결정됩니다 —
     `…/#request`(검토 요청) · `…/#results`(검토 결과) · `…/#dashboard`(대시보드) ·
     `…/#how`(이용 안내). 예: `https://aigovsensing.github.io/dataset-review/#dashboard`
4. **재검토** — 입력을 수정했거나 결과가 미흡하면 이슈에 `rerun-review` 라벨을 붙이세요.
   해당 이슈만 다시 검토됩니다. (Gemini 호출이 1회 추가되므로 필요할 때만 사용)

### 입력 팁: 논문·공식 URL 을 함께 입력하면 정확도가 올라갑니다

논문 주소(예: `https://arxiv.org/abs/xxxx.xxxxx`), 공식 홈페이지, LICENSE/Terms, GitHub·
Hugging Face 주소를 입력하면 Gemini 가 Google 검색 그라운딩으로 그 자료들을 우선적으로
찾아 라이선스 조항·데이터 수집 방법·개인정보 처리 서술을 원문 근거와 함께 인용합니다.
URL 이 구체적일수록 검토 품질이 올라갑니다. 여러 개는 줄바꿈으로 구분해 입력합니다.

### 논문 주소(arXiv)는 어떻게 분석되나?

> **결론부터**: 코드가 arXiv PDF 를 직접 다운로드·파싱하지는 **않습니다.** 그 URL 을 Gemini 에
> 넘겨, **Gemini 가 Google 검색 그라운딩으로 논문을 찾아 분석·인용**하도록 되어 있습니다.

**처리 흐름 (arXiv 주소 입력 시)**

1. **폼에서 URL 추출 (코드, AI 아님)** — [`parse_issue_body()`](../scripts/dataset_review.py#L31)가 이슈 본문의
   `### 논문 주소 (URL)` 섹션을 정규식으로 파싱해 `fields["paper_urls"]` 에 담습니다.
2. **프롬프트에 URL 그대로 삽입** — [`build_user_prompt()`](../scripts/dataset_review.py#L82):
   ```python
   if fields.get("paper_urls"):
       lines.append(f"- 논문 주소: {fields['paper_urls']}")
   ```
   arXiv 전용 처리(PDF 변환·다운로드)는 없습니다. URL 을 텍스트로 넣고, "Google 검색 도구로 논문 등
   공식 자료를 직접 확인 · 이 URL 을 우선 근거로 활용 · 인용 시 출처 URL 함께 제시"라고 지시합니다.
3. **시스템 지침이 논문 활용 방식을 규정** — [`system_prompt_dataset_review.md`](../prompt-book/system_prompt_dataset_review.md#L27):
   *"논문·공식 홈페이지·LICENSE… URL 이 제공되면 Google 검색 도구로 해당 자료를 우선적으로 찾아,
   라이선스 조항·데이터 수집 방법(크롤링·출처·필터링)·개인정보 서술을 원문에서 확인하고 그 문장을
   그대로 인용한다."* → 논문에서 **라이선스 / 데이터 수집 방식 / 개인정보** 3대 항목의 근거를 찾습니다.
4. **Gemini 1회 호출 (google_search 그라운딩)** — [`dataset_review.py`](../scripts/dataset_review.py#L478):
   ```python
   tools = [types.Tool(google_search=types.GoogleSearch())]
   ```
   Gemini 가 이 도구로 arXiv 논문(및 관련 공식 자료)을 **실제 검색·열람해 분석**합니다. 논문 내용을
   이해하는 "분석"은 여기서 일어납니다.
5. **후처리로 인용을 링크화 (코드, AI 아님)** — Gemini 가 근거 문장 끝에 `[cite: N]` 을 붙이면
   ([`system_prompt_dataset_review.md`](../prompt-book/system_prompt_dataset_review.md#L54)), `linkify_citations()` 가 그 번호를 실제
   출처 URL 링크로 변환하고 그라운딩 출처 목록을 결과 하단에 첨부합니다.

**참고 (이력):** 과거 두 방식을 시도했다가 무료 티어 안정성 문제로 되돌렸습니다.
- `url_context` 도구(모델이 PDF 원문을 직접 읽기) → 대용량 논문 PDF 에서 **빈 응답 실패**
- arXiv API 로 초록을 코드로 가져와 주입 → 모델이 초록을 출력에 되풀이하는 **무한 반복 루프**

그래서 현재는 가장 안정적인 **google_search 그라운딩 단독** 방식입니다. 정리하면 — arXiv URL 은
"Gemini 에게 이 논문을 찾아 근거로 쓰라"는 **지시의 입력**으로 쓰이고, 실제 논문 읽기·분석은
Gemini 의 Google 검색 그라운딩이 수행하며, 코드는 그 앞뒤(URL 추출·인용 링크화·출처 첨부)를 담당합니다.

## 검토 결과 내보내기 (CSV · 대시보드/집계용)

모든 검토 결과를 **CSV/JSON 으로 집계**할 수 있습니다. [`scripts/export_dataset_reviews.py`](../scripts/export_dataset_reviews.py)
가 `dataset-review` 이슈들을 모아 각 검토 댓글에서 구조화 필드를 파싱해
`docs/data/reviews.csv` (Excel 한글 호환 UTF-8 BOM) 와 `docs/data/reviews.json` 을 생성합니다.
JSON에는 실제 집계 완료 시각인 `exported_at`과 검토 결과 배열 `rows`가 저장됩니다.

**컬럼**: `issue, dataset, verdict(판정), model, status, review_confidence(자동리뷰 만족도), license_check/judgment,
collection_check/judgment, privacy_check/judgment, litigation(소송 여부), author, created_at, updated_at, url`

- **자동 갱신**: [`export-reviews.yml`](../.github/workflows/export-reviews.yml) 워크플로가 **이슈 레이블 변경 시와 매일**(및 수동
  `Run workflow`) 실행되어 CSV 를 커밋합니다.
- **다운로드**: 홈페이지 **검토 결과** 탭의 **⬇️ CSV** 버튼(= `data/reviews.csv`) 또는 저장소에서 직접 받습니다.
- **로컬 실행**:
  ```bash
  GITHUB_TOKEN=$(gh auth token) GITHUB_REPOSITORY=<owner>/<repo> python scripts/export_dataset_reviews.py
  ```
- 최신 형식(불릿·4열 표)과 구버전(파이프 표) 검토 댓글을 모두 파싱합니다. 매우 오래된 일부 형식은
  판정·데이터셋만 채워질 수 있으며, 해당 이슈를 `rerun-review` 로 재검토하면 항목 필드까지 채워집니다.

## 라벨

| 라벨 | 의미 |
| --- | --- |
| `dataset-review` | 검토 요청 이슈 (트리거). **사전 생성 필요** — 이슈 폼이 이 라벨을 부여 |
| `reviewing` | 검토 진행 중 (워크플로가 자동 부여/제거) |
| `reviewed` | 검토 완료 (워크플로가 자동 부여) |
| `review-failed` | 검토 실패 — API 키/쿼터 등 확인 필요 (워크플로가 자동 부여) |
| `rerun-review` | 이 라벨을 추가하면 재검토를 강제 실행 |
