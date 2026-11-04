"""영어 지원(docs/i18n.js · docs/i18n-en.js) 회귀 테스트.

- index.html 의 한국어 '번역 단위'(docs/i18n.js 의 isUnit/skeleton 규칙과 동일)가 모두 영어 사전에 있는지
- 사전 값에 한글이 남아 있지 않은지(의도된 예외 제외), 태그 골격이 원문과 같은지
- 정규식 규칙이 유효한지
화면이 나중에 그리는 동적 문구(대시보드 등)는 브라우저가 필요하므로 tools/i18n_sweep.js 로 점검한다.
"""

from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HAN = re.compile(r"[가-힣]")
INLINE = {"b", "strong", "em", "i", "a", "code", "span", "br", "kbd", "sub", "small", "u", "mark"}
VOID = {"br", "input", "img", "meta", "link", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
ATTRS = ("placeholder", "title", "aria-label", "alt")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_dictionary() -> dict:
    src = (DOCS / "i18n-en.js").read_text(encoding="utf-8")
    body = src[src.index("window.I18N_EN =") + len("window.I18N_EN ="):].strip().rstrip(";")
    return json.loads(body)


class Node:
    def __init__(self, tag: str | None, attrs: dict | None = None, parent: "Node | None" = None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs or {}, parent
        self.children: list = []  # Node 또는 str


class Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def skeleton(n: Node) -> str:
    out = ""
    for c in n.children:
        if isinstance(c, str):
            out += esc(c)
        elif c.tag == "br":
            out += "<br>"
        else:
            out += f"<{c.tag}>{skeleton(c)}</{c.tag}>"
    return out


def text_of(n: Node) -> str:
    return "".join(c if isinstance(c, str) else text_of(c) for c in n.children)


def is_unit(n: Node) -> bool:
    has_han = False
    for c in n.children:
        if isinstance(c, str):
            has_han = has_han or bool(HAN.search(c))
        else:
            if c.tag not in INLINE:
                return False
            has_han = has_han or bool(HAN.search(text_of(c)))
    return has_han


def skipped(n: Node) -> bool:
    while n is not None:
        if n.tag in ("script", "style", "textarea", "pre") or n.attrs.get("translate") == "no":
            return True
        n = n.parent
    return False


def collect(tree_root: Node):
    """(번역 단위/텍스트 키 목록, 속성 문자열 목록)"""
    keys: list[str] = []
    attrs: list[str] = []

    def walk(n: Node):
        if n.tag is None or skipped(n):
            return
        for a in ATTRS:
            v = n.attrs.get(a)
            if v and HAN.search(v):
                attrs.append(norm(v))
        if HAN.search(text_of(n)) and is_unit(n):
            keys.append(norm(skeleton(n)))
            for c in n.children:  # 하위 요소의 속성도 점검
                if not isinstance(c, str):
                    walk_attrs(c)
            return
        for c in n.children:
            if isinstance(c, str):
                if HAN.search(c) and not skipped(n):
                    keys.append(norm(c))
            else:
                walk(c)

    def walk_attrs(n: Node):
        for a in ATTRS:
            v = n.attrs.get(a)
            if v and HAN.search(v) and not skipped(n):
                attrs.append(norm(v))
        for c in n.children:
            if not isinstance(c, str):
                walk_attrs(c)

    def find(n: Node, tag: str):
        for c in n.children:
            if not isinstance(c, str):
                if c.tag == tag:
                    return c
                r = find(c, tag)
                if r:
                    return r
        return None

    # <title>·<meta> 는 번역기가 document.title / 속성으로 따로 처리하므로 본문(body)만 단위로 점검한다.
    walk(find(tree_root, "body"))
    return keys, attrs


def tags(s: str) -> list[str]:
    return re.findall(r"</?[a-z][a-z0-9]*>", s)


class I18nTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dict = load_dictionary()
        t = Tree()
        t.feed((DOCS / "index.html").read_text(encoding="utf-8"))
        cls.tree = t.root
        cls.rules = [(re.compile(p), r) for p, r in cls.dict.get("rules", [])]

    def covered(self, key: str) -> bool:
        return key in self.dict["map"] or any(rx.search(key) for rx, _ in self.rules)

    def test_every_static_korean_unit_has_an_english_translation(self) -> None:
        keys, attrs = collect(self.tree)
        self.assertGreater(len(keys), 60, "번역 단위 추출이 비정상적으로 적다 — 추출 규칙 확인")
        missing = sorted({k for k in keys + attrs if not self.covered(k)})
        self.assertEqual(missing, [], "docs/i18n-en.js 에 번역이 없는 문구:\n  " + "\n  ".join(m[:120] for m in missing))

    def test_title_and_meta_description_are_translated(self) -> None:
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        title = norm(re.search(r"<title>(.*?)</title>", html, re.S).group(1))
        desc = norm(re.search(r'<meta name="description" content="(.*?)"', html, re.S).group(1))
        self.assertIn(title, self.dict["map"])
        self.assertIn(desc, self.dict["map"])

    def test_translations_keep_the_same_tags_as_the_source(self) -> None:
        # 속성은 같은 태그 순서로 원본에서 복사되므로, 태그 구성이 다르면 링크 등이 어긋난다.
        bad = [
            k for k, v in self.dict["map"].items()
            if tags(k) != tags(v) and not (tags(k) == [] and tags(v) == [])
            # 영어판에만 <em> 안내 문구를 덧붙인 항목은 태그가 늘어난다(허용: 원본 태그가 부분집합)
            and not all(t in tags(v) for t in tags(k))
        ]
        self.assertEqual(bad, [], "태그 구성이 원문과 다른 번역")

    def test_english_values_contain_no_untranslated_korean(self) -> None:
        # 의도적으로 한글을 남기는 항목(언어 이름 등)이 생기면 여기서 허용 목록에 추가한다.
        allowed: set[str] = set()
        leftover = [k for k, v in self.dict["map"].items() if HAN.search(v) and k not in allowed]
        self.assertEqual(leftover, [], "영어 번역에 한글이 남아 있음")

    def test_rules_are_valid_regular_expressions_and_substitutions(self) -> None:
        for pattern, repl in self.dict.get("rules", []):
            rx = re.compile(pattern)  # 유효성
            groups = rx.groups
            for n in re.findall(r"[$%](\d)", repl):
                self.assertLessEqual(int(n), groups, f"규칙이 존재하지 않는 캡처 그룹을 참조: {pattern}")
        for pattern, _ in self.dict.get("sub", []):
            re.compile(pattern)

    def test_language_switch_is_wired_in_index_html(self) -> None:
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-set-lang="ko"', html)
        self.assertIn('data-set-lang="en"', html)
        self.assertLess(html.index("i18n-en.js"), html.index("i18n.js"))
        self.assertLess(html.index("I18N.init()"), html.index('src="app.js"'))


if __name__ == "__main__":
    unittest.main()
