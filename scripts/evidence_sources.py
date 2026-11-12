#!/usr/bin/env python3
"""1차 자료 직접 조회로 검토 '근거(evidence)'를 모은다 — Gemini 그라운딩·검색 API 없이, 무료·키 불필요.

배경
----
무료 Google AI Studio 키로는 Gemini 3.x 의 Google 검색 그라운딩을 쓸 수 없고(공식 가격표: Free tier "Not available"),
2.5 는 폐기 중이라, 검토가 '검색 없는 PLAIN 생성'으로 떨어지면 정확도가 크게 낮아진다. 그런데 데이터셋 법적 검토의
핵심 사실(라이선스·출처·개인정보 언급·논문)은 검색엔진이 아니라 **원천**(Hugging Face 카드, GitHub LICENSE,
arXiv, Zenodo, 데이터셋 홈페이지)에 직접 적혀 있다. 이 모듈은 요청에 담긴 URL(과 데이터셋 이름)로 그 원천들을
직접 읽어 (제목, URL, 내용 요약) 목록을 만들고, 검토 엔진이 이를 `[N]` 인용 근거로 사용한다.

안전
----
- 요청자가 넣은 URL 을 가져오므로 http/https 만 허용하고, 사설·루프백·링크로컬(클라우드 메타데이터 포함)·예약 주소는
  차단한다. 리다이렉트도 매 단계 재검증한다. 응답 크기·시간을 제한한다.
- 가져온 내용은 '신뢰할 수 없는 데이터'다(프롬프트 주입 가능). 엔진이 프롬프트에서 데이터 구역으로 구분한다.
- 실패한 원천은 건너뛰고(진단 로그만) 나머지로 계속한다. 키·토큰 값은 출력하지 않는다.
"""
from __future__ import annotations

import base64
import html as htmllib
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

UA = "dataset-review/1.0 (+https://github.com/aigovsensing/dataset-review)"
MAX_BYTES = 1_500_000        # 응답 본문 상한
TIMEOUT = 20
SNIPPET_MAX = 2800           # 근거 1건의 내용 상한(글자)
TOTAL_MAX = 30000            # 전체 근거 내용 상한(글자)
MAX_ITEMS = 14

Evidence = tuple[str, str, str]  # (제목, URL, 내용 요약)

URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%\[\]]+")
KEYWORDS = (
    "license", "licence", "licensed", "terms of use", "terms and conditions", "copyright", "consent", "privacy",
    "personal", "pii", "biometric", "face", "ethic", "scrap", "crawl", "collected", "source", "citation",
    "라이선스", "저작권", "개인정보", "동의",
)


# ───────────────────────── 안전한 HTTP ─────────────────────────
def _check_url(url: str) -> None:
    """http/https 와 공개 주소만 허용한다(SSRF 방지). 위반 시 ValueError."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("허용되지 않는 URL 형식")
    if p.port not in (None, 80, 443):
        raise ValueError("허용되지 않는 포트")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError("도메인 확인 실패") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ValueError("내부/예약 주소는 조회하지 않는다")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_get(url: str, headers: dict[str, str] | None = None, max_bytes: int = MAX_BYTES) -> tuple[int, str, str]:
    """(상태코드, content-type, 본문 텍스트). 네트워크 오류는 예외로 올린다."""
    _check_url(url)
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    opener = urllib.request.build_opener(_SafeRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=h), timeout=TIMEOUT) as r:
            raw = r.read(max_bytes + 1)[:max_bytes]
            ctype = r.headers.get("Content-Type", "")
            return r.status, ctype, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", ""


# ───────────────────────── 텍스트 도우미 ─────────────────────────
def clean(text: str, limit: int = SNIPPET_MAX) -> str:
    """제어문자 제거 + 공백 정리 + 길이 제한(신뢰할 수 없는 입력의 최소 정화)."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def strip_tags(s: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))


