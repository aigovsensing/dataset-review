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
  };
  const VALID_TABS = Object.keys(TAB_LABELS);

  function currentTab() {
    const h = (location.hash || "").replace(/^#/, "");
    return VALID_TABS.includes(h) ? h : "request";
  }
  function tabUrl(tab) {
    return location.origin + location.pathname + "#" + tab;
  }
  function applyTabFromHash() {
    const target = currentTab();
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === target));
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `tab-${target}`);
    });
    if (target === "results") loadResults();
    if (target === "dashboard") loadDashboard();
  }

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

  function buildShareMenu() {
    const menu = $("#share-menu");
    if (!menu) return;
    const rows = VALID_TABS.map((t) =>
      `<div class="share-row">` +
      `<span class="sr-label">${TAB_LABELS[t]}</span>` +
      `<input class="sr-url" type="text" readonly value="${escapeHtml(tabUrl(t))}" ` +
      `aria-label="${TAB_LABELS[t]} 링크" />` +
      `<button class="btn primary small sr-copy" type="button" data-copy="${t}">복사</button>` +
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
      const btn = e.target.closest("[data-copy]");
      if (!btn) return;
      const t = btn.getAttribute("data-copy");
      const url = tabUrl(t);
      const msg = $("#share-copied");
      const ok = await copyText(url);
      if (!ok) {
        // 폴백: 해당 입력창을 선택해 사용자가 직접 복사(Ctrl/⌘+C)하도록 유도
        const row = btn.closest(".share-row");
        const inp = row && row.querySelector(".sr-url");
        if (inp) { inp.focus(); inp.select(); }
      }
      if (msg) msg.textContent = ok
        ? `복사되었습니다 — ${TAB_LABELS[t]} 링크`
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

  // ---- 제출 ----
  const form = $("#review-form");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const values = collectValues();
      if (!values["dataset-name"]) {
        alert("데이터셋 명칭을 입력해 주세요.");
        return;
      }
      window.open(buildIssueUrl(values), "_blank", "noopener");
    });
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
    { key: "none", label: "미응답", icon: "❔", cls: "none", color: "var(--text-dim)" },
  ];

  function confidenceMeta(value) {
    return CONFIDENCE.find((x) => x.key === value) || CONFIDENCE[3];
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

    body.innerHTML =
      `<p class="dash-updated dim">최근 집계: ${escapeHtml(latestTxt)} · 총 <strong>${rows.length}</strong>건</p>` +
      statsSection(rows) +
      confidenceSection(rows) +
      chartsSection(rows) +
      trendSection(rows) +
      tableSection();

    bindDashTable();
  }

  // ── ① 요약 통계 카드 ────────────────────────────────────────
  function statsSection(rows) {
    const counts = { "사용 가능": 0, "추가 검토 필요": 0, "사용 비권고": 0, "미판정": 0 };
    rows.forEach((r) => { counts[verdictMeta(r.verdict).key]++; });
    const privacyRisk = rows.filter((r) => itemRisk(r, "privacy") === "high").length;
    const litig = rows.filter((r) => r.litigation === "있음").length;
    const reviewed = rows.filter((r) => r.status === "reviewed").length;

    const card = (cls, num, label) =>
      `<div class="stat-card ${cls}"><div class="stat-num">${num}</div><div class="stat-label">${label}</div></div>`;

    return (
      `<div class="dash-section">` +
      `<h4>🧭 검토 현황</h4>` +
      `<div class="dash-stats">` +
      card("total", rows.length, "총 검토 데이터셋") +
      card("ok", counts["사용 가능"], "✅ 사용 가능") +
      card("warn", counts["추가 검토 필요"], "⚠️ 추가 검토 필요") +
      card("fail", counts["사용 비권고"], "⛔ 사용 비권고") +
      `</div>` +
      `<p class="dash-meta-line">` +
      `<span>🔒 개인정보 리스크 <strong>${privacyRisk}</strong>건</span>` +
      `<span>⚖️ 소송 관련 <strong>${litig}</strong>건</span>` +
      `<span>❔ 미판정 <strong>${counts["미판정"]}</strong>건</span>` +
      `<span>📄 검토 완료 <strong>${reviewed}</strong>/${rows.length}</span>` +
      `</p></div>`
    );
  }

  // ── ② AI 자동리뷰 결과 만족도 ───────────────────────────────
  function confidenceSection(rows) {
    const counts = { high: 0, medium: 0, low: 0, none: 0 };
    rows.forEach((r) => { counts[confidenceMeta(r.review_confidence).key]++; });
    const responses = rows.length - counts.none;
    const responseRate = rows.length ? Math.round((responses / rows.length) * 100) : 0;
    const bars = CONFIDENCE.map((m) => {
      const count = counts[m.key];
      const pct = rows.length ? (count / rows.length) * 100 : 0;
      return `<div class="confidence-item">` +
        `<div class="confidence-head"><span>${m.icon} ${m.label}</span>` +
        `<strong>${count}건 · ${Math.round(pct)}%</strong></div>` +
        `<div class="confidence-track"><span class="confidence-fill ${m.cls}" style="width:${pct.toFixed(1)}%"></span></div>` +
        `</div>`;
    }).join("");
    return (
      `<div class="dash-section"><h4>💬 AI 자동리뷰 결과 만족도</h4>` +
      `<div class="chart-box confidence-box">${bars}</div>` +
      `<p class="dash-meta-line"><span>응답 <strong>${responses}</strong>/${rows.length}건</span>` +
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
    return (
      `<div class="cell-risk"><span class="risk-dot ${lv}" title="${RISK_META[lv].label}"></span>` +
      `<span class="cell-text" title="${escapeHtml(full)}">${escapeHtml(txt) || "<span class='dim'>-</span>"}</span></div>`
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

  function detailHtml(r) {
    const vm = verdictMeta(r.verdict);
    const cm = confidenceMeta(r.review_confidence);
    const cell = (v) => (v && String(v).trim() ? escapeHtml(String(v)) : '<span class="dim">-</span>');
    const rowsHtml = ITEMS.map((it) =>
      `<tr><td>${it.label}</td>` +
      `<td>${cell(r[it.key + "_check"])}</td>` +
      `<td>${cell(r[it.key + "_judgment"])}</td>` +
      `<td>${cell(r[it.key + "_basis"])}</td></tr>`
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
