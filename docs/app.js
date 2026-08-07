(function () {
  "use strict";

  const cfg = window.DATASET_REVIEW_CONFIG || {};
  const { owner, repo, template, label } = cfg;
  const repoUrl = `https://github.com/${owner}/${repo}`;

  const $ = (sel) => document.querySelector(sel);
  const fieldIds = [
    "dataset-name",
    "related-datasets",
    "paper-urls",
    "homepage-url",
    "litigation-url",
    "extra-notes",
  ];

  // ---- 낮/밤 테마 토글 ----
  const root = document.documentElement;
  const themeToggle = $("#theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {
        /* localStorage 사용 불가 시 무시 */
      }
    });
  }

  // ---- GitHub 토큰(선택): 비인증 60회/시간 → 인증 5,000회/시간 ----
  const TOKEN_KEY = "dr_github_token";
  function getToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  }
  function setToken(v) {
    try {
      if (v) localStorage.setItem(TOKEN_KEY, v);
      else localStorage.removeItem(TOKEN_KEY);
    } catch (e) {
      /* localStorage 사용 불가 시 무시 */
    }
  }
  function apiHeaders() {
    const h = { Accept: "application/vnd.github+json" };
    const t = getToken();
    if (t) h.Authorization = `Bearer ${t}`;
    return h;
  }

  function setAuthStatus(text, kind) {
    const el = $("#auth-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "dim" + (kind ? " " + kind : "");
  }
  function updateAuthUI() {
    const btn = $("#auth-btn");
    const authed = !!getToken();
    if (btn) btn.textContent = authed ? "🔑 인증됨" : "🔑 인증";
    const input = $("#gh-token");
    if (input && authed) input.placeholder = "저장된 토큰 사용 중 (다시 입력하면 교체)";
    setAuthStatus(
      authed ? "인증 토큰이 저장되어 있습니다 (시간당 5,000회)." : "",
      authed ? "ok" : ""
    );
  }

  const authBtn = $("#auth-btn");
  const authPanel = $("#auth-panel");
  if (authBtn && authPanel) {
    authBtn.addEventListener("click", () => {
      authPanel.hidden = !authPanel.hidden;
    });
  }
  const authSave = $("#auth-save");
  if (authSave) {
    authSave.addEventListener("click", () => {
      const input = $("#gh-token");
      const val = input ? input.value.trim() : "";
      if (!val) {
        setAuthStatus("토큰을 입력하세요.", "err");
        return;
      }
      setToken(val);
      if (input) input.value = "";
      updateAuthUI();
      setAuthStatus("토큰을 저장했습니다. 목록을 다시 불러옵니다…", "ok");
      loadResults(true);
    });
  }
  const authClear = $("#auth-clear");
  if (authClear) {
    authClear.addEventListener("click", () => {
      setToken("");
      const input = $("#gh-token");
      if (input) {
        input.value = "";
        input.placeholder = "github_pat_... 또는 ghp_...";
      }
      updateAuthUI();
      setAuthStatus("토큰을 삭제했습니다. 비인증 상태(시간당 60회)로 조회합니다.", "");
      loadResults(true);
    });
  }
  updateAuthUI();

  // ---- 저장소 링크 ----
  const repoLink = $("#repo-link");
  if (repoLink) repoLink.href = repoUrl;

  // ---- 탭 전환 (URL 해시 기반 딥링크: #request/#results/#dashboard/#how) ----
  const TAB_LABELS = {
    request: "📝 검토 요청",
    results: "📋 검토 결과",
    dashboard: "📊 대시보드",
    how: "ℹ️ 이용 안내",
    "paper-request": "📝 논문 검토 요청",
    "paper-results": "📋 논문 검토 결과",
    "paper-how": "ℹ️ 논문 이용 안내",
  };
  const VALID_TABS = Object.keys(TAB_LABELS);

  // 검토 유형(모드) 판별: paper-* 탭이면 논문 모드, 그 외 데이터셋 모드.
  function deriveMode(tab) {
    return String(tab || "").indexOf("paper") === 0 ? "paper" : "dataset";
  }

  // 대시보드 세부 메뉴 딥링크: #dashboard/<section>
  //   #dashboard/stats, /litigation, /charts, /trend, /table, /confidence
  const DASH_SECTION_LABELS = {
    stats: "🧭 검토 현황",
    litigation: "⚖️ 소송 현황",
    charts: "📈 시각화",
    trend: "🗓️ 검토 추이",
    table: "🗂️ 데이터셋별 결과",
    confidence: "💬 만족도",
  };
  const DASH_SECTIONS = Object.keys(DASH_SECTION_LABELS);

  // 해시를 { tab, sub } 로 분해. 예) "#dashboard/litigation" → { tab, sub }
  function parseHash() {
    const parts = (location.hash || "").replace(/^#/, "").split("/");
    const tab = VALID_TABS.includes(parts[0]) ? parts[0] : "dashboard";
    return { tab, sub: parts[1] || "" };
  }
  function currentTab() {
    return parseHash().tab;
  }
  function tabUrl(tab, sub) {
    const frag = sub ? `${tab}/${sub}` : tab;
    return location.origin + location.pathname + "#" + frag;
  }
  function applyTabFromHash() {
    const { tab: target, sub } = parseHash();
    const mode = deriveMode(target);
    // 검토 유형(모드) 반영: 해당 모드의 nav/패널만 노출
    root.setAttribute("data-mode", mode);
    document.querySelectorAll("[data-mode-btn]").forEach((b) =>
      b.classList.toggle("active", b.getAttribute("data-mode-btn") === mode)
    );
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === target));
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `tab-${target}`);
    });
    if (target === "results") loadResults();
    if (target === "paper-results") loadPaperResults();
    if (target === "dashboard") {
      const wantSub = sub && DASH_SECTIONS.includes(sub) ? sub : null;
      if (wantSub) dashState.section = wantSub; // 첫 렌더 시 이 섹션이 열리도록
      const wasLoaded = dashState.loaded;
      loadDashboard();
      // 이미 렌더된 상태면(재방문/해시 변경) 해당 섹션으로 즉시 전환
      if (wasLoaded && wantSub) activateDashSection(wantSub);
    }
  }

  // 검토 유형(모드) 전환 버튼: 해당 모드의 기본 탭으로 이동.
  document.querySelectorAll("[data-mode-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const m = btn.getAttribute("data-mode-btn");
      if (deriveMode(currentTab()) === m) return; // 이미 해당 모드면 무시
      location.hash = m === "paper" ? "paper-request" : "dashboard";
    });
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      if ("#" + target === location.hash) applyTabFromHash(); // 같은 탭 재클릭 시에도 상태 보정
      else location.hash = target; // hashchange 이벤트가 applyTabFromHash 를 호출
    });
  });
  window.addEventListener("hashchange", applyTabFromHash);

  // ---- 메뉴별 공유 링크 ----
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {
      /* 아래 폴백 사용 */
    }
    return false;
  }

  // 공유 대상 목록: 상위 탭 + 대시보드 세부 메뉴(딥링크)
  function shareTargets() {
    const list = [];
    VALID_TABS.forEach((t) => {
      list.push({ label: TAB_LABELS[t], url: tabUrl(t) });
      if (t === "dashboard") {
        DASH_SECTIONS.forEach((s) => {
          list.push({ label: "↳ " + DASH_SECTION_LABELS[s], url: tabUrl("dashboard", s) });
        });
      }
    });
    return list;
  }

  function buildShareMenu() {
    const menu = $("#share-menu");
    if (!menu) return;
    const rows = shareTargets().map((it) =>
      `<div class="share-row">` +
      `<span class="sr-label">${escapeHtml(it.label)}</span>` +
      `<input class="sr-url" type="text" readonly value="${escapeHtml(it.url)}" ` +
      `aria-label="${escapeHtml(it.label)} 링크" />` +
      `<button class="btn primary small sr-copy" type="button">복사</button>` +
      `</div>`
    ).join("");
    menu.innerHTML =
      `<h4>🔗 메뉴별 공유 링크</h4>${rows}` +
      `<p id="share-copied" class="share-copied"></p>`;
  }

  const shareBtn = $("#share-btn");
  const shareMenu = $("#share-menu");
  if (shareBtn && shareMenu) {
    shareBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (shareMenu.hidden) {
        buildShareMenu();
        shareMenu.hidden = false;
      } else {
        shareMenu.hidden = true;
      }
    });
    shareMenu.addEventListener("click", async (e) => {
      const input = e.target.closest(".sr-url");
      if (input) { input.focus(); input.select(); return; }
      const btn = e.target.closest(".sr-copy");
      if (!btn) return;
      const row = btn.closest(".share-row");
      const inp = row && row.querySelector(".sr-url");
      const labelEl = row && row.querySelector(".sr-label");
      const url = inp ? inp.value : "";
      const label = labelEl ? labelEl.textContent.replace(/^↳\s*/, "") : "";
      const msg = $("#share-copied");
      const ok = await copyText(url);
      if (!ok && inp) { inp.focus(); inp.select(); } // 폴백: 직접 복사(Ctrl/⌘+C)
      if (msg) msg.textContent = ok
        ? `복사되었습니다 — ${label} 링크`
        : `링크가 선택되었습니다. Ctrl/⌘+C 로 복사하세요.`;
    });
    // 바깥 클릭 시 닫기
    document.addEventListener("click", (e) => {
      if (shareMenu.hidden) return;
      if (!e.target.closest(".share-wrap")) shareMenu.hidden = true;
    });
  }

  // ---- 폼 값 수집 ----
  function collectValues() {
    const values = {};
    fieldIds.forEach((id) => {
      const el = document.getElementById(id);
      values[id] = el ? el.value.trim() : "";
    });
    return values;
  }

  // ---- 이슈 폼 prefill URL 생성 ----
  function buildIssueUrl(values) {
    const params = new URLSearchParams();
    params.set("template", template);
    const name = values["dataset-name"] || "";
    params.set("title", `[검토] ${name}`.trim());
    fieldIds.forEach((id) => {
      if (values[id]) params.set(id, values[id]);
    });
    return `${repoUrl}/issues/new?${params.toString()}`;
  }

  // ---- 중복(이미 검토됨) 감지 ----
  // 데이터셋 명칭을 비교용으로 정규화(공백 정리 + 소문자화).
  function normalizeName(s) {
    return String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
  }
  // 이슈 제목 "[검토] {명칭}" 에서 데이터셋 명칭만 추출.
  function datasetFromTitle(title) {
    const m = /^\s*\[검토\]\s*(.*)$/.exec(String(title || ""));
    return (m ? m[1] : String(title || "")).trim();
  }

  // 같은 데이터셋이 이미 검토되어 GitHub 이슈로 등록되어 있으면 그 이슈 정보를 반환.
  // 우선순위: (1) 라이브 이슈 API(가장 최신) → (2) data/reviews.json(동일 출처·한도 무관 폴백).
  // 어느 소스도 조회하지 못하면 null 을 반환해 신규 이슈 생성을 그대로 진행한다(조회 실패로
  // 사용자를 막지 않기 위함).
  async function findExistingIssue(name) {
    const target = normalizeName(name);
    if (!target) return null;

    // (1) 라이브 이슈 목록 (state=all: 열림/닫힘 모두 포함)
    try {
      const api = `https://api.github.com/repos/${owner}/${repo}/issues?labels=${encodeURIComponent(
        label
      )}&state=all&per_page=100&sort=created&direction=desc`;
      const res = await fetch(api, { headers: apiHeaders() });
      if (res.ok) {
        const issues = await res.json();
        const hit = (issues || [])
          .filter((i) => !i.pull_request)
          .find((i) => normalizeName(datasetFromTitle(i.title)) === target);
        if (hit) return { number: hit.number, title: hit.title, url: hit.html_url };
      }
    } catch (e) {
      /* 아래 JSON 폴백 사용 */
    }

    // (2) 자동 집계 JSON 폴백 (라이브 API 실패·한도 초과·100건 초과 대비)
    try {
      const res = await fetch("data/reviews.json", { cache: "no-cache" });
      if (res.ok) {
        const data = await res.json();
        const rows = (data && data.rows) || (Array.isArray(data) ? data : []);
        const hit = rows.find((r) => normalizeName(r.dataset) === target);
        if (hit) {
          return {
            number: hit.issue,
            title: hit.dataset ? `[검토] ${hit.dataset}` : `#${hit.issue}`,
            url: hit.url || `${repoUrl}/issues/${hit.issue}`,
          };
        }
      }
    } catch (e) {
      /* 조회 불가 시 신규 생성 진행 */
    }

    return null;
  }

  function clearRequestNotice() {
    const el = $("#request-notice");
    if (el) {
      el.hidden = true;
      el.innerHTML = "";
    }
  }

  // 이미 검토된 데이터셋일 때: 신규 이슈를 만들지 않고, 기존 이슈 주소와
  // rerun-review(재검토) 라벨 안내를 보여준다.
  function showDuplicateNotice(existing, values) {
    const el = $("#request-notice");
    if (!el) return;
    const url = escapeHtml(existing.url || "#");
    const title = escapeHtml(existing.title || `#${existing.number}`);
    el.innerHTML =
      `<div class="dup-card">` +
      `<h4>🐶 이미 검토된 데이터셋이에요</h4>` +
      `<p>이 데이터셋은 이미 검토되어 GitHub 이슈에 등록되어 있습니다. ` +
      `중복 검토(무료 쿼터 낭비)를 막기 위해 <strong>새 이슈를 생성하지 않았습니다.</strong></p>` +
      `<p class="dup-issue">📌 등록된 이슈: ` +
      `<a href="${url}" target="_blank" rel="noopener">#${existing.number} ${title}</a></p>` +
      `<p>다시 검토하려면 위 이슈로 이동한 뒤 <code>rerun-review</code> 라벨을 추가(체크)하세요. ` +
      `라벨이 붙는 즉시 재검토가 자동으로 실행됩니다.</p>` +
      `<div class="dup-actions">` +
      `<a class="btn primary small" href="${url}" target="_blank" rel="noopener">이슈로 이동해 재검토(rerun-review) →</a>` +
      `<button type="button" id="dup-force" class="btn ghost small">그래도 새 이슈로 요청</button>` +
      `</div>` +
      `<p class="dim dup-hint">※ 동명의 다른 데이터셋이라면 ‘그래도 새 이슈로 요청’ 으로 새로 등록할 수 있습니다.</p>` +
      `</div>`;
    el.hidden = false;
    const force = $("#dup-force");
    if (force) {
      force.addEventListener("click", () => {
        window.open(buildIssueUrl(values), "_blank", "noopener");
      });
    }
    if (typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  // ---- 제출 ----
  const form = $("#review-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const values = collectValues();
      const name = values["dataset-name"];
      if (!name) {
        alert("데이터셋 명칭을 입력해 주세요.");
        return;
      }
      clearRequestNotice();
      const submitBtn = form.querySelector('button[type="submit"]');
      const prevLabel = submitBtn ? submitBtn.textContent : "";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "이미 검토됐는지 확인 중…";
      }
      let existing = null;
      try {
        existing = await findExistingIssue(name);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = prevLabel;
        }
      }
      if (existing) {
        // 이미 검토된 데이터셋 → 신규 이슈 생성 없이 재검토 안내
        showDuplicateNotice(existing, values);
        return;
      }
      window.open(buildIssueUrl(values), "_blank", "noopener");
    });
  }

  // 데이터셋 명칭을 수정하면 이전 중복 안내를 지운다(다른 데이터셋일 수 있으므로).
  const datasetNameInput = document.getElementById("dataset-name");
  if (datasetNameInput) {
    datasetNameInput.addEventListener("input", clearRequestNotice);
  }

  // ---- 미리보기 ----
  const previewBtn = $("#preview-btn");
  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      const values = collectValues();
      const lines = [
        `제목: [검토] ${values["dataset-name"] || ""}`,
        "",
        `데이터셋 명칭: ${values["dataset-name"] || "(미입력)"}`,
        `관련 / 원본 데이터셋: ${values["related-datasets"] || "-"}`,
        `논문 주소: ${values["paper-urls"] || "-"}`,
        `공식 홈페이지 / 저장소: ${values["homepage-url"] || "-"}`,
        `관련 소송 (CourtListener): ${values["litigation-url"] || "-"}`,
        `추가 참고 사항: ${values["extra-notes"] || "-"}`,
      ];
      $("#preview-body").textContent = lines.join("\n");
      $("#preview").open = true;
    });
  }

  // ═══════════════ 논문 리뷰 (paper) ═══════════════
  const paperTemplate = cfg.paperTemplate || "paper-review.yml";
  const paperLabel = cfg.paperLabel || "paper-review";

  function paperValues() {
    return {
      title: (document.getElementById("paper-title") || {}).value ?
        document.getElementById("paper-title").value.trim() : "",
      url: (document.getElementById("paper-url") || {}).value ?
        document.getElementById("paper-url").value.trim() : "",
      notes: (document.getElementById("paper-extra-notes") || {}).value ?
        document.getElementById("paper-extra-notes").value.trim() : "",
    };
  }
  // 이슈 폼(paper-review.yml) prefill URL. 필드 id: paper-title / paper-url / extra-notes
  function buildPaperIssueUrl(v) {
    const params = new URLSearchParams();
    params.set("template", paperTemplate);
    params.set("title", `[논문검토] ${v.title || ""}`.trim());
    if (v.title) params.set("paper-title", v.title);
    if (v.url) params.set("paper-url", v.url);
    if (v.notes) params.set("extra-notes", v.notes);
    return `${repoUrl}/issues/new?${params.toString()}`;
  }

  const paperForm = $("#paper-form");
  if (paperForm) {
    paperForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = paperValues();
      if (!v.url) {
        alert("논문 PDF 또는 웹사이트 URL 을 입력해 주세요.");
        return;
      }
      window.open(buildPaperIssueUrl(v), "_blank", "noopener");
    });
  }
  const paperPreviewBtn = $("#paper-preview-btn");
  if (paperPreviewBtn) {
    paperPreviewBtn.addEventListener("click", () => {
      const v = paperValues();
      const lines = [
        `제목: [논문검토] ${v.title || ""}`,
        "",
        `논문 제목: ${v.title || "(미입력 — 원문에서 확인)"}`,
        `논문 PDF / 웹사이트 URL: ${v.url || "(미입력)"}`,
        `추가 참고 사항: ${v.notes || "-"}`,
      ];
      $("#paper-preview-body").textContent = lines.join("\n");
      $("#paper-preview").open = true;
    });
  }

  // 논문 검토 결과 목록
  const paperIssuesUrl = `${repoUrl}/issues?q=is%3Aissue+label%3A${encodeURIComponent(paperLabel)}`;
  const paperGhLink =
    `<p><a class="btn ghost small" target="_blank" rel="noopener" href="${paperIssuesUrl}">` +
    `GitHub에서 이슈 보기 →</a></p>`;
  let paperLoaded = false;
  function loadPaperResults(force) {
    const box = $("#paper-results-list");
    if (!box) return;
    if (paperLoaded && !force) return;
    paperLoaded = true;
    box.innerHTML = '<p class="dim">불러오는 중…</p>';
    const api = `https://api.github.com/repos/${owner}/${repo}/issues?labels=${encodeURIComponent(
      paperLabel
    )}&state=all&per_page=100&sort=created&direction=desc`;
    fetch(api, { headers: apiHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error("paper issues " + res.status);
        return res.json();
      })
      .then((issues) => {
        const rows = (issues || []).filter((i) => !i.pull_request);
        if (!rows.length) {
          box.innerHTML =
            '<p class="dim">아직 논문 검토 결과가 없습니다. 첫 논문을 검토 요청해 보세요.</p>' + paperGhLink;
          return;
        }
        box.innerHTML = rows.map((i) => {
          const date = i.created_at ? new Date(i.created_at).toLocaleDateString("ko-KR") : "";
          const labels = (i.labels || []).map((l) => (typeof l === "string" ? l : l.name));
          let badge = '<span class="pbadge warn">대기</span>';
          if (labels.indexOf("reviewed") > -1) badge = '<span class="pbadge ok">✅ 검토 완료</span>';
          else if (labels.indexOf("review-failed") > -1) badge = '<span class="pbadge fail">⚠️ 실패</span>';
          else if (labels.indexOf("reviewing") > -1) badge = '<span class="pbadge warn">⏳ 검토 중</span>';
          const st = i.state === "closed" ? "닫힘" : "열림";
          const title = escapeHtml(String(i.title || "").replace(/^\s*\[논문검토\]\s*/, "")) || ("#" + i.number);
          return (
            `<a class="paper-item" href="${i.html_url}" target="_blank" rel="noopener">` +
            `<span class="pi-title">📄 ${title}</span>` +
            `<span class="pi-meta">${badge}<span class="dim">#${i.number} · ${date} · ${st}</span></span>` +
            `</a>`
          );
        }).join("");
      })
      .catch(() => {
        box.innerHTML =
          '<p class="dim">목록을 불러올 수 없습니다(공용 IP 레이트리밋일 수 있음). 잠시 후 다시 시도하세요.</p>' +
          paperGhLink;
      });
  }
  const paperRefresh = $("#paper-refresh-btn");
  if (paperRefresh) paperRefresh.addEventListener("click", () => loadPaperResults(true));

  // ---- 검토 결과 목록 ----
  const CACHE_KEY = `dr_results_${owner}_${repo}`;
  const issuesUrl = `${repoUrl}/issues?q=is%3Aissue+label%3A${encodeURIComponent(label)}`;
  const ghLinkHtml =
    `<p><a class="btn ghost small" target="_blank" rel="noopener" href="${issuesUrl}">` +
    `GitHub에서 이슈 보기 →</a></p>`;

  let resultsLoaded = false;
  function loadResults(force) {
    const listEl = $("#results-list");
    if (!listEl) return;
    if (resultsLoaded && !force) return;
    resultsLoaded = true;
    listEl.innerHTML = '<p class="dim">불러오는 중…</p>';

    const api = `https://api.github.com/repos/${owner}/${repo}/issues?labels=${encodeURIComponent(
      label
    )}&state=all&per_page=100&sort=created&direction=desc`;

    let status = 0;
    let rateRemaining = null;
    let rateReset = 0;
    fetch(api, { headers: apiHeaders() })
      .then((res) => {
        status = res.status;
        rateRemaining = res.headers.get("X-RateLimit-Remaining");
        rateReset = parseInt(res.headers.get("X-RateLimit-Reset") || "0", 10);
        if (!res.ok) throw new Error(`GitHub API ${res.status}`);
        return res.json();
      })
      .then((issues) => {
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), issues }));
        } catch (e) {
          /* localStorage 사용 불가 시 무시 */
        }
        if (getToken()) setAuthStatus("인증됨 (시간당 5,000회). 목록을 정상적으로 불러왔습니다.", "ok");
        setNotice("");
        setIssues(issues);
      })
      .catch(() => renderError(listEl, status, rateRemaining, rateReset));
  }

  function setNotice(html) {
    const el = $("#results-notice");
    if (el) el.innerHTML = html || "";
  }

  function fmtTime(epochSeconds) {
    if (!epochSeconds) return "";
    try {
      return new Date(epochSeconds * 1000).toLocaleTimeString("ko-KR");
    } catch (e) {
      return "";
    }
  }

  function renderError(listEl, status, rateRemaining, rateReset) {
    const hasToken = !!getToken();
    let msg;
    let openAuth = false;
    if (status === 401) {
      // 잘못되었거나 만료된 토큰
      msg =
        "GitHub 토큰이 유효하지 않거나 만료되었습니다 (401). '🔑 인증'에서 토큰을 다시 입력하거나 삭제하세요.";
      openAuth = true;
      setAuthStatus("토큰이 유효하지 않습니다 (401). 다시 입력하거나 삭제하세요.", "err");
    } else if (status === 403 && rateRemaining === "0") {
      const resetTxt = rateReset ? ` 약 ${fmtTime(rateReset)}에 초기화됩니다.` : "";
      if (hasToken) {
        msg =
          "인증 상태에서도 API 요청 한도(시간당 5,000회)를 초과했습니다." +
          resetTxt +
          " 잠시 후 다시 시도하거나 아래 링크를 이용하세요.";
      } else {
        msg =
          "GitHub 비인증 API 요청 한도(IP당 시간당 60회)를 초과했습니다." +
          resetTxt +
          " 회사 공용 IP를 공유하는 환경에서는 한도가 빠르게 소진될 수 있습니다. " +
          "위 '🔑 인증'에서 본인의 GitHub 토큰을 입력하면 시간당 5,000회로 늘릴 수 있습니다. " +
          "또는 아래 링크에서 직접 확인하세요.";
        openAuth = true;
      }
    } else if (status === 403) {
      msg = "GitHub API 접근이 거부되었습니다 (403). 잠시 후 다시 시도하거나 아래 링크를 이용하세요.";
    } else {
      msg = `목록을 불러오지 못했습니다 (GitHub API ${status || "오류"}).`;
    }

    // 인증이 도움이 되는 상황이면 토큰 패널을 자동으로 펼친다
    if (openAuth) {
      const panel = $("#auth-panel");
      if (panel) panel.hidden = false;
    }

    const notice = `<p class="dim">${msg}</p>` + ghLinkHtml;

    // 폴백 순서: (1) 자동 집계 JSON(data/reviews.json) — 라벨 변경 시·매일 갱신되고
    // 인증/요청 한도와 무관한 동일 출처 파일이라 라이브 API 가 막혀도 최신 이슈까지 표시된다.
    // (2) 실패하면 이 브라우저에 마지막으로 성공한 라이브 응답(localStorage 캐시).
    fallbackFromJson(notice).catch(() => fallbackFromCache(listEl, notice));
  }

  // data/reviews.json 의 행을 목록 렌더러(rowsHtml/statusBadge)가 기대하는 이슈 형태로 변환.
  function issuesFromRows(rows) {
    return (rows || []).map((r) => {
      const labels = [];
      // status(reviewed/reviewing/review-failed)는 라벨명과 동일 → 상태 배지로 매핑된다.
      if (r.status && r.status !== "pending") labels.push({ name: r.status });
      return {
        number: r.issue,
        title: r.dataset ? `[검토] ${r.dataset}` : `#${r.issue}`,
        html_url: r.url,
        created_at: r.created_at,
        state: r.state, // 구버전 JSON 엔 없을 수 있음(그때는 상태·댓글 표기 생략)
        comments: r.comments,
        labels,
      };
    });
  }

  function fallbackFromJson(notice) {
    return fetch("data/reviews.json", { cache: "no-cache" })
      .then((res) => {
        if (!res.ok) throw new Error("reviews.json " + res.status);
        return res.json();
      })
      .then((data) => {
        const rows = (data && data.rows) || [];
        if (!rows.length) throw new Error("reviews.json empty");
        const when = data.exported_at
          ? new Date(data.exported_at).toLocaleString("ko-KR")
          : "";
        setNotice(
          notice +
            `<p class="dim" style="margin-top:14px">📁 GitHub API 대신 자동 집계 데이터로 표시합니다` +
            `${when ? ` (${when} 기준, 매일 갱신)` : ""}.</p>`
        );
        setIssues(issuesFromRows(rows));
      });
  }

  function fallbackFromCache(listEl, notice) {
    // 마지막으로 성공한 목록이 있으면 캐시를 (검색·페이지네이션 그대로) 표시
    let cachedIssues = null;
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (cached && Array.isArray(cached.issues) && cached.issues.length) {
        const when = new Date(cached.t).toLocaleString("ko-KR");
        notice += `<p class="dim" style="margin-top:14px">📁 아래는 마지막으로 불러온 캐시 목록입니다 (${when} 기준, 최신이 아닐 수 있음).</p>`;
        cachedIssues = cached.issues;
      }
    } catch (e) {
      /* 캐시 파싱 실패 무시 */
    }

    setNotice(notice);
    if (cachedIssues) {
      setIssues(cachedIssues);
    } else {
      setIssues([]);
      if (listEl) listEl.innerHTML = "";
    }
  }

  function statusBadge(labels) {
    const names = labels.map((l) => l.name);
    if (names.includes("review-failed")) return '<span class="badge fail">검토 실패</span>';
    if (names.includes("reviewed")) return '<span class="badge done">검토 완료</span>';
    if (names.includes("reviewing")) return '<span class="badge prog">검토 중</span>';
    return '<span class="badge wait">대기</span>';
  }

  function rowsHtml(issues) {
    const items = (issues || []).filter((i) => !i.pull_request);
    if (!items.length) return "";
    return items
      .map((i) => {
        // 메타는 있는 값만 이어붙인다(JSON 폴백엔 state·comments 가 없을 수 있음).
        const meta = [new Date(i.created_at).toLocaleString("ko-KR")];
        if (i.state) meta.push(i.state === "closed" ? "닫힘" : "열림");
        if (typeof i.comments === "number") meta.push(`댓글 ${i.comments}`);
        return (
          `<a class="result-row" href="${i.html_url}" target="_blank" rel="noopener">` +
          `<span class="result-title">#${i.number} ${escapeHtml(i.title)}</span>` +
          `<span class="result-meta">${statusBadge(i.labels)}` +
          `<span class="dim">${meta.join(" · ")}</span></span>` +
          `</a>`
        );
      })
      .join("");
  }

  // ---- 검색 + 페이지네이션(게시판) ----
  let allIssues = []; // PR 제외 전체 목록
  let currentPage = 1;
  let pageSize = 10;
  let searchTerm = "";

  function setIssues(issues) {
    allIssues = (issues || []).filter((i) => !i.pull_request);
    currentPage = 1;
    const controls = $("#results-controls");
    if (controls) controls.hidden = allIssues.length === 0;
    applyView();
  }

  function getFiltered() {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return allIssues;
    return allIssues.filter((i) => (i.title || "").toLowerCase().includes(q));
  }

  function applyView() {
    const listEl = $("#results-list");
    if (!listEl) return;
    const filtered = getFiltered();
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > pages) currentPage = pages;
    if (currentPage < 1) currentPage = 1;

    if (!allIssues.length) {
      listEl.innerHTML = '<p class="dim">아직 검토 요청이 없습니다. 첫 검토를 요청해 보세요.</p>';
    } else if (!total) {
      listEl.innerHTML = `<p class="dim">"${escapeHtml(searchTerm)}" 에 대한 검색 결과가 없습니다.</p>`;
    } else {
      const start = (currentPage - 1) * pageSize;
      listEl.innerHTML = rowsHtml(filtered.slice(start, start + pageSize));
    }

    const pager = $("#results-pager");
    if (pager) {
      if (total <= 0) {
        pager.hidden = true;
      } else {
        pager.hidden = false;
        const info = $("#page-info");
        const prev = $("#page-prev");
        const next = $("#page-next");
        if (info) info.textContent = `${currentPage} / ${pages} 페이지 · 총 ${total}건`;
        if (prev) prev.disabled = currentPage <= 1;
        if (next) next.disabled = currentPage >= pages;
      }
    }
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // 컨트롤 이벤트 바인딩
  const searchEl = $("#results-search");
  if (searchEl) {
    searchEl.addEventListener("input", () => {
      searchTerm = searchEl.value;
      currentPage = 1;
      applyView();
    });
  }
  const pageSizeEl = $("#page-size");
  if (pageSizeEl) {
    pageSizeEl.addEventListener("change", () => {
      pageSize = parseInt(pageSizeEl.value, 10) || 10;
      currentPage = 1;
      applyView();
    });
  }
  const pagePrev = $("#page-prev");
  if (pagePrev) pagePrev.addEventListener("click", () => { currentPage -= 1; applyView(); });
  const pageNext = $("#page-next");
  if (pageNext) pageNext.addEventListener("click", () => { currentPage += 1; applyView(); });

  const refreshBtn = $("#refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => loadResults(true));

  // ==========================================================================
  //  대시보드 — 검토 현황 집계 · 시각화 · 데이터셋별 상세
  //  데이터 소스: docs/data/reviews.json (매일 자동 갱신, GitHub API 인증 불필요)
  // ==========================================================================
  const VERDICTS = [
    { key: "사용 가능", cls: "ok", color: "var(--accent)", icon: "✅" },
    { key: "추가 검토 필요", cls: "warn", color: "var(--warn)", icon: "⚠️" },
    { key: "사용 비권고", cls: "fail", color: "var(--fail)", icon: "⛔" },
    { key: "미판정", cls: "none", color: "var(--text-dim)", icon: "❔" },
  ];
  const ITEMS = [
    { key: "license", label: "라이선스" },
    { key: "collection", label: "데이터 생성·수집 방식" },
    { key: "privacy", label: "개인정보 포함 여부" },
  ];
  const RISK_META = {
    low: { label: "리스크 낮음", cls: "low" },
    mid: { label: "주의", cls: "mid" },
    high: { label: "리스크 있음", cls: "high" },
    unknown: { label: "확인 불가", cls: "unknown" },
    none: { label: "정보 없음", cls: "none" },
  };
  const CONFIDENCE = [
    { key: "high", label: "High", icon: "😊", cls: "high", color: "var(--accent)" },
    { key: "medium", label: "Medium", icon: "😐", cls: "medium", color: "var(--warn)" },
    { key: "low", label: "Low", icon: "😞", cls: "low", color: "var(--fail)" },
    { key: "bad", label: "Bad", icon: "😡", cls: "bad", color: "var(--bad)" },
    { key: "none", label: "미응답", icon: "❔", cls: "none", color: "var(--text-dim)" },
  ];

  function confidenceMeta(value) {
    return CONFIDENCE.find((x) => x.key === value) ||
      CONFIDENCE.find((x) => x.key === "none");
  }

  function verdictMeta(v) {
    return VERDICTS.find((x) => x.key === v) || VERDICTS[3];
  }

  // 확인 결과·내부 판단 텍스트를 리스크 수준으로 분류(키워드 휴리스틱)
  function classifyRisk(text) {
    const t = String(text || "").trim();
    if (!t) return "none";
    if (/확인\s*불가|확인\s*필요|확인이\s*필요|미확인|불명|불분명|알\s*수\s*없/.test(t)) return "unknown";
    if (/불가|제한|비상업|비권고|침해|위반|위험|높음|부재|리스크\s*있음|잠재적|동의\s*범위/.test(t)) return "high";
    if (/가능|낮음|문제\s*없음|문제없음|허용|무관|해당\s*없음|양호/.test(t)) return "low";
    return "mid";
  }
  // 항목 리스크: 내부 판단을 우선, 비면 확인 결과로 판단
  function itemRisk(row, key) {
    const j = row[key + "_judgment"];
    const c = row[key + "_check"];
    return classifyRisk(j && j.trim() ? j : c);
  }

  const dashState = {
    rows: [], exportedAt: "", filter: null, confidence: null, search: "", loaded: false, page: 1, pageSize: 5,
    section: null, // 대시보드 세부 메뉴(선택된 섹션 key)
    litSearch: "", // 소송 현황 데이터셋 검색어
    litPage: 1, litPageSize: 5, // 소송 현황 게시판 페이지네이션
  };
  const DASH_PAGE_SIZES = [5, 10, 15, 30, 50, 70, 100];

  function loadDashboard(force) {
    const body = $("#dash-body");
    if (!body) return;
    if (dashState.loaded && !force) return;
    dashState.loaded = true;
    body.innerHTML = '<p class="dim">불러오는 중…</p>';
    // 캐시 무효화용 쿼리(매일 갱신되므로 날짜 단위면 충분)
    fetch("data/reviews.json", { cache: "no-cache" })
      .then((res) => {
        if (!res.ok) throw new Error("reviews.json " + res.status);
        return res.json();
      })
      .then((data) => {
        // 구버전(JSON 배열)과 신버전({ exported_at, rows })을 모두 지원한다.
        dashState.rows = Array.isArray(data) ? data : (Array.isArray(data.rows) ? data.rows : []);
        dashState.exportedAt = Array.isArray(data) ? "" : (data.exported_at || "");
        renderDashboard();
      })
      .catch(() => {
        body.innerHTML =
          '<p class="dim">집계 데이터를 아직 불러올 수 없습니다. 검토가 1건 이상 완료되고 ' +
          '일일 집계(export)가 실행된 뒤 표시됩니다.</p>' + ghLinkHtml;
      });
  }

  function renderDashboard() {
    const body = $("#dash-body");
    if (!body) return;
    const rows = dashState.rows;
    if (!rows.length) {
      body.innerHTML = '<p class="dim">아직 집계된 검토 결과가 없습니다.</p>';
      return;
    }
    // 실제 집계 완료 시각. 구버전 데이터는 이슈 updated_at 최댓값을 폴백으로 사용한다.
    let latest = dashState.exportedAt;
    if (!latest) {
      rows.forEach((r) => { if ((r.updated_at || "") > latest) latest = r.updated_at; });
    }
    const latestTxt = latest ? new Date(latest).toLocaleString("ko-KR") : "-";

    // 세부 메뉴(섹션) 목록. html 이 빈 문자열이면(예: 소송 이력 없음) 메뉴에서 제외한다.
    const sections = [
      { key: "stats",      label: "🧭 검토 현황",        html: statsSection(rows) },
      { key: "litigation", label: "⚖️ 소송 현황",        html: litigationSection(rows) },
      { key: "charts",     label: "📈 시각화",           html: chartsSection(rows) },
      { key: "trend",      label: "🗓️ 검토 추이",        html: trendSection(rows) },
      { key: "table",      label: "🗂️ 데이터셋별 결과",  html: tableSection() },
      { key: "confidence", label: "💬 만족도",           html: confidenceSection(rows) },
    ].filter((s) => s.html && s.html.trim());

    // 선택된 섹션이 없거나 더 이상 존재하지 않으면 첫 번째 섹션을 기본값으로.
    if (!dashState.section || !sections.some((s) => s.key === dashState.section)) {
      dashState.section = sections.length ? sections[0].key : "";
    }

    const nav = sections.map((s) =>
      `<button class="dash-navbtn${s.key === dashState.section ? " active" : ""}" ` +
      `type="button" data-section="${s.key}" role="tab" ` +
      `aria-selected="${s.key === dashState.section}">${s.label}</button>`
    ).join("");

    const panels = sections.map((s) =>
      `<div class="dash-panel" data-section-panel="${s.key}"${s.key === dashState.section ? "" : " hidden"}>` +
      `${s.html}</div>`
    ).join("");

    body.innerHTML =
      `<p class="dash-updated dim">최근 집계: ${escapeHtml(latestTxt)} · 총 <strong>${rows.length}</strong>건</p>` +
      `<div class="dash-subnav" role="tablist" aria-label="대시보드 세부 메뉴">${nav}</div>` +
      `<div class="dash-panels">${panels}</div>`;

    bindDashSubnav();
    bindDashTable();
    bindLitTable();
  }

  // 지정한 섹션만 보이고 나머지는 숨긴다(세부 메뉴/딥링크 공통).
  // 모든 패널을 DOM 에 렌더한 뒤 표시만 토글하므로 표/차트 바인딩이 유지된다.
  // 현재 데이터에 없는 섹션이면 false 를 반환하고 아무것도 바꾸지 않는다.
  function activateDashSection(key) {
    const nav = $(".dash-subnav");
    if (!nav) return false;
    const btns = Array.prototype.slice.call(nav.querySelectorAll(".dash-navbtn"));
    if (!btns.some((b) => b.getAttribute("data-section") === key)) return false;
    btns.forEach((b) => {
      const on = b.getAttribute("data-section") === key;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("#dash-body .dash-panel").forEach((p) => {
      p.hidden = p.getAttribute("data-section-panel") !== key;
    });
    dashState.section = key;
    return true;
  }

  // 세부 메뉴 클릭 → URL 해시(#dashboard/<section>)를 갱신해 딥링크·뒤로가기 지원.
  function bindDashSubnav() {
    const nav = $(".dash-subnav");
    if (!nav) return;
    const btns = Array.prototype.slice.call(nav.querySelectorAll(".dash-navbtn"));
    btns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-section");
        const frag = "dashboard/" + key;
        if ("#" + frag === location.hash) activateDashSection(key); // 같은 링크 재클릭 보정
        else location.hash = frag; // hashchange → applyTabFromHash → activateDashSection
        // 섹션 전환 시 대시보드 상단이 보이도록 스크롤(긴 표에서 편의).
        const body = $("#dash-body");
        if (body && typeof body.scrollIntoView === "function") {
          body.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  // ── ⚖️ 소송이 걸려있는 데이터셋 현황 ─────────────────────────────
  // 소송/법적 분쟁 이력이 확인된('litigation === 있음') 데이터셋을,
  // 사건명·사건번호·원고·피고·근거 강도와 함께 표로 보여주고,
  // 행을 펼치면 침해 주장 요지·원고의 입증 방법(판단 기준)·소장 인용 등을 열람한다.
  const LIT_STRENGTH = {
    "강": { label: "강 · 직접 자인", cls: "high", order: 0 },
    "중": { label: "중 · 간접 자인", cls: "mid", order: 1 },
    "약": { label: "약 · 정황 근거", cls: "low", order: 2 },
  };
  function litStrengthMeta(s) {
    return LIT_STRENGTH[s] || { label: "확인 불가", cls: "none", order: 3 };
  }
  // 값이 있으면 이스케이프해 반환, 없으면 '—'(dim). undefined(구버전 JSON)도 안전 처리.
  function litCell(v) {
    return v && String(v).trim() ? escapeHtml(v) : '<span class="dim">—</span>';
  }
  // 당사자(원고/피고) 인라인 표기: 값이 없으면 '미상'.
  function litParty(v) {
    return v && String(v).trim() ? escapeHtml(v) : '<span class="dim">미상</span>';
  }

  // 소송 현황 게시판: 페이지당 개수 옵션
  const LIT_PAGE_SIZES = [5, 10, 15, 20, 30, 50, 70, 100];

  let litRows = [];

  // 카드 1개(컴팩트): 데이터셋명+강도 배지 / 사건명 / 원고 v. 피고 · 사건번호.
  // 침해 주장 요지(teaser)는 세로 공간 절약을 위해 카드에서 빼고 상세(펼침)에서 표시한다.
  function litCardHtml(r, idx) {
    const sm = litStrengthMeta(r.litigation_strength);
    const dsName = r.dataset || ("#" + r.issue);
    const caseName = r.litigation_case && String(r.litigation_case).trim()
      ? escapeHtml(r.litigation_case)
      : '<span class="dim">사건명 확인 불가</span>';
    const docket = r.litigation_docket && String(r.litigation_docket).trim()
      ? `<span class="lit-dot" aria-hidden="true">·</span>` +
        `<span class="lit-docket">📁 ${escapeHtml(r.litigation_docket)}</span>`
      : "";
    return (
      `<div class="lit-card sev-${sm.cls}" data-lit="${idx}" role="button" tabindex="0" aria-expanded="false">` +
      `<div class="lit-card-head">` +
      `<span class="lit-card-ds"><span class="chev" aria-hidden="true">▸</span>${escapeHtml(dsName)}</span>` +
      `<span class="lbadge ${sm.cls}">${sm.label}</span></div>` +
      `<div class="lit-card-case">⚖️ ${caseName}</div>` +
      `<div class="lit-parties">` +
      `<span class="lit-party plaintiff"><span class="role">원고</span>${litParty(r.litigation_plaintiff)}</span>` +
      `<span class="lit-vs">v.</span>` +
      `<span class="lit-party defendant"><span class="role">피고</span>${litParty(r.litigation_defendant)}</span>` +
      docket +
      `</div>` +
      `<div class="lit-card-detail" data-lit-detail="${idx}" hidden>${litDetailHtml(r)}</div>` +
      `</div>`
    );
  }

  // 검색어를 적용한 {r, i} 목록.
  // 검색 대상: 데이터셋 명칭 · 소송 원고 · 소송 피고 · 소송번호(도켓) · 사건명.
  // (원고/피고가 '미상'인 건도 당사자명이 사건명에 담기는 경우가 많아 사건명도 포함한다.
  //  예: 피고 필드가 비어도 사건명 "Nassif et al v. Samsung Electronics ..." 로 검색 가능)
  function litFiltered() {
    const q = (dashState.litSearch || "").trim().toLowerCase();
    const all = litRows.map((r, i) => ({ r, i }));
    if (!q) return all;
    return all.filter(({ r }) => {
      const haystack = [
        r.dataset || ("#" + r.issue), // 데이터셋 명칭
        r.litigation_plaintiff,       // 소송 원고 명칭
        r.litigation_defendant,       // 소송 피고 명칭
        r.litigation_docket,          // 소송번호 명칭(도켓)
        r.litigation_case,            // 사건명(당사자명이 포함되는 경우 대비)
      ]
        .map((v) => String(v || "").toLowerCase())
        .join(" ");
      return haystack.includes(q);
    });
  }

  // 현재 페이지/검색어 기준으로 카드 목록을 다시 그린다(게시판 페이지네이션).
  function renderLitList() {
    const list = $("#lit-list");
    if (!list) return;
    const items = litFiltered();
    const total = items.length;
    const size = dashState.litPageSize;
    const pages = Math.max(1, Math.ceil(total / size));
    if (dashState.litPage > pages) dashState.litPage = pages;
    if (dashState.litPage < 1) dashState.litPage = 1;
    const start = (dashState.litPage - 1) * size;
    const pageItems = items.slice(start, start + size);

    list.innerHTML = pageItems.map(({ r, i }) => litCardHtml(r, i)).join("");

    const empty = $("#lit-empty");
    if (empty) empty.hidden = total > 0;
    const countEl = $("#lit-search-count");
    if (countEl) {
      const q = (dashState.litSearch || "").trim();
      countEl.textContent = q ? `${total}건 검색됨 / 전체 ${litRows.length}건` : `총 ${litRows.length}건`;
    }
    updateLitPager(total, pages);
  }

  function updateLitPager(total, pages) {
    const pager = $("#lit-pager");
    if (!pager) return;
    if (total <= 0) { pager.hidden = true; return; }
    pager.hidden = false;
    const info = $("#lit-page-info");
    const prev = $("#lit-prev");
    const next = $("#lit-next");
    if (info) info.textContent = `${dashState.litPage} / ${pages} 페이지 · 총 ${total}건`;
    if (prev) prev.disabled = dashState.litPage <= 1;
    if (next) next.disabled = dashState.litPage >= pages;
  }

  function litigationSection(rows) {
    litRows = (rows || [])
      .filter((r) => r.litigation === "있음")
      .sort((a, b) =>
        litStrengthMeta(a.litigation_strength).order - litStrengthMeta(b.litigation_strength).order ||
        String(a.dataset || "").localeCompare(String(b.dataset || ""))
      );
    if (!litRows.length) return "";
    if (dashState.litPage < 1) dashState.litPage = 1;

    const sizeOpts = LIT_PAGE_SIZES.map((n) =>
      `<option value="${n}"${n === dashState.litPageSize ? " selected" : ""}>${n}</option>`
    ).join("");

    return (
      `<div class="dash-section"><h4>⚖️ 소송이 걸려있는 데이터셋 현황 ` +
      `<span class="dim" style="font-size:0.8rem">(${litRows.length}건)</span></h4>` +
      `<div class="lit-intro"><span class="lit-intro-icon" aria-hidden="true">🚨</span>` +
      `<p><strong>저작권자의 허가 없이 AI 학습 데이터로 무단 이용</strong>되어 ` +
      `<strong>저작권 침해 소송에 연루된</strong> 데이터셋입니다. 아래 데이터셋을 AI 모델 학습에 사용하면 ` +
      `동일한 <strong>법적 리스크</strong>에 노출될 수 있으니 주의가 필요합니다. ` +
      `카드를 클릭하면 <strong>침해 주장 요지 · 원고의 입증 방법 · 소장 원문 인용 · 내부 판단</strong> 등 상세 정보가 펼쳐집니다.</p></div>` +
      `<div class="lit-controls">` +
      `<input type="search" id="lit-search" class="results-search" ` +
      `placeholder="🔍 데이터셋 명칭 · 원고 · 피고 · 소송번호로 검색" aria-label="소송 현황 검색 (데이터셋명·원고·피고·소송번호)" ` +
      `value="${escapeHtml(dashState.litSearch || "")}" />` +
      `<label class="page-size">페이지당 <select id="lit-page-size">${sizeOpts}</select> 개</label>` +
      `<span id="lit-search-count" class="lit-search-count dim"></span>` +
      `</div>` +
      `<div class="lit-list" id="lit-list"></div>` +
      `<p id="lit-empty" class="dim lit-empty" hidden>🐶 검색어와 일치하는 소송 연루 데이터셋이 없습니다.</p>` +
      `<div id="lit-pager" class="results-pager" hidden>` +
      `<button id="lit-prev" class="btn ghost small" type="button">← 이전</button>` +
      `<span id="lit-page-info" class="page-info"></span>` +
      `<button id="lit-next" class="btn ghost small" type="button">다음 →</button></div>` +
      `<p class="lit-legend dim">침해 입증 근거 강도 &nbsp; ` +
      `<span class="lbadge high">강 · 직접 자인</span> 피고 자인·법원 인정 &nbsp; ` +
      `<span class="lbadge mid">중 · 간접 자인</span> 논증적 추론 &nbsp; ` +
      `<span class="lbadge low">약 · 정황 근거</span> 명칭만 언급</p>` +
      `</div>`
    );
  }

  function litDetailHtml(r) {
    const field = (label, val, wide) =>
      `<div class="lit-field${wide ? " wide" : ""}"><dt>${label}</dt>` +
      `<dd>${val && String(val).trim() ? escapeHtml(val) : '<span class="dim">—</span>'}</dd></div>`;
    const quote = r.litigation_quote && String(r.litigation_quote).trim()
      ? `<blockquote class="lit-quote">${escapeHtml(r.litigation_quote)}</blockquote>`
      : '<span class="dim">—</span>';
    return (
      `<div class="lit-detail"><dl class="lit-grid">` +
      field("법원", r.litigation_court) +
      field("사건 상태", r.litigation_status, true) +
      field("침해 주장 요지", r.litigation_claim, true) +
      field("원고가 어떻게 알아냈는가 (판단 기준)", r.litigation_how, true) +
      field("소장 항 번호", r.litigation_paragraph) +
      `<div class="lit-field wide"><dt>소장 원문 인용</dt><dd>${quote}</dd></div>` +
      field("요약", r.litigation_summary, true) +
      field("내부 판단", r.litigation_judgment, true) +
      field("판단 근거", r.litigation_basis, true) +
      `</dl>` +
      `<p class="lit-foot"><a class="btn ghost small" href="${escapeHtml(r.url || "#")}" ` +
      `target="_blank" rel="noopener">GitHub 이슈 #${r.issue} 원문 보기 →</a></p></div>`
    );
  }

  function bindLitTable() {
    const list = $("#lit-list");
    if (!list) return;
    const toggle = (card) => {
      const detail = card.querySelector(".lit-card-detail");
      if (!detail) return;
      detail.hidden = !detail.hidden;
      card.classList.toggle("open", !detail.hidden);
      card.setAttribute("aria-expanded", detail.hidden ? "false" : "true");
    };
    // 카드가 재렌더돼도 유지되도록 컨테이너(#lit-list)에 이벤트 위임.
    list.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;                // 링크 클릭은 통과(새 탭 열기)
      if (e.target.closest(".lit-card-detail")) return; // 펼쳐진 상세 내부 클릭은 접힘 방지
      const card = e.target.closest(".lit-card");
      if (card) toggle(card);
    });
    list.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const card = e.target.closest(".lit-card");
      if (card && e.target === card) { e.preventDefault(); toggle(card); }
    });

    const scrollTop = () => {
      const sec = list.closest(".dash-section");
      if (sec && typeof sec.scrollIntoView === "function") {
        sec.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };

    // ── 데이터셋 명칭 검색 ──
    const search = $("#lit-search");
    if (search) {
      search.addEventListener("input", () => {
        dashState.litSearch = search.value;
        dashState.litPage = 1;
        renderLitList();
      });
    }
    // ── 페이지당 개수 변경 ──
    const sizeSel = $("#lit-page-size");
    if (sizeSel) {
      sizeSel.addEventListener("change", () => {
        dashState.litPageSize = parseInt(sizeSel.value, 10) || 5;
        dashState.litPage = 1;
        renderLitList();
      });
    }
    // ── 페이지 이동 ──
    const prev = $("#lit-prev");
    const next = $("#lit-next");
    if (prev) prev.addEventListener("click", () => { dashState.litPage -= 1; renderLitList(); scrollTop(); });
    if (next) next.addEventListener("click", () => { dashState.litPage += 1; renderLitList(); scrollTop(); });

    renderLitList();
  }

  // ── ① 요약 통계 카드 ────────────────────────────────────────
  // 판정 4분류가 무엇을 뜻하는지 처음 보는 사람도 알 수 있게 한 줄 설명.
  const VERDICT_MEANING = {
    "사용 가능": "문제 없음 — 바로 사용 가능",
    "추가 검토 필요": "일부 확인·조건 필요 — 검토 후 사용",
    "사용 비권고": "법적 리스크 큼 — 사용 지양",
    "미판정": "정보 부족 — 추가 확인 필요",
  };

  function statsSection(rows) {
    const total = rows.length;
    const counts = { "사용 가능": 0, "추가 검토 필요": 0, "사용 비권고": 0, "미판정": 0 };
    rows.forEach((r) => { counts[verdictMeta(r.verdict).key]++; });
    const privacyRisk = rows.filter((r) => itemRisk(r, "privacy") === "high").length;
    const litig = rows.filter((r) => r.litigation === "있음").length;
    const reviewed = rows.filter((r) => r.status === "reviewed").length;
    const usable = counts["사용 가능"];
    const usablePct = total ? Math.round((usable / total) * 100) : 0;

    // ① 판정 분포를 한 줄로 보여주는 구성 막대(사용 가능 여부 비율을 한눈에)
    const segs = VERDICTS.filter((v) => counts[v.key] > 0).map((v) => {
      const pct = total ? (counts[v.key] / total) * 100 : 0;
      const label = pct >= 9 ? `${v.icon} ${Math.round(pct)}%` : "";
      return `<span class="st-seg ${v.cls}" style="width:${pct.toFixed(2)}%" ` +
        `title="${v.icon} ${v.key} · ${counts[v.key]}건 (${Math.round(pct)}%)">${label}</span>`;
    }).join("");

    // ② 판정별 카드(큰 숫자 + 뜻풀이)
    const cards = VERDICTS.map((v) => {
      const c = counts[v.key];
      const pct = total ? Math.round((c / total) * 100) : 0;
      return `<div class="st-card ${v.cls}">` +
        `<div class="st-card-top"><span class="st-emoji">${v.icon}</span>` +
        `<span class="st-count">${c}<span class="st-unit">건</span></span>` +
        `<span class="st-pct">${pct}%</span></div>` +
        `<div class="st-name">${v.key}</div>` +
        `<div class="st-mean">${VERDICT_MEANING[v.key]}</div>` +
        `</div>`;
    }).join("");

    // ③ 세부 리스크 지표(뜻풀이 포함)
    const riskTile = (ico, num, label, hint) =>
      `<div class="st-risk"><span class="st-risk-ico" aria-hidden="true">${ico}</span>` +
      `<div><div class="st-risk-num">${num}</div>` +
      `<div class="st-risk-label">${label} <span class="dim">${hint}</span></div></div></div>`;

    return (
      `<div class="dash-section"><h4>🧭 검토 현황</h4>` +
      `<p class="st-intro">지금까지 <strong>${total}개</strong> 데이터셋의 법적 리스크를 검토했습니다. ` +
      `각 데이터셋은 <strong>사용 가능 여부</strong>에 따라 아래 4가지로 분류되며, 현재 바로 쓸 수 있는(문제 없는) ` +
      `데이터셋은 <strong class="st-hl-ok">${usable}개 · ${usablePct}%</strong>입니다.</p>` +
      `<div class="st-bar" role="img" aria-label="판정 분포: 사용 가능 ${counts["사용 가능"]}건, 추가 검토 필요 ${counts["추가 검토 필요"]}건, 사용 비권고 ${counts["사용 비권고"]}건, 미판정 ${counts["미판정"]}건">${segs}</div>` +
      `<div class="st-cards">${cards}</div>` +
      `<div class="st-risks">` +
      riskTile("🔒", `${privacyRisk}건`, "개인정보 리스크", "(얼굴·음성 등 식별정보 포함)") +
      riskTile("⚖️", `${litig}건`, "소송 연루", "(저작권 침해 소송 대상)") +
      riskTile("📄", `${reviewed}/${total}`, "검토 완료", "(전체 대비 완료 건수)") +
      `</div></div>`
    );
  }

  // ── ② AI 자동리뷰 결과 만족도 ───────────────────────────────
  function confidenceSection(rows) {
    const counts = { high: 0, medium: 0, low: 0, bad: 0, none: 0 };
    rows.forEach((r) => { counts[confidenceMeta(r.review_confidence).key]++; });
    const total = rows.length;
    const responses = total - counts.none;
    const responseRate = total ? Math.round((responses / total) * 100) : 0;
    // 응답(미응답 제외) 중 긍정(High) 비율 — 한눈에 보는 만족 지표
    const posRate = responses ? Math.round((counts.high / responses) * 100) : 0;

    // ① 상단 구성 막대: 전체 분포를 한 줄로 한눈에.
    const segs = CONFIDENCE.filter((m) => counts[m.key] > 0).map((m) => {
      const pct = total ? (counts[m.key] / total) * 100 : 0;
      const label = pct >= 9 ? `${m.icon} ${Math.round(pct)}%` : "";
      return `<span class="cf-seg ${m.cls}" style="width:${pct.toFixed(2)}%" ` +
        `title="${m.icon} ${m.label} · ${counts[m.key]}건 (${Math.round(pct)}%)">${label}</span>`;
    }).join("");

    // ② 레벨별 카드: 큰 숫자 + 색상 강조로 가독성 확보.
    const cards = CONFIDENCE.map((m) => {
      const count = counts[m.key];
      const pct = total ? Math.round((count / total) * 100) : 0;
      return `<div class="cf-card ${m.cls}">` +
        `<div class="cf-emoji">${m.icon}</div>` +
        `<div class="cf-label">${m.label}</div>` +
        `<div class="cf-count">${count}<span class="cf-unit">건</span></div>` +
        `<div class="cf-pct">${pct}%</div>` +
        `</div>`;
    }).join("");

    return (
      `<div class="dash-section"><h4>💬 AI 자동리뷰 결과 만족도</h4>` +
      `<div class="cf-summary">` +
      `<div class="cf-score"><div class="cf-score-num">${posRate}<span class="cf-score-unit">%</span></div>` +
      `<div class="cf-score-label">😊 High 만족 비율<br><span class="dim">(응답 ${responses}건 기준)</span></div></div>` +
      `<div class="cf-bar-wrap"><div class="cf-bar" role="img" ` +
      `aria-label="만족도 구성: High ${counts.high}건, Medium ${counts.medium}건, Low ${counts.low}건, Bad ${counts.bad}건, 미응답 ${counts.none}건">${segs}</div>` +
      `<div class="cf-bar-legend">` +
      CONFIDENCE.map((m) => `<span class="cf-lg"><span class="cf-dot ${m.cls}"></span>${m.icon} ${m.label} <strong>${counts[m.key]}</strong></span>`).join("") +
      `</div></div></div>` +
      `<div class="cf-cards">${cards}</div>` +
      `<p class="dash-meta-line"><span>응답 <strong>${responses}</strong>/${total}건</span>` +
      `<span>응답률 <strong>${responseRate}%</strong></span></p></div>`
    );
  }

  // ── ③ 시각화: 판정 분포(도넛) + 항목별 리스크(스택 막대) ──────
  function chartsSection(rows) {
    const counts = {};
    VERDICTS.forEach((v) => { counts[v.key] = 0; });
    rows.forEach((r) => { counts[verdictMeta(r.verdict).key]++; });
    const total = rows.length;
    const segs = VERDICTS.filter((v) => counts[v.key] > 0)
      .map((v) => ({ value: counts[v.key], color: v.color, label: v.key }));

    const legend = VERDICTS.map((v) => {
      const c = counts[v.key];
      const pct = total ? Math.round((c / total) * 100) : 0;
      return (
        `<div class="lg"><span class="sw" style="background:${v.color}"></span>` +
        `<span>${v.icon} ${v.key}</span>` +
        `<span class="lg-count">${c}건 · ${pct}%</span></div>`
      );
    }).join("");

    // 항목별 리스크 스택
    const levels = ["low", "mid", "high", "unknown", "none"];
    const riskBars = ITEMS.map((it) => {
      const c = { low: 0, mid: 0, high: 0, unknown: 0, none: 0 };
      rows.forEach((r) => { c[itemRisk(r, it.key)]++; });
      const segsHtml = levels
        .filter((lv) => c[lv] > 0)
        .map((lv) => {
          const pct = (c[lv] / total) * 100;
          return `<span class="stack-seg seg-${lv}" style="width:${pct.toFixed(1)}%" ` +
            `title="${RISK_META[lv].label}: ${c[lv]}건"></span>`;
        }).join("");
      const risky = c.high + c.unknown;
      return (
        `<div class="risk-item">` +
        `<div class="ri-label"><span>${it.label}</span>` +
        `<span class="dim">주의 이상 ${risky}건</span></div>` +
        `<div class="stack-bar">${segsHtml}</div></div>`
      );
    }).join("");

    const riskLegend =
      `<div class="risk-legend">` +
      `<span class="lg"><span class="sw seg-low"></span>리스크 낮음</span>` +
      `<span class="lg"><span class="sw seg-mid"></span>주의</span>` +
      `<span class="lg"><span class="sw seg-high"></span>리스크 있음</span>` +
      `<span class="lg"><span class="sw seg-unknown"></span>확인 불가</span>` +
      `</div>`;

    return (
      `<div class="dash-section"><h4>📈 시각화</h4><div class="dash-charts">` +
      `<div class="chart-box"><h5>내부 판단 분포</h5>` +
      `<div class="donut-wrap">${donutSvg(segs, total)}<div class="donut-legend">${legend}</div></div></div>` +
      `<div class="chart-box"><h5>검토 항목별 리스크</h5>${riskBars}${riskLegend}</div>` +
      `</div></div>`
    );
  }

  function donutSvg(segs, total) {
    const r = 48, cx = 60, cy = 60, C = 2 * Math.PI * r;
    let offset = 0, arcs = "";
    if (total > 0) {
      segs.forEach((s) => {
        if (!s.value) return;
        const len = (s.value / total) * C;
        arcs +=
          `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${s.color}" stroke-width="16" ` +
          `stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" ` +
          `stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"></circle>`;
        offset += len;
      });
    } else {
      arcs = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border)" stroke-width="16"></circle>`;
    }
    return (
      `<svg viewBox="0 0 120 120" width="128" height="128" role="img" aria-label="판정 분포">` +
      arcs +
      `<text x="60" y="58" text-anchor="middle" style="font-size:22px;font-weight:700;fill:var(--text)">${total}</text>` +
      `<text x="60" y="74" text-anchor="middle" style="font-size:9px;fill:var(--text-dim)">건 검토</text>` +
      `</svg>`
    );
  }

  // ── ④ 검토 추이 (요청일 기준) ────────────────────────────────
  function trendSection(rows) {
    const map = new Map();
    rows.forEach((r) => {
      const d = (r.created_at || "").slice(0, 10);
      if (d) map.set(d, (map.get(d) || 0) + 1);
    });
    const days = Array.from(map.keys()).sort().slice(-14);
    if (!days.length) return "";
    const max = Math.max(...days.map((d) => map.get(d)));
    const bars = days.map((d) => {
      const cnt = map.get(d);
      const h = max ? Math.round((cnt / max) * 100) : 0;
      const md = d.slice(5); // MM-DD
      return (
        `<div class="trend-col" title="${d}: ${cnt}건">` +
        `<span class="trend-cnt">${cnt}</span>` +
        `<div class="trend-bar" style="height:${h}%"></div>` +
        `<span class="trend-date">${md}</span></div>`
      );
    }).join("");
    return (
      `<div class="dash-section"><h4>🗓️ 검토 추이 <span class="dim" style="font-size:0.8rem">(최근 ${days.length}일)</span></h4>` +
      `<div class="chart-box"><div class="trend">${bars}</div></div></div>`
    );
  }

  // ── ⑤ 데이터셋별 상세 (필터 + 드릴다운 테이블) ───────────────
  function tableSection() {
    const chips = [{ key: null, label: "전체" }]
      .concat(VERDICTS.map((v) => ({ key: v.key, label: `${v.icon} ${v.key}` })))
      .map((c) => {
        const active = dashState.filter === c.key ? " active" : "";
        const val = c.key === null ? "" : c.key;
        return `<button class="chip${active}" data-verdict="${escapeHtml(val)}">${c.label}</button>`;
      }).join("");

    const sizeOpts = DASH_PAGE_SIZES.map((n) =>
      `<option value="${n}"${n === dashState.pageSize ? " selected" : ""}>${n}</option>`
    ).join("");
    const confidenceOpts = CONFIDENCE.map((m) =>
      `<option value="${m.key}">${m.icon} 만족도 ${m.label}</option>`
    ).join("");

    return (
      `<div class="dash-section"><h4>🗂️ 데이터셋별 검토 결과</h4>` +
      `<div class="dash-filter">${chips}` +
      `<input type="search" id="dash-search" class="results-search" placeholder="🔍 데이터셋 검색" ` +
      `value="${escapeHtml(dashState.search)}" aria-label="데이터셋 검색" />` +
      `<select id="dash-confidence" class="dash-select" aria-label="AI 자동리뷰 만족도 필터">` +
      `<option value="">만족도 전체</option>${confidenceOpts}</select>` +
      `<label class="page-size">페이지당 <select id="dash-page-size">${sizeOpts}</select> 개</label>` +
      `</div>` +
      `<div class="dash-table-wrap"><table class="dash-table">` +
      `<thead><tr><th>데이터셋</th><th>판정</th><th>라이선스</th><th>수집·생성</th>` +
      `<th>개인정보</th><th>만족도</th><th>소송</th><th>모델</th><th>요청일</th></tr></thead>` +
      `<tbody id="dash-tbody"></tbody></table></div>` +
      `<div id="dash-pager" class="results-pager" hidden>` +
      `<button id="dash-prev" class="btn ghost small" type="button">← 이전</button>` +
      `<span id="dash-page-info" class="page-info"></span>` +
      `<button id="dash-next" class="btn ghost small" type="button">다음 →</button>` +
      `</div>` +
      `<p class="dim" style="font-size:0.82rem;margin-top:10px">행을 클릭하면 종합의견(확인 결과 · 내부 판단 · 판단 근거)이 펼쳐집니다.</p>` +
      `</div>`
    );
  }

  function filteredRows() {
    const q = dashState.search.trim().toLowerCase();
    return dashState.rows.filter((r) => {
      if (dashState.filter && verdictMeta(r.verdict).key !== dashState.filter) return false;
      if (dashState.confidence && confidenceMeta(r.review_confidence).key !== dashState.confidence) return false;
      if (q && !String(r.dataset || "").toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function riskCell(row, key) {
    const lv = itemRisk(row, key);
    const txt = (row[key + "_check"] || row[key + "_judgment"] || "").replace(/`/g, "");
    const full = [row[key + "_check"], row[key + "_judgment"]].filter(Boolean).join(" · ");
    const inner = escapeHtml(txt) || "<span class='dim'>-</span>";
    const dataFull = full ? ` data-full="${escapeHtml(full)}"` : "";
    return (
      `<div class="cell-risk"><span class="risk-dot ${lv}" title="${RISK_META[lv].label}"></span>` +
      `<span class="cell-text"${dataFull}>${inner}</span></div>`
    );
  }

  function updateDashPager(total, pages) {
    const pager = $("#dash-pager");
    if (!pager) return;
    if (total <= 0) { pager.hidden = true; return; }
    pager.hidden = false;
    const info = $("#dash-page-info");
    const prev = $("#dash-prev");
    const next = $("#dash-next");
    if (info) info.textContent = `${dashState.page} / ${pages} 페이지 · 총 ${total}건`;
    if (prev) prev.disabled = dashState.page <= 1;
    if (next) next.disabled = dashState.page >= pages;
  }

  function renderDashTbody() {
    const tbody = $("#dash-tbody");
    if (!tbody) return;
    const all = filteredRows();
    const total = all.length;
    const pages = Math.max(1, Math.ceil(total / dashState.pageSize));
    if (dashState.page > pages) dashState.page = pages;
    if (dashState.page < 1) dashState.page = 1;

    if (!total) {
      tbody.innerHTML = `<tr><td colspan="9" class="dim">조건에 맞는 데이터셋이 없습니다.</td></tr>`;
      updateDashPager(0, pages);
      return;
    }

    const start = (dashState.page - 1) * dashState.pageSize;
    const rows = all.slice(start, start + dashState.pageSize);
    updateDashPager(total, pages);

    tbody.innerHTML = rows.map((r, idx) => {
      const vm = verdictMeta(r.verdict);
      const date = r.created_at ? new Date(r.created_at).toLocaleDateString("ko-KR") : "-";
      const litig = r.litigation === "있음"
        ? `<span class="vbadge fail">있음</span>`
        : `<span class="dim">-</span>`;
      const cm = confidenceMeta(r.review_confidence);
      const main =
        `<tr class="ds-row" data-idx="${idx}">` +
        `<td><span class="ds-link">${escapeHtml(r.dataset || ("#" + r.issue))}</span></td>` +
        `<td><span class="vbadge ${vm.cls}">${vm.icon} ${r.verdict || "미판정"}</span></td>` +
        `<td>${riskCell(r, "license")}</td>` +
        `<td>${riskCell(r, "collection")}</td>` +
        `<td>${riskCell(r, "privacy")}</td>` +
        `<td><span class="cbadge ${cm.cls}">${cm.icon} ${cm.label}</span></td>` +
        `<td>${litig}</td>` +
        `<td class="dim" style="white-space:nowrap">${escapeHtml(r.model || "-")}</td>` +
        `<td class="dim" style="white-space:nowrap">${date}</td></tr>`;
      const detail =
        `<tr class="detail-row" data-detail="${idx}" hidden><td colspan="9">${detailHtml(r)}</td></tr>`;
      return main + detail;
    }).join("");
  }

  // 판단 근거의 `[출처 N](url)` 마크다운 링크를 짧은 클릭형 링크로 변환한다.
  // 원문의 초장문 Vertex AI 리다이렉트 URL이 그대로 노출돼 표가 우측으로 잘리던 문제를 해결.
  function basisCell(v) {
    if (!v || !String(v).trim()) return '<span class="dim">-</span>';
    const s = String(v);
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    let out = "", last = 0, m;
    while ((m = re.exec(s)) !== null) {
      out += escapeHtml(s.slice(last, m.index));
      const label = escapeHtml(m[1].trim());
      const href = m[2].trim();
      if (/^https?:\/\//i.test(href)) {
        out += `<a class="src-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">🔗 ${label}</a>`;
      } else {
        out += escapeHtml(m[0]);
      }
      last = re.lastIndex;
    }
    out += escapeHtml(s.slice(last));
    return out;
  }

  function detailHtml(r) {
    const vm = verdictMeta(r.verdict);
    const cm = confidenceMeta(r.review_confidence);
    const cell = (v) => (v && String(v).trim() ? escapeHtml(String(v)) : '<span class="dim">-</span>');
    const rowsHtml = ITEMS.map((it) =>
      `<tr><td>${it.label}</td>` +
      `<td>${cell(r[it.key + "_check"])}</td>` +
      `<td>${cell(r[it.key + "_judgment"])}</td>` +
      `<td class="basis-cell">${basisCell(r[it.key + "_basis"])}</td></tr>`
    ).join("");
    return (
      `<div class="detail-inner">` +
      `<p class="di-verdict">종합 판정: <span class="vbadge ${vm.cls}">${vm.icon} ${r.verdict || "미판정"}</span></p>` +
      `<p class="di-confidence">AI 자동리뷰 결과 만족도: <span class="cbadge ${cm.cls}">${cm.icon} ${cm.label}</span></p>` +
      `<table class="detail-table"><thead><tr><th>검토 항목</th><th>확인 결과</th>` +
      `<th>내부 판단</th><th>판단 근거</th></tr></thead><tbody>${rowsHtml}</tbody></table>` +
      `<p class="di-foot"><a class="btn ghost small" href="${escapeHtml(r.url || "#")}" target="_blank" rel="noopener">GitHub 이슈 #${r.issue} 상세 보기 →</a></p>` +
      `</div>`
    );
  }

  function bindDashTable() {
    renderDashTbody();
    document.querySelectorAll("#dash-body .chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const v = chip.getAttribute("data-verdict");
        dashState.filter = v || null;
        dashState.page = 1;
        document.querySelectorAll("#dash-body .chip").forEach((c) => {
          c.classList.toggle("active", (c.getAttribute("data-verdict") || "") === (v || ""));
        });
        renderDashTbody();
      });
    });
    const search = $("#dash-search");
    if (search) {
      search.addEventListener("input", () => {
        dashState.search = search.value;
        dashState.page = 1;
        renderDashTbody();
      });
    }
    const sizeSel = $("#dash-page-size");
    if (sizeSel) {
      sizeSel.addEventListener("change", () => {
        dashState.pageSize = parseInt(sizeSel.value, 10) || 15;
        dashState.page = 1;
        renderDashTbody();
      });
    }
    const confidenceSel = $("#dash-confidence");
    if (confidenceSel) {
      confidenceSel.value = dashState.confidence || "";
      confidenceSel.addEventListener("change", () => {
        dashState.confidence = confidenceSel.value || null;
        dashState.page = 1;
        renderDashTbody();
      });
    }
    const prev = $("#dash-prev");
    if (prev) prev.addEventListener("click", () => { dashState.page -= 1; renderDashTbody(); });
    const next = $("#dash-next");
    if (next) next.addEventListener("click", () => { dashState.page += 1; renderDashTbody(); });
    const tbody = $("#dash-tbody");
    if (tbody) {
      tbody.addEventListener("click", (e) => {
        const row = e.target.closest("tr.ds-row");
        if (!row) return;
        const idx = row.getAttribute("data-idx");
        const detail = tbody.querySelector(`tr.detail-row[data-detail="${idx}"]`);
        if (detail) detail.hidden = !detail.hidden;
      });
    }
  }

  const dashRefresh = $("#dash-refresh");
  if (dashRefresh) dashRefresh.addEventListener("click", () => loadDashboard(true));

  // ---- 표 셀 호버 툴팁 ----
  // 대시보드 표의 라이선스·수집/생성·개인정보 셀은 2줄로 줄여 표시하고(공간 절약),
  // 마우스를 올리면 전체 내용(data-full)을 떠 있는 툴팁으로 보여준다. 표 래퍼가
  // overflow-x:auto 라 CSS ::after 툴팁은 잘리므로, body 에 붙는 단일 요소로 띄운다.
  function initCellTooltip() {
    let tip = null;
    const ensure = () => {
      if (!tip) {
        tip = document.createElement("div");
        tip.className = "cell-tip";
        tip.setAttribute("role", "tooltip");
        document.body.appendChild(tip);
      }
      return tip;
    };
    const hide = () => { if (tip) tip.style.display = "none"; };
    const place = (el) => {
      const full = el.getAttribute("data-full");
      if (!full) return;
      const t = ensure();
      t.textContent = full;
      t.style.display = "block";
      const r = el.getBoundingClientRect();
      const doc = document.documentElement;
      const tw = t.offsetWidth, th = t.offsetHeight;
      let left = window.scrollX + r.left;
      const maxLeft = window.scrollX + doc.clientWidth - tw - 8;
      if (left > maxLeft) left = Math.max(window.scrollX + 8, maxLeft);
      let top = window.scrollY + r.bottom + 6;
      if (r.bottom + 6 + th > doc.clientHeight) top = window.scrollY + r.top - th - 6;
      t.style.left = left + "px";
      t.style.top = top + "px";
    };
    document.addEventListener("mouseover", (e) => {
      const el = e.target.closest && e.target.closest(".cell-text[data-full]");
      if (el) place(el);
    });
    document.addEventListener("mouseout", (e) => {
      const el = e.target.closest && e.target.closest(".cell-text[data-full]");
      if (el) hide();
    });
    window.addEventListener("scroll", hide, true);
  }
  initCellTooltip();

  // 최초 진입 시 해시가 가리키는 탭을 활성화(공유 링크로 바로 진입 지원).
  // 모든 상태 변수(dashState 등) 초기화 이후에 호출해야 TDZ 오류가 없다.
  applyTabFromHash();

  // ---- 접근 암호 게이트 (약한 클라이언트 측 차단) ----
  async function sha256Hex(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function initAuthGate() {
    const overlay = $("#login-overlay");
    const form = $("#login-form");
    const pw = $("#login-pw");
    const msg = $("#login-msg");
    const hint = $("#login-hint");
    const expected = (cfg.authHash || "").toLowerCase();

    // 암호가 설정되지 않았으면 게이트를 열어 둔다
    if (!expected) {
      root.setAttribute("data-auth", "1");
      if (overlay) overlay.remove();
      return;
    }
    // 이미 인증됨(head 스크립트가 data-auth 설정)
    if (root.getAttribute("data-auth") === "1") {
      if (overlay) overlay.remove();
      return;
    }
    if (hint && cfg.authHint) hint.textContent = cfg.authHint;
    if (pw) pw.focus();
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const val = pw ? pw.value : "";
        if (!val) return;
        let ok = false;
        try {
          ok = (await sha256Hex(val)) === expected;
        } catch (err) {
          if (msg) msg.textContent = "이 브라우저에서 암호 확인을 지원하지 않습니다.";
          return;
        }
        if (ok) {
          try { localStorage.setItem("dr_auth", "1"); } catch (e2) {}
          root.setAttribute("data-auth", "1");
          if (overlay) overlay.remove();
        } else {
          if (msg) msg.textContent = "암호가 올바르지 않습니다.";
          if (pw) { pw.value = ""; pw.focus(); }
        }
      });
    }
  }
  initAuthGate();
})();
