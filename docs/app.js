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

  // ---- 탭 전환 ----
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab-panel").forEach((p) => {
        p.classList.toggle("active", p.id === `tab-${target}`);
      });
      if (target === "results") loadResults();
    });
  });

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
    )}&state=all&per_page=30&sort=created&direction=desc`;

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
        renderResults(issues, listEl);
      })
      .catch(() => renderError(listEl, status, rateRemaining, rateReset));
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

    let html = `<p class="dim">${msg}</p>` + ghLinkHtml;

    // 마지막으로 성공한 목록이 있으면 캐시로 표시
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (cached && Array.isArray(cached.issues) && cached.issues.length) {
        const when = new Date(cached.t).toLocaleString("ko-KR");
        html +=
          `<p class="dim" style="margin-top:14px">📁 아래는 마지막으로 불러온 캐시 목록입니다 (${when} 기준, 최신이 아닐 수 있음).</p>` +
          rowsHtml(cached.issues);
      }
    } catch (e) {
      /* 캐시 파싱 실패 무시 */
    }
    listEl.innerHTML = html;
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
        const date = new Date(i.created_at).toLocaleString("ko-KR");
        const state = i.state === "closed" ? "닫힘" : "열림";
        return (
          `<a class="result-row" href="${i.html_url}" target="_blank" rel="noopener">` +
          `<span class="result-title">#${i.number} ${escapeHtml(i.title)}</span>` +
          `<span class="result-meta">${statusBadge(i.labels)}` +
          `<span class="dim">${date} · ${state} · 댓글 ${i.comments}</span></span>` +
          `</a>`
        );
      })
      .join("");
  }

  function renderResults(issues, listEl) {
    const rows = rowsHtml(issues);
    listEl.innerHTML = rows ||
      '<p class="dim">아직 검토 요청이 없습니다. 첫 검토를 요청해 보세요.</p>';
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  const refreshBtn = $("#refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => loadResults(true));
})();