def keyword_windows(text: str, width: int = 240, max_windows: int = 6) -> str:
    """긴 문서에서 라이선스·개인정보 등 핵심 키워드 주변 문장만 뽑는다(겹치는 구간은 병합)."""
    low = text.lower()
    spans: list[tuple[int, int]] = []
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), low):
            spans.append((max(0, m.start() - width), min(len(text), m.end() + width)))
            if len(spans) > 200:
                break
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return " … ".join(clean(text[a:b], 700) for a, b in merged[:max_windows])


class _Page(HTMLParser):
    """HTML 에서 제목·설명·JSON-LD·보이는 텍스트를 뽑는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.jsonld: list[str] = []
        self.text: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_ld = False
        self._ld_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "nav", "footer"):
            if tag == "script" and "ld+json" in (a.get("type") or ""):
                self._in_ld, self._ld_buf = True, []
            else:
                self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or a.get("property") or "").lower() in (
                "description", "og:description", "twitter:description") and not self.description:
            self.description = a.get("content") or ""

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.jsonld.append("".join(self._ld_buf))
        elif tag in ("script", "style", "noscript", "svg", "nav", "footer") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_ld:
            self._ld_buf.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip:
            self.text.append(data)


def parse_html(doc: str) -> dict:
    p = _Page()
    try:
        p.feed(doc)
    except Exception:  # noqa: BLE001 - 깨진 HTML 도 가능한 만큼 사용
        pass
    return {"title": clean(p.title, 200), "description": clean(p.description, 500),
            "jsonld": p.jsonld, "text": clean(" ".join(p.text), 400_000)}


def jsonld_facts(blocks: list[str]) -> str:
    """schema.org Dataset/CreativeWork JSON-LD 에서 라이선스 등 법적으로 중요한 필드만 뽑는다."""
    facts: list[str] = []

    def val(x):
        if isinstance(x, dict):
            return x.get("name") or x.get("@id") or x.get("url") or ""
        if isinstance(x, list):
            return ", ".join(str(val(i)) for i in x[:4])
        return str(x)

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            if "@graph" in node:
                walk(node["@graph"])
            for key in ("name", "license", "creator", "author", "publisher", "isAccessibleForFree",
                        "datePublished", "citation", "sameAs"):
                if key in node and node[key]:
                    facts.append(f"{key}={clean(val(node[key]), 160)}")
    for b in blocks:
        try:
            walk(json.loads(b))
        except Exception:  # noqa: BLE001
            continue
    return "; ".join(dict.fromkeys(facts))[:900]


# ───────────────────────── 원천별 조회 ─────────────────────────
def hf_dataset(repo_id: str, with_readme: bool = True, candidate: bool = False) -> list[Evidence]:
    page = f"https://huggingface.co/datasets/{repo_id}"
    status, _, body = http_get(f"https://huggingface.co/api/datasets/{repo_id}")
    if status != 200:
        return []
    d = json.loads(body)
    card = d.get("cardData") or {}
    tags = d.get("tags") or []
    pick = [t for t in tags if t.startswith(("license:", "task_categories:", "source_datasets:", "language:", "size_categories:"))]
    lic = card.get("license")
    facts = [
        f"license={lic if lic else '카드에 license 필드 없음(미명시)'}",
        f"gated={d.get('gated')}", f"author={d.get('author')}", f"lastModified={d.get('lastModified')}",
        f"downloads={d.get('downloads')}", f"tags={', '.join(pick[:12])}",
    ]
    if card.get("source_datasets"):
        facts.append(f"source_datasets={card.get('source_datasets')}")
    if card.get("pretty_name"):
        facts.append(f"pretty_name={card.get('pretty_name')}")
    desc = clean(strip_tags(d.get("description") or ""), 600)
    label = "Hugging Face 데이터셋 카드(메타데이터)" + (" — 이름 검색 후보(공식 여부 미확인)" if candidate else "")
    out: list[Evidence] = [(f"{label} · {repo_id}", page, clean("; ".join(facts) + (f" | 설명: {desc}" if desc else "")))]
    if with_readme:
        s2, _, readme = http_get(f"https://huggingface.co/datasets/{repo_id}/raw/main/README.md", max_bytes=400_000)
        if s2 == 200 and readme:
            body_text = re.sub(r"^---.*?---\s*", "", readme, count=1, flags=re.S)
            snippet = clean(body_text, 700) + " … " + keyword_windows(body_text)
            out.append((f"Hugging Face 데이터셋 카드(README 발췌) · {repo_id}", page + "#readme", clean(snippet)))
    return out


def github_repo(owner: str, repo: str) -> list[Evidence]:
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    hdr = {"Accept": "application/vnd.github+json"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    status, _, body = http_get(base, hdr)
    if status != 200:
        return []
    d = json.loads(body)
    lic = d.get("license") or {}
    facts = [
        f"license={lic.get('spdx_id') or lic.get('name') or '저장소에 LICENSE 미감지'}",
        f"archived={d.get('archived')}", f"fork={d.get('fork')}", f"pushed_at={d.get('pushed_at')}",
        f"stars={d.get('stargazers_count')}", f"topics={', '.join((d.get('topics') or [])[:8])}",
    ]
    if d.get("description"):
        facts.append(f"설명: {clean(d['description'], 240)}")
    url = d.get("html_url") or f"https://github.com/{owner}/{repo}"
    out: list[Evidence] = [(f"GitHub 저장소 메타데이터 · {owner}/{repo}", url, clean("; ".join(facts)))]
    s2, _, lb = http_get(f"{base}/license", hdr)
    if s2 == 200:
        j = json.loads(lb)
        try:
            text = base64.b64decode(j.get("content", "")).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            out.append((f"GitHub LICENSE 파일 · {owner}/{repo}", j.get("html_url") or url, clean(text, 1200)))
    s3, _, rb = http_get(f"{base}/readme", hdr)
    if s3 == 200:
        j = json.loads(rb)
        try:
            readme = base64.b64decode(j.get("content", "")).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            readme = ""
        if readme:
            out.append((f"GitHub README 발췌 · {owner}/{repo}", j.get("html_url") or url,
                        clean(clean(readme, 600) + " … " + keyword_windows(readme))))
    return out


def _arxiv_entries(xml_text: str) -> list[dict]:
    if "<!ENTITY" in xml_text:  # 엔티티 확장 공격 방지
        return []
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for e in root.findall("a:entry", ns):
        g = lambda tag: (e.findtext(tag, default="", namespaces=ns) or "").strip()  # noqa: E731
        out.append({
            "id": g("a:id"), "title": clean(g("a:title"), 240), "summary": clean(g("a:summary"), 900),
            "published": g("a:published")[:10], "comment": clean(g("x:comment"), 200),
            "journal": clean(g("x:journal_ref"), 200),
            "authors": ", ".join((a.findtext("a:name", default="", namespaces=ns) or "") for a in e.findall("a:author", ns)[:6]),
        })
    return out


def arxiv_paper(arxiv_id: str) -> list[Evidence]:
    status, _, xml_text = http_get(f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}")
    if status != 200:
        return []
    entries = _arxiv_entries(xml_text)
    if not entries or not entries[0]["title"]:
        return []
    e = entries[0]
    lic = ""
    s2, _, absp = http_get(f"https://arxiv.org/abs/{arxiv_id}", max_bytes=300_000)
    if s2 == 200:
        m = re.search(r'href="(https?://[^"]*licenses?/[^"]*)"', absp)
        lic = m.group(1) if m else ""
    facts = f"저자: {e['authors']}; 게재일: {e['published']}; 논문 라이선스: {lic or '확인 불가'}"
    if e["journal"]:
        facts += f"; 게재지: {e['journal']}"
    if e["comment"]:
        facts += f"; 저자 코멘트: {e['comment']}"
    return [(f"arXiv 논문 · {e['title']}", f"https://arxiv.org/abs/{arxiv_id}", clean(f"{facts} | 초록: {e['summary']}"))]


def arxiv_search(name: str, limit: int = 2) -> list[Evidence]:
    q = urllib.parse.quote(f'ti:"{name}"')
    status, _, xml_text = http_get(f"https://export.arxiv.org/api/query?search_query={q}&max_results={limit}")
    if status != 200:
        return []
    return [(f"arXiv 논문(이름 검색 후보) · {e['title']}", e["id"].replace("http://", "https://"),
             clean(f"저자: {e['authors']}; 게재일: {e['published']} | 초록: {e['summary']}"))
            for e in _arxiv_entries(xml_text) if e["title"]]


def zenodo_record(rec_id: str) -> list[Evidence]:
    status, _, body = http_get(f"https://zenodo.org/api/records/{rec_id}")
    if status != 200:
        return []
    d = json.loads(body)
    md = d.get("metadata") or {}
    lic = (md.get("license") or {}).get("id") or (md.get("license") or {}).get("title") or "미명시"
    creators = ", ".join(c.get("name", "") for c in (md.get("creators") or [])[:5])
    facts = (f"license={lic}; access_right={md.get('access_right')}; publication_date={md.get('publication_date')}; "
             f"creators={creators}; doi={d.get('doi') or md.get('doi')}")
    desc = clean(strip_tags(md.get("description") or ""), 800)
    return [(f"Zenodo 레코드 · {clean(md.get('title') or rec_id, 160)}", f"https://zenodo.org/records/{rec_id}",
             clean(f"{facts} | 설명: {desc}"))]


def crossref_doi(doi: str) -> list[Evidence]:
    status, _, body = http_get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
    if status != 200:
        return []
    m = json.loads(body).get("message") or {}
    lic = "; ".join(l.get("URL", "") for l in (m.get("license") or [])[:3]) or "미명시"
    title = clean(" ".join(m.get("title") or [doi]), 200)
    year = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    return [(f"Crossref DOI 메타데이터 · {title}", f"https://doi.org/{doi}",
             clean(f"publisher={m.get('publisher')}; type={m.get('type')}; year={year}; license={lic}"))]


def generic_page(url: str) -> list[Evidence]:
    status, ctype, body = http_get(url)
    if status != 200 or not body:
        return []
    if "html" not in ctype.lower() and "<html" not in body[:2000].lower():
        return [(f"웹 문서 · {urllib.parse.urlparse(url).netloc}", url, clean(body, 1500))] if "text" in ctype.lower() else []
    pg = parse_html(body)
    parts = []
    if pg["description"]:
        parts.append(f"설명: {pg['description']}")
    ld = jsonld_facts(pg["jsonld"])
    if ld:
        parts.append(f"구조화 메타데이터(JSON-LD): {ld}")
    kw = keyword_windows(pg["text"])
    parts.append(f"본문 발췌: {clean(pg['text'], 500)}" + (f" … 핵심 문장: {kw}" if kw else ""))
    return [(f"웹 문서 · {pg['title'] or urllib.parse.urlparse(url).netloc}", url, clean(" | ".join(parts)))]


def wikipedia_summary(name: str) -> list[Evidence]:
    title = urllib.parse.quote(name.strip().replace(" ", "_"))
    status, _, body = http_get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
    if status != 200:
        return []
    d = json.loads(body)
    if d.get("type") == "disambiguation" or not d.get("extract"):
        return []
    return [(f"Wikipedia · {d.get('title')}", (d.get("content_urls") or {}).get("desktop", {}).get("page", ""),
             clean(d["extract"], 900))]


# ───────────────────────── URL 분류 · 수집 ─────────────────────────
def classify_url(url: str) -> tuple[str, tuple]:
    p = urllib.parse.urlparse(url)
    host, parts = (p.hostname or "").lower(), [x for x in p.path.split("/") if x]
    if host in ("huggingface.co", "www.huggingface.co") and len(parts) >= 3 and parts[0] == "datasets":
        return "hf", (f"{parts[1]}/{parts[2]}",)
    if host in ("huggingface.co", "www.huggingface.co") and len(parts) == 2 and parts[0] == "datasets":
        return "hf", (parts[1],)
    if host in ("github.com", "www.github.com") and len(parts) >= 2:
        return "github", (parts[0], re.sub(r"\.git$", "", parts[1]))
    if host in ("arxiv.org", "www.arxiv.org", "export.arxiv.org") and len(parts) >= 2 and parts[0] in ("abs", "pdf", "html"):
        return "arxiv", (re.sub(r"(\.pdf|v\d+)$", "", "/".join(parts[1:]).removesuffix(".pdf")),)
    if host == "zenodo.org" and len(parts) >= 2 and parts[0] in ("records", "record"):
        return "zenodo", (parts[1],)
    if host in ("doi.org", "dx.doi.org") and parts:
        return "doi", ("/".join(parts),)
    return "generic", (url,)


def extract_urls(fields: dict[str, str]) -> list[str]:
    order = ("dataset_repo_url", "homepage_url", "paper_urls", "code_repo_url", "litigation_url",
             "related_datasets", "extra_notes")
    urls: list[str] = []
    for key in order:
        for u in URL_RE.findall(fields.get(key) or ""):
            u = u.rstrip(".,;:)]'\"")
            if u not in urls:
                urls.append(u)
    return urls


def _fetch(kind: str, args: tuple) -> list[Evidence]:
    if kind == "hf":
        return hf_dataset(args[0])
    if kind == "github":
        return github_repo(*args)
    if kind == "arxiv":
        return arxiv_paper(args[0])
    if kind == "zenodo":
        return zenodo_record(args[0])
    if kind == "doi":
        return crossref_doi(args[0])
    return generic_page(args[0])


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", name.lower()) if len(t) >= 3]


def collect_primary_evidence(name: str, fields: dict[str, str], max_items: int = MAX_ITEMS) -> list[Evidence]:
    """요청의 URL 과 데이터셋 이름으로 1차 자료를 모은다. 실패한 원천은 건너뛴다."""
    evidence: list[Evidence] = []
    used: list[str] = []

    def add(items: list[Evidence], label: str) -> None:
        if items:
            used.append(label)
        for it in items:
            if it[1] and all(it[1] != e[1] for e in evidence) and len(evidence) < max_items:
                evidence.append(it)

    for url in extract_urls(fields)[:8]:
        kind, args = classify_url(url)
        try:
            add(_fetch(kind, args), kind)
        except Exception as exc:  # noqa: BLE001 - 한 원천의 실패가 전체를 막지 않게
            print(f"[diag] evidence {kind} 실패: {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)

    # 이름 기반 보강: 데이터셋 저장소 근거가 없을 때만(공식 여부는 미확인으로 표시)
    name = (name or "").strip()
    has_dataset_source = any(u.startswith(("hf", "zenodo")) for u in used)
    if name and not has_dataset_source:
        toks = _name_tokens(name)
        try:
            status, _, body = http_get(f"https://huggingface.co/api/datasets?search={urllib.parse.quote(name)}&limit=5")
            if status == 200:
                for d in json.loads(body):
                    rid = d.get("id", "")
                    if rid and toks and all(t in rid.lower() for t in toks[:2]):
                        add(hf_dataset(rid, with_readme=False, candidate=True), "hf-search")
                        if used.count("hf-search") >= 2:
                            break
        except Exception as exc:  # noqa: BLE001
            print(f"[diag] evidence hf-search 실패: {type(exc).__name__}", file=sys.stderr)
    if name and "arxiv" not in used:
        try:
            add(arxiv_search(name), "arxiv-search")
        except Exception as exc:  # noqa: BLE001
            print(f"[diag] evidence arxiv-search 실패: {type(exc).__name__}", file=sys.stderr)
    if name:
        try:
            add(wikipedia_summary(name), "wikipedia")
        except Exception as exc:  # noqa: BLE001
            print(f"[diag] evidence wikipedia 실패: {type(exc).__name__}", file=sys.stderr)

    # 전체 분량 제한(뒤쪽 항목부터 줄임)
    total = 0
    trimmed: list[Evidence] = []
    for t, u, s in evidence:
        room = TOTAL_MAX - total
        if room <= 200:
            break
        s = s[:room]
        total += len(s)
        trimmed.append((t, u, s))
    print(f"[diag] primary_evidence sources={used} items={len(trimmed)} chars={total}", file=sys.stderr)
    return trimmed
