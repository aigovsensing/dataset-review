/* 한국어 ↔ English 전환 (docs/i18n.js)
 *
 * - 원문(source of truth)은 한국어 HTML 이다. 한국어 모드에서는 이 파일이 아무 것도 바꾸지 않는다.
 * - English 모드에서는 화면에 그려진 한국어 텍스트/속성을 사전(docs/i18n-en.js)으로 번역한다.
 *   정적 HTML 뿐 아니라 app.js 가 나중에 그리는 목록·대시보드도 MutationObserver 로 자동 번역한다.
 * - 사전 키는 '번역 단위'의 태그 골격(속성 제거·공백 정규화)이다. 속성(href 등)은 번역 때 원본 요소에서 복사한다.
 *   같은 규칙을 tests/test_i18n.py 가 파이썬으로 재현해 사전 누락을 검사한다(두 곳을 함께 고칠 것).
 * - 언어 결정: ?lang=ko|en → 저장값(localStorage) → 브라우저 언어(한국어면 ko, 그 밖은 en).
 */
(function () {
  "use strict";

  var SUPPORTED = ["ko", "en"];
  var HAN = /[가-힣]/;
  var INLINE = { B: 1, STRONG: 1, EM: 1, I: 1, A: 1, CODE: 1, SPAN: 1, BR: 1, KBD: 1, SUB: 1, SMALL: 1, U: 1, MARK: 1 };
  var ATTRS = ["placeholder", "title", "aria-label", "alt", "content"];

  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 불가 환경 */ } }

  function detect() {
    var q = null;
    try { q = new URLSearchParams(location.search).get("lang"); } catch (e) { /* 구형 브라우저 */ }
    if (q && SUPPORTED.indexOf(q) >= 0) { safeSet("lang", q); return q; }
    var saved = safeGet("lang");
    if (saved && SUPPORTED.indexOf(saved) >= 0) return saved;
    var nav = (navigator.languages && navigator.languages[0]) || navigator.language || "ko";
    return String(nav).toLowerCase().indexOf("ko") === 0 ? "ko" : "en";
  }

  var lang = detect();
  var root = document.documentElement;
  root.setAttribute("lang", lang);
  root.setAttribute("data-lang", lang);
  // English 모드: 번역이 끝나기 전 한국어가 비치지 않도록 본문을 잠시 숨긴다(CSS: html[data-i18n-pending]).
  // 스크립트 오류로 영구히 숨겨지지 않도록 3초 뒤 무조건 해제한다.
  if (lang === "en") {
    root.setAttribute("data-i18n-pending", "");
    setTimeout(function () { root.removeAttribute("data-i18n-pending"); }, 3000);
  }

  var DICT = (lang === "en" && window.I18N_EN) || { map: {}, rules: [] };
  var RULES = (DICT.rules || []).map(function (r) { return [new RegExp(r[0]), r[1]]; });
  var SUBS = (DICT.sub || []).map(function (r) { return [new RegExp(r[0], "g"), r[1]]; });

  function norm(s) { return String(s).replace(/\s+/g, " ").trim(); }

  // ── 번역 단위 골격: 태그(속성 제거)와 텍스트만 남긴 문자열 ─────────────────────────────
  function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function skeleton(el) {
    var out = "";
    for (var n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) out += esc(n.nodeValue);
      else if (n.nodeType === 1) {
        var tag = n.tagName.toLowerCase();
        out += tag === "br" ? "<br>" : "<" + tag + ">" + skeleton(n) + "</" + tag + ">";
      }
    }
    return out;
  }

  // 규칙 치환: $n = 캡처 원문, %n = 캡처를 사전으로 번역한 값(예: 데이터 유형 이름).
  function applyRule(re, repl, k) {
    return k.replace(re, function () {
      var g = arguments;
      return repl.replace(/([$%])(\d)/g, function (m, kind, n) {
        var v = g[+n];
        if (v === undefined) return "";
        if (kind === "%") { var tv = lookup(v); return tv !== undefined ? tv : v; }
        return v;
      });
    });
  }

  // 1) 정확히 일치하는 항목 → 2) 전체 일치 규칙(rules) → 3) 부분 치환(sub: '[데이터셋검토]' 접두어 등)
  function lookup(key) {
    var k = norm(key);
    var hit = DICT.map[k];
    if (hit !== undefined) return hit;
    for (var i = 0; i < RULES.length; i++) {
      if (RULES[i][0].test(k)) return applyRule(RULES[i][0], RULES[i][1], k);
    }
    var out = k;
    for (var j = 0; j < SUBS.length; j++) out = out.replace(SUBS[j][0], SUBS[j][1]);
    return out !== k ? out : undefined;
  }

  function isUnit(el) {
    var hasHan = false;
    for (var n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) { if (HAN.test(n.nodeValue)) hasHan = true; }
      else if (n.nodeType === 1) {
        if (!INLINE[n.tagName]) return false;
        if (HAN.test(n.textContent)) hasHan = true;
      }
    }
    return hasHan;
  }

  function skipped(el) {
    return !!(el.closest && el.closest('[translate="no"], script, style, textarea, pre, code[data-i18n-skip]'));
  }

  // English 골격을 DOM 으로 만들고, 같은 태그의 원본 요소 속성을 순서대로 복사한다.
  function applyUnit(el, english) {
    var tpl = document.createElement("template");
    tpl.innerHTML = english;
    var srcByTag = {};
    el.querySelectorAll("*").forEach(function (s) { (srcByTag[s.tagName] = srcByTag[s.tagName] || []).push(s); });
    var used = {};
    tpl.content.querySelectorAll("*").forEach(function (d) {
      var list = srcByTag[d.tagName] || [];
      var i = used[d.tagName] || 0;
      used[d.tagName] = i + 1;
      var s = list[i];
      if (!s) return;
      Array.prototype.forEach.call(s.attributes, function (a) { d.setAttribute(a.name, a.value); });
    });
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(tpl.content);
  }

  function translateAttrs(el) {
    ATTRS.forEach(function (a) {
      if (el.tagName === "META" && a === "content" && el.getAttribute("name") !== "description") return;
      if (a === "content" && el.tagName !== "META") return;
      var v = el.getAttribute(a);
      if (!v || !HAN.test(v)) return;
      var t = lookup(v);
      if (t !== undefined && t !== v) el.setAttribute(a, t);
    });
  }

  function translateTextNode(n) {
    if (!HAN.test(n.nodeValue) || (n.parentNode && skipped(n.parentNode))) return;
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(n.nodeValue);
    var t = lookup(m[2]);
    if (t !== undefined) n.nodeValue = m[1] + t + m[3];
  }

  function translateElement(el) {
    if (el.nodeType !== 1 || skipped(el)) return;
    translateAttrs(el);
    if (HAN.test(el.textContent)) {
      if (isUnit(el)) {
        var t = lookup(skeleton(el));
        if (t !== undefined) { applyUnit(el, t); return; }
      }
      for (var n = el.firstChild; n; n = n.nextSibling) {
        if (n.nodeType === 1) translateElement(n);
        else if (n.nodeType === 3) translateTextNode(n);
      }
    } else {
      // 한글 텍스트는 없지만 속성(placeholder 등)이 한국어일 수 있다.
      el.querySelectorAll("*").forEach(translateAttrs);
    }
  }

  function translateTree(node) {
    if (node.nodeType === 3) { translateTextNode(node); return; }
    if (node.nodeType === 1) {
      translateElement(node);
      // 한글 텍스트가 없는 하위 요소의 속성(title 등)도 처리
      if (!HAN.test(node.textContent)) return;
      node.querySelectorAll("[placeholder],[title],[aria-label],[alt]").forEach(translateAttrs);
    }
  }

  // JS 에서 조립하는 문자열용: t("한국어 {name}", {name: v}). 앞뒤 공백은 보존한다.
  function t(ko, vars) {
    var out = ko;
    if (lang === "en") {
      var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(ko);
      var hit = lookup(m[2]);
      if (hit !== undefined) out = m[1] + hit + m[3];
    }
    if (vars) out = out.replace(/\{(\w+)\}/g, function (x, k) { return vars[k] !== undefined ? vars[k] : x; });
    return out;
  }

  // ── 입력값 보존: 언어 전환은 새로고침으로 처리하므로 작성 중인 폼 값을 잠시 저장했다가 복원 ──
  function saveForms() {
    try {
      var data = {};
      document.querySelectorAll("form input[id], form textarea[id], form select[id]").forEach(function (f) {
        if (f.type === "password" || f.type === "hidden") return;
        data[f.id] = f.type === "checkbox" ? f.checked : f.value;
      });
      sessionStorage.setItem("i18n_forms", JSON.stringify(data));
    } catch (e) { /* 무시 */ }
  }
  function restoreForms() {
    try {
      var raw = sessionStorage.getItem("i18n_forms");
      if (!raw) return;
      sessionStorage.removeItem("i18n_forms");
      var data = JSON.parse(raw);
      Object.keys(data).forEach(function (id) {
        var f = document.getElementById(id);
        if (!f || f.closest("#login-form")) return;
        if (f.type === "checkbox") f.checked = !!data[id]; else if (data[id]) f.value = data[id];
      });
    } catch (e) { /* 무시 */ }
  }

  function setLang(next) {
    if (SUPPORTED.indexOf(next) < 0 || next === lang) return;
    safeSet("lang", next);
    saveForms();
    // ?lang= 가 주소에 있으면 제거(공유 링크에 남지 않게, 저장값이 우선하도록)한 뒤 새로고침한다.
    // location.replace(같은 주소) 는 해시 이동으로 처리되어 새로고침이 되지 않으므로 reload() 를 쓴다.
    try {
      var url = new URL(location.href);
      if (url.searchParams.has("lang")) {
        url.searchParams.delete("lang");
        history.replaceState(null, "", url.toString());
      }
    } catch (e) { /* 무시 */ }
    location.reload();
  }

  function bindSwitch() {
    document.querySelectorAll("[data-set-lang]").forEach(function (b) {
      var is = b.getAttribute("data-set-lang") === lang;
      b.classList.toggle("active", is);
      b.setAttribute("aria-pressed", is ? "true" : "false");
      b.addEventListener("click", function () { setLang(b.getAttribute("data-set-lang")); });
    });
  }

  // 본문 끝(app.js 실행 직전)에서 호출한다: 정적 DOM 을 번역하고, 이후 동적 렌더를 관찰해 번역한다.
  function init() {
    bindSwitch();
    restoreForms();
    if (lang !== "en") return;
    document.title = lookup(document.title) || document.title;
    var meta = document.head.querySelector('meta[name="description"]');
    if (meta) translateAttrs(meta);
    translateTree(document.body);
    root.removeAttribute("data-i18n-pending");
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === "characterData") { if (m.target.parentNode) translateElement(m.target.parentNode); return; }
        if (m.target.nodeType === 1) translateElement(m.target);
        Array.prototype.forEach.call(m.addedNodes, translateTree);
      });
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  window.I18N = {
    init: init,
    lang: lang,
    locale: lang === "en" ? "en-US" : "ko-KR",
    t: t,
    setLang: setLang,
    // 개발·테스트용
    _skeleton: skeleton, _isUnit: isUnit, _lookup: lookup, _translateTree: translateTree,
  };
})();
