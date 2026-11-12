"""1차 자료 근거 수집(scripts/evidence_sources.py) 테스트. 네트워크는 쓰지 않는다(http_get 을 대체)."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import evidence_sources as ES  # noqa: E402

HF_JSON = json.dumps({
    "id": "stanfordnlp/imdb", "author": "stanfordnlp", "gated": False, "lastModified": "2024-01-04T12:09:45.000Z",
    "downloads": 100, "tags": ["license:other", "task_categories:text-classification", "language:en", "private:false"],
    "description": "\n\tDataset Card for imdb\n\nLarge Movie Review Dataset.",
    "cardData": {"license": ["other"], "source_datasets": ["original"], "pretty_name": "IMDB"},
})
HF_README = ("---\nlicense: other\n---\n# IMDB\nSome intro text about the dataset. " + "filler " * 200 +
             "The reviews were collected from the web; the license is custom and users must obtain consent. " + "tail " * 50)
GH_REPO = json.dumps({"html_url": "https://github.com/numenta/NAB", "license": {"spdx_id": "AGPL-3.0", "name": "GNU AGPL v3"},
                      "archived": False, "fork": False, "pushed_at": "2025-01-01T00:00:00Z", "stargazers_count": 1900,
                      "topics": ["anomaly-detection"], "description": "Numenta Anomaly Benchmark"})
GH_LICENSE = json.dumps({"html_url": "https://github.com/numenta/NAB/blob/master/LICENSE",
                         "content": base64.b64encode(b"GNU AFFERO GENERAL PUBLIC LICENSE Version 3").decode()})
GH_README = json.dumps({"html_url": "https://github.com/numenta/NAB#readme",
                        "content": base64.b64encode(b"# NAB\nThe data is released under the AGPL license.").decode()})
ARXIV_XML = """<?xml version='1.0'?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry><id>http://arxiv.org/abs/1512.03385v1</id><title>Deep Residual Learning for Image Recognition</title>
<summary>We present a residual learning framework.</summary><published>2015-12-10T00:00:00Z</published>
<author><name>Kaiming He</name></author><arxiv:comment>Tech report</arxiv:comment></entry></feed>"""
ARXIV_ABS = '<html><a href="http://arxiv.org/licenses/nonexclusive-distrib/1.0/">license</a></html>'


class FakeWeb:
    """URL 에 포함된 문자열로 응답을 고르는 가짜 http_get."""

    def __init__(self, routes: dict[str, tuple[int, str, str]]) -> None:
        self.routes, self.calls = routes, []

    def __call__(self, url, headers=None, max_bytes=0):
        self.calls.append(url)
        for key, resp in self.routes.items():
            if key in url:
                return resp
        return 404, "", ""


class SafetyTest(unittest.TestCase):
    def test_blocks_internal_and_unsafe_urls(self) -> None:
        for bad in ("http://127.0.0.1/", "http://10.0.0.5/x", "http://169.254.169.254/latest/meta-data/",
                    "http://[::1]/", "ftp://example.com/x", "file:///etc/passwd", "http://192.168.1.1/",
                    "https://example.com:8443/x", "http://0.0.0.0/"):
            with self.assertRaises(ValueError, msg=bad):
                ES._check_url(bad)

    def test_clean_strips_control_chars_and_limits(self) -> None:
        self.assertEqual(ES.clean("a\x00b\x07c \n\t d"), "a b c d")
        self.assertEqual(len(ES.clean("x" * 5000, 100)), 100)


class ParsingTest(unittest.TestCase):
    def test_classify_url(self) -> None:
        c = ES.classify_url
        self.assertEqual(c("https://huggingface.co/datasets/stanfordnlp/imdb"), ("hf", ("stanfordnlp/imdb",)))
        self.assertEqual(c("https://huggingface.co/datasets/squad"), ("hf", ("squad",)))
        self.assertEqual(c("https://github.com/numenta/NAB.git"), ("github", ("numenta", "NAB")))
        self.assertEqual(c("https://arxiv.org/abs/1512.03385v2"), ("arxiv", ("1512.03385",)))
        self.assertEqual(c("https://arxiv.org/pdf/1512.03385.pdf"), ("arxiv", ("1512.03385",)))
        self.assertEqual(c("https://zenodo.org/records/19102416"), ("zenodo", ("19102416",)))
        self.assertEqual(c("https://doi.org/10.1109/CVPR.2016.90"), ("doi", ("10.1109/CVPR.2016.90",)))
        self.assertEqual(c("https://www.kaggle.com/datasets/a/b")[0], "generic")

    def test_extract_urls_orders_by_priority_and_dedupes(self) -> None:
        f = {"dataset_repo_url": "https://huggingface.co/datasets/a/b\nhttps://zenodo.org/records/1.",
             "paper_urls": "see https://arxiv.org/abs/1512.03385, and https://huggingface.co/datasets/a/b",
             "extra_notes": "note (https://example.com/page)"}
        self.assertEqual(ES.extract_urls(f), ["https://huggingface.co/datasets/a/b", "https://zenodo.org/records/1",
                                              "https://arxiv.org/abs/1512.03385", "https://example.com/page"])

    def test_keyword_windows_finds_license_sentences(self) -> None:
        out = ES.keyword_windows("x " * 500 + "This dataset is released under CC BY 4.0 license. " + "y " * 500)
        self.assertIn("CC BY 4.0", out)
        self.assertLess(len(out), 2500)

    def test_html_title_description_jsonld_and_text(self) -> None:
        doc = ('<html><head><title>My Dataset</title><meta name="description" content="A dataset of faces">'
               '<script type="application/ld+json">{"@type":"Dataset","name":"MyDS","license":"https://creativecommons.org/licenses/by/4.0/"}</script>'
               '<style>.x{}</style></head><body><nav>menu</nav><p>Visible text about consent.</p><script>var a=1</script></body></html>')
        pg = ES.parse_html(doc)
        self.assertEqual(pg["title"], "My Dataset")
        self.assertEqual(pg["description"], "A dataset of faces")
        self.assertIn("Visible text about consent.", pg["text"])
        self.assertNotIn("var a", pg["text"])
        self.assertNotIn("menu", pg["text"])
        self.assertIn("license=https://creativecommons.org/licenses/by/4.0/", ES.jsonld_facts(pg["jsonld"]))

    def test_arxiv_rejects_entity_expansion(self) -> None:
        self.assertEqual(ES._arxiv_entries('<!DOCTYPE x [<!ENTITY a "b">]><feed/>'), [])
        self.assertEqual(ES._arxiv_entries("not xml"), [])


class SourceFetchTest(unittest.TestCase):
    def test_hf_dataset_reports_license_and_readme_windows(self) -> None:
        web = FakeWeb({"/api/datasets/": (200, "application/json", HF_JSON),
                       "/raw/main/README.md": (200, "text/plain", HF_README)})
        with mock.patch.object(ES, "http_get", web):
            ev = ES.hf_dataset("stanfordnlp/imdb")
        self.assertEqual(len(ev), 2)
        self.assertIn("license=['other']", ev[0][2])
        self.assertEqual(ev[0][1], "https://huggingface.co/datasets/stanfordnlp/imdb")
        self.assertIn("consent", ev[1][2])            # 핵심 문장이 발췌에 포함
        self.assertNotIn("license: other\n---", ev[1][2])  # YAML 머리말 제외

    def test_hf_missing_license_is_stated_explicitly(self) -> None:
        d = json.loads(HF_JSON); d["cardData"].pop("license")
        web = FakeWeb({"/api/datasets/": (200, "application/json", json.dumps(d))})
        with mock.patch.object(ES, "http_get", web):
            ev = ES.hf_dataset("a/b", with_readme=False)
        self.assertIn("미명시", ev[0][2])

    def test_hf_not_found_returns_empty(self) -> None:
        with mock.patch.object(ES, "http_get", FakeWeb({})):
            self.assertEqual(ES.hf_dataset("no/such"), [])

    def test_github_repo_license_and_readme(self) -> None:
        web = FakeWeb({"/repos/numenta/NAB/license": (200, "", GH_LICENSE), "/repos/numenta/NAB/readme": (200, "", GH_README),
                       "/repos/numenta/NAB": (200, "", GH_REPO)})
        with mock.patch.object(ES, "http_get", web):
            ev = ES.github_repo("numenta", "NAB")
        titles = [e[0] for e in ev]
        self.assertTrue(any("메타데이터" in t for t in titles) and any("LICENSE" in t for t in titles))
        self.assertIn("AGPL-3.0", ev[0][2])
        self.assertIn("AFFERO", ev[1][2])

    def test_github_token_is_sent_but_never_reported(self) -> None:
        seen = {}

        def fake(url, headers=None, max_bytes=0):
            seen.update(headers or {})
            return 200, "", GH_REPO if url.endswith("/NAB") else "{}"

        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "ghs_secret123"}), mock.patch.object(ES, "http_get", fake):
            ev = ES.github_repo("numenta", "NAB")
        self.assertEqual(seen.get("Authorization"), "Bearer ghs_secret123")
        self.assertNotIn("ghs_secret123", json.dumps(ev))

    def test_arxiv_paper_with_license(self) -> None:
        web = FakeWeb({"export.arxiv.org": (200, "", ARXIV_XML), "arxiv.org/abs/": (200, "text/html", ARXIV_ABS)})
        with mock.patch.object(ES, "http_get", web):
            ev = ES.arxiv_paper("1512.03385")
        self.assertIn("nonexclusive-distrib", ev[0][2])
        self.assertIn("Kaiming He", ev[0][2])

    def test_zenodo_and_crossref(self) -> None:
        z = json.dumps({"doi": "10.5281/zenodo.1", "metadata": {"title": "T", "license": {"id": "cc-by-4.0"},
                                                                 "access_right": "open", "creators": [{"name": "A"}],
                                                                 "description": "<p>desc</p>"}})
        c = json.dumps({"message": {"title": ["Paper"], "publisher": "IEEE", "type": "proceedings-article",
                                    "license": [{"URL": "https://example.com/tdm"}], "issued": {"date-parts": [[2016]]}}})
        with mock.patch.object(ES, "http_get", FakeWeb({"zenodo.org/api": (200, "", z), "crossref.org": (200, "", c)})):
            self.assertIn("cc-by-4.0", ES.zenodo_record("1")[0][2])
            self.assertIn("IEEE", ES.crossref_doi("10.1/x")[0][2])

    def test_generic_page_extracts_license_signals(self) -> None:
        doc = ("<html><head><title>CelebA</title></head><body><p>Intro.</p>" + "<p>filler</p>" * 100 +
               "<p>The dataset is available for non-commercial research purposes only; see the license.</p></body></html>")
        with mock.patch.object(ES, "http_get", FakeWeb({"example.org": (200, "text/html", doc)})):
            ev = ES.generic_page("https://example.org/celeba")
        self.assertIn("non-commercial", ev[0][2])


class CollectTest(unittest.TestCase):
    def fields(self, **kw):
        return {"dataset_repo_url": "", "paper_urls": "", "code_repo_url": "", **kw}

    def test_url_driven_collection_across_sources(self) -> None:
        web = FakeWeb({"/api/datasets/stanfordnlp/imdb": (200, "", HF_JSON), "/raw/main/README.md": (200, "", HF_README),
                       "export.arxiv.org": (200, "", ARXIV_XML), "arxiv.org/abs/": (200, "text/html", ARXIV_ABS),
                       "wikipedia.org": (200, "", json.dumps({"title": "IMDB", "extract": "A movie review set.",
                                                              "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/IMDB"}}}))})
        f = self.fields(dataset_repo_url="https://huggingface.co/datasets/stanfordnlp/imdb", paper_urls="https://arxiv.org/abs/1512.03385")
        with mock.patch.object(ES, "http_get", web):
            ev = ES.collect_primary_evidence("IMDB", f)
        urls = [e[1] for e in ev]
        self.assertIn("https://huggingface.co/datasets/stanfordnlp/imdb", urls)
        self.assertIn("https://arxiv.org/abs/1512.03385", urls)
        self.assertEqual(len(urls), len(set(urls)))
        # 저장소 근거가 있으면 이름 검색 후보(HF search)는 호출하지 않는다.
        self.assertFalse(any("datasets?search=" in c for c in web.calls))

    def test_name_only_request_uses_discovery_and_marks_candidates(self) -> None:
        search = json.dumps([{"id": "someone/celeba-mirror"}, {"id": "other/unrelated"}])
        web = FakeWeb({"datasets?search=": (200, "", search), "/api/datasets/someone/celeba-mirror": (200, "", HF_JSON),
                       "export.arxiv.org": (200, "", ARXIV_XML)})
        with mock.patch.object(ES, "http_get", web):
            ev = ES.collect_primary_evidence("CelebA Mirror", self.fields())
        titles = " | ".join(e[0] for e in ev)
        self.assertIn("공식 여부 미확인", titles)       # 미러를 공식으로 오인하지 않도록 표시
        self.assertNotIn("unrelated", titles)

    def test_one_failing_source_does_not_break_the_rest(self) -> None:
        calls = {"n": 0}

        def fake(url, headers=None, max_bytes=0):
            calls["n"] += 1
            if "huggingface.co" in url:
                raise RuntimeError("network down")
            if "export.arxiv.org" in url:
                return 200, "", ARXIV_XML
            if "arxiv.org/abs" in url:
                return 200, "text/html", ARXIV_ABS
            return 404, "", ""

        f = self.fields(dataset_repo_url="https://huggingface.co/datasets/a/b", paper_urls="https://arxiv.org/abs/1512.03385")
        with mock.patch.object(ES, "http_get", fake):
            ev = ES.collect_primary_evidence("", f)
        self.assertEqual([e[1] for e in ev], ["https://arxiv.org/abs/1512.03385"])

    def test_total_size_is_capped(self) -> None:
        big = json.dumps({"id": "a/b", "cardData": {"license": "x"}, "tags": [], "description": "d " * 3000})
        web = FakeWeb({"/api/datasets/": (200, "", big), "/raw/main/README.md": (200, "", "word " * 90000)})
        f = self.fields(dataset_repo_url="\n".join(f"https://huggingface.co/datasets/o/n{i}" for i in range(8)))
        with mock.patch.object(ES, "http_get", web):
            ev = ES.collect_primary_evidence("", f)
        self.assertLessEqual(sum(len(e[2]) for e in ev), ES.TOTAL_MAX)
        self.assertLessEqual(len(ev), ES.MAX_ITEMS)


if __name__ == "__main__":
    unittest.main()
