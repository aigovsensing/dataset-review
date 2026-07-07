// 저장소 정보 설정. 다른 저장소에 재배포하는 경우 이 값만 수정하면 됩니다.
window.DATASET_REVIEW_CONFIG = {
  owner: "aigovsensing",
  repo: "dataset-review",
  // 이슈 폼 템플릿 파일명 (.github/ISSUE_TEMPLATE/ 하위)
  template: "dataset-review.yml",
  // 검토 요청 이슈에 부여되는 라벨
  label: "dataset-review",

  // ── 간이 접근 암호(약한 게이트) ──────────────────────────────────────
  // 정적 페이지라 실제 보안이 아니라 "아무나 접속" 차단용 최소 장치입니다.
  // 암호 평문을 저장소에 두지 않도록 SHA-256 해시만 보관합니다.
  // 암호 변경: 터미널에서  printf '%s' '새암호' | sha256sum  실행 후 아래 값 교체.
  // 게이트를 끄려면 authHash 를 "" 로 두세요.
  authHash: "a05f757677aa59387f11e957a42ed160dfab5539f7ce9f968daa66b7a29c0950", // guest2848
  authHint: "관리자에게 문의하여 접근 암호를 받으세요.",
};
