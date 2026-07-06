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

    fetch(api, { headers: { Accept: "application/vnd.github+json" } })
      .then((res) => {
        if (!res.ok) throw new Error(`GitHub API ${res.status}`);
        return res.json();
      })
      .then((issues) => renderResults(issues, listEl))
      .catch((err) => {
        listEl.innerHTML =
          `<p class="dim">목록을 불러오지 못했습니다 (${err.message}).</p>` +
          `<p><a class="btn ghost small" target="_blank" rel="noopener" ` +
          `href="${repoUrl}/issues?q=is%3Aissue+label%3A${encodeURIComponent(label)}">` +
          `GitHub에서 이슈 보기 →</a></p>`;
      });
  }

  function statusBadge(labels) {
    const names = labels.map((l) => l.name);
    if (names.includes("review-failed")) return '<span class="badge fail">검토 실패</span>';
    if (names.includes("reviewed")) return '<span class="badge done">검토 완료</span>';
    if (names.includes("reviewing")) return '<span class="badge prog">검토 중</span>';
    return '<span class="badge wait">대기</span>';
  }

  function renderResults(issues, listEl) {
    // PR 제외
    const items = (issues || []).filter((i) => !i.pull_request);
    if (!items.length) {
      listEl.innerHTML =
        '<p class="dim">아직 검토 요청이 없습니다. 첫 검토를 요청해 보세요.</p>';
      return;
    }
    const rows = items
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
    listEl.innerHTML = rows;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  const refreshBtn = $("#refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => loadResults(true));
})();
