from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "send_collect.py"
SPEC = importlib.util.spec_from_file_location("send_collect", MODULE_PATH)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class SendCollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="send-collect-test-"))
        self.archive = self.work / "archive"

    def tearDown(self) -> None:
        shutil.rmtree(self.work)

    def test_catalogue_preserves_seed_separation_and_counts(self) -> None:
        manifest = collector.catalogue(ROOT / "intake/seeds/SEND_all_153_local_authorities.csv", ROOT / "intake/seeds/direct_sources.csv")
        self.assertEqual(manifest["counts"]["authority_rows"], 153)
        self.assertEqual(manifest["counts"]["discovery_records"], 459)
        self.assertEqual(manifest["counts"]["direct_seed_records"], 10)
        self.assertEqual(manifest["counts"]["total_records"], 469)
        direct = next(item for item in manifest["records"] if item["source_key"] == "essex-ofsted-2026")
        self.assertEqual(direct["document_url"], "https://files.ofsted.gov.uk/v1/file/50302461")
        self.assertIsNone(direct["discovery_url"])
        self.assertTrue(direct["repository_archive_ref"].endswith("Essex_Area_SEND_Full_inspection_Jan26.pdf"))
        discovery = next(item for item in manifest["records"] if item["source_key"] == "authority-e10000012-ofsted_area_index")
        self.assertEqual(discovery["record_kind"], "discovery")
        self.assertIsNone(discovery["document_url"])

    def test_url_normalisation_rejects_non_web_and_credentials(self) -> None:
        self.assertEqual(collector.canonical_url("HTTPS://Example.ORG:443/report#part"), "https://example.org/report")
        with self.assertRaises(collector.CollectionError):
            collector.canonical_url("file:///tmp/report.pdf")
        with self.assertRaises(collector.CollectionError):
            collector.canonical_url("https://user:secret@example.org/report")

    def test_content_addressed_archive_deduplicates_bytes_without_overwrite(self) -> None:
        state = collector.archive_state(self.archive)
        first, first_data = collector.archive_bytes(self.archive, state, source_key="one", original_url="https://example.org/one", final_url="https://example.org/one", body=b"report", content_type="application/pdf", metadata={"collection_provenance": "test"})
        second, second_data = collector.archive_bytes(self.archive, state, source_key="two", original_url="https://example.org/two", final_url="https://example.org/two", body=b"report", content_type="application/pdf", metadata={"collection_provenance": "test"})
        self.assertEqual(first, "downloaded")
        self.assertEqual(second, "duplicate")
        self.assertEqual(first_data["archive_path"], second_data["archive_path"])
        self.assertTrue((self.archive / first_data["archive_path"]).exists())
        self.assertEqual(len(state["hashes"]), 1)
        exported = collector.metadata_export(self.archive)
        self.assertEqual(exported["sources"][0]["sha256"], first_data["sha256"])
        self.assertNotIn("archive_path", exported["sources"][0])
        self.assertEqual({item["source_key"] for item in exported["sources"][0]["relationships"]}, {"one", "two"})

    def test_importer_records_crawler_provenance_and_rejects_path_escape(self) -> None:
        fixture_dir = ROOT / "tests/fixtures"
        copied = self.work / "export"
        shutil.copytree(fixture_dir, copied)
        events, run = collector.import_crawl_export(copied / "sample-crawl-export.csv", self.archive)
        self.assertEqual(events[0]["status"], "downloaded")
        metadata = next((self.archive / "objects").glob("*/metadata.json"))
        value = json.loads(metadata.read_text())
        self.assertEqual(value["collection_provenance"], "external_site_scraper_export")
        self.assertEqual(value["crawler_metadata"]["collection_id"], "example-batch-1")
        self.assertTrue(run.exists())
        escaped = self.work / "bad.csv"
        with escaped.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["url", "content_path"]); writer.writeheader(); writer.writerow({"url": "https://example.org/x", "content_path": "../outside.html"})
        bad, _ = collector.import_crawl_export(escaped, self.archive)
        self.assertEqual(bad[0]["status"], "failed")
        self.assertIn("within the export directory", bad[0]["reason"])

    def test_status_reports_latest_outcomes_and_authority_coverage(self) -> None:
        manifest = collector.catalogue(ROOT / "intake/seeds/SEND_all_153_local_authorities.csv", ROOT / "intake/seeds/direct_sources.csv")
        state = collector.archive_state(self.archive)
        collector.archive_bytes(self.archive, state, source_key="a", original_url="https://www.gov.uk/report", final_url="https://www.gov.uk/report", body=b"held", content_type="text/html", metadata={"collection_provenance": "test", "local_authority": "Essex", "ons_code": "E10000012"})
        collector.save_state(self.archive, state)
        collector.write_run(self.archive, "fetch", [{"source_key": "a", "status": "downloaded", "host": "www.gov.uk", "local_authority": "Essex"}])
        collector.write_run(self.archive, "fetch", [{"source_key": "a", "status": "skipped", "host": "www.gov.uk", "local_authority": "Essex"}, {"source_key": "b", "status": "blocked", "host": "www.lgo.org.uk", "local_authority": "Essex"}])
        report = collector.status_report(manifest, self.archive)
        self.assertEqual(report["registered"], 469)
        self.assertEqual(report["latest_run_outcomes"]["skipped"], 1)
        self.assertEqual(report["latest_run_outcomes"]["blocked"], 1)
        self.assertEqual(report["archive"]["externally_held_sources"], 1)
        self.assertEqual(report["authority_coverage"]["externally_held"], 1)

    def test_existing_repository_source_is_skipped_unless_explicitly_requested(self) -> None:
        manifest = collector.catalogue(ROOT / "intake/seeds/SEND_all_153_local_authorities.csv", ROOT / "intake/seeds/direct_sources.csv")
        args = SimpleNamespace(accept_terms=[], limit=1, source_key=["essex-ofsted-2026"], include_known_source=False,
                               execute=True, timeout=1, max_bytes=100, retries=0, backoff=0, rate_limit=0)
        events, _ = collector.fetch(manifest, self.archive, args)
        self.assertEqual(events[0]["status"], "skipped")
        self.assertEqual(events[0]["reason"], "already held in repository source archive")

    def test_verified_url_import_requires_official_individual_urls_and_merges(self) -> None:
        batch = self.work / "urls.csv"
        with batch.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["url", "title", "source_class", "publisher", "local_authority", "ons_code", "source_verification", "rights_check", "discovery_parent_url", "collection_id"])
            writer.writeheader()
            writer.writerow({"url": "https://files.ofsted.gov.uk/v1/file/50233738", "title": "Surrey area SEND inspection", "source_class": "direct_pdf", "publisher": "Ofsted and CQC", "local_authority": "Surrey", "ons_code": "E10000030", "source_verification": "official_direct_pdf_verified", "rights_check": "Open Government Licence stated in report", "discovery_parent_url": "https://reports.ofsted.gov.uk/", "collection_id": "test"})
            writer.writerow({"url": "https://files.ofsted.gov.uk/v1/file/50233738", "title": "Surrey area SEND inspection duplicate provenance", "source_class": "direct_pdf", "publisher": "Ofsted and CQC", "local_authority": "Surrey", "ons_code": "E10000030", "source_verification": "official_direct_pdf_verified", "rights_check": "Open Government Licence stated in report", "discovery_parent_url": "https://reports.ofsted.gov.uk/", "collection_id": "test-2"})
        with mock.patch.object(collector, "assert_safe_url", side_effect=lambda url, _hosts=None: collector.canonical_url(url)):
            records = collector.verified_url_records(batch)
        manifest = collector.merge_manifest(collector.catalogue(ROOT / "intake/seeds/SEND_all_153_local_authorities.csv", ROOT / "intake/seeds/direct_sources.csv"), records)
        self.assertEqual(manifest["counts"]["imported_url_records"], 1)
        self.assertEqual(manifest["counts"]["merged_url_records"], 1)
        self.assertEqual(manifest["counts"]["total_records"], 470)
        bad = self.work / "bad-urls.csv"
        bad.write_text("url,title,source_class,source_verification,rights_check\nhttps://example.org/search/all,No,direct_html,verified_direct,checked\n")
        with self.assertRaises(collector.CollectionError):
            collector.verified_url_records(bad)
        html = self.work / "html-urls.csv"
        html.write_text("url,title,source_class,source_verification,rights_check\nhttps://www.gov.uk/report,No,direct_html,official_direct_html_verified,checked\n")
        with mock.patch.object(collector, "assert_safe_url", side_effect=lambda url, _hosts=None: collector.canonical_url(url)):
            with self.assertRaisesRegex(collector.CollectionError, "direct_pdf or direct_data"):
                collector.verified_url_records(html)

    def test_untrusted_hosts_and_archive_inside_checkout_are_rejected(self) -> None:
        with self.assertRaises(collector.CollectionError):
            collector.assert_safe_url("https://example.org/report", collector.TRUSTED_FETCH_HOSTS)
        with self.assertRaises(collector.CollectionError):
            collector.external_archive_root(ROOT / "intake/run-output/archive", ROOT)

    def test_response_quality_checks_pdf_html_and_block_pages(self) -> None:
        with self.assertRaises(collector.CollectionError):
            collector.validate_response({"source_class": "direct_pdf"}, b"<html>blocked</html>", "text/html")
        with self.assertRaises(collector.CollectionError):
            collector.validate_response({"source_class": "direct_html"}, b"<html><title>Access denied</title></html>", "text/html")
        collector.validate_response({"source_class": "direct_pdf"}, b"%PDF-1.7 report", "application/pdf")
        collector.validate_response({"source_class": "direct_html"}, b"<!doctype html><html><body>report</body></html>", "text/html")

    def test_automated_fetch_selection_excludes_html_and_pdf_review_is_explicit(self) -> None:
        manifest = {"records": [
            {"source_key": "pdf", "source_class": "direct_pdf", "document_url": "https://files.ofsted.gov.uk/v1/file/1", "title": "PDF", "publisher": "Ofsted", "local_authority": "Essex", "ons_code": "E10000012", "source_verification": "official_direct_pdf_verified", "rights_check": "OGL", "collection_id": "batch", "notes": ""},
            {"source_key": "html", "source_class": "direct_html", "document_url": "https://www.gov.uk/page", "title": "HTML", "publisher": "GOV.UK", "local_authority": None, "ons_code": None, "source_verification": "official_direct_html_verified", "rights_check": "OGL", "collection_id": "batch", "notes": ""},
        ]}
        self.assertEqual([item["source_key"] for item in collector.select_fetch_records(manifest, None, set())], ["pdf"])
        self.assertEqual([item["source_key"] for item in collector.pdf_candidate_rows(manifest, "batch")], ["pdf"])

    def test_robots_cross_host_exception_is_only_ofsted_pair(self) -> None:
        def identity(url: str, _hosts: object = None) -> str:
            return url
        with mock.patch.object(collector, "assert_safe_url", side_effect=identity), mock.patch.object(collector, "read_response", return_value=("https://reports.ofsted.gov.uk/robots.txt", b"User-agent: *\nAllow: /", "text/plain")) as read:
            collector.robots_permission("https://files.ofsted.gov.uk/v1/file/1", 1)
            self.assertEqual(read.call_args.kwargs["permitted_cross_host_redirect"], ("files.ofsted.gov.uk", "reports.ofsted.gov.uk"))
        with mock.patch.object(collector, "assert_safe_url", side_effect=identity), mock.patch.object(collector, "read_response", return_value=("https://www.gov.uk/robots.txt", b"User-agent: *\nAllow: /", "text/plain")) as read:
            collector.robots_permission("https://www.gov.uk/report", 1)
            self.assertIsNone(read.call_args.kwargs["permitted_cross_host_redirect"])

    def test_robots_rfc9309_unavailable_and_unreachable_statuses(self) -> None:
        def identity(url: str, _hosts: object = None) -> str:
            return url
        target = "https://assets.publishing.service.gov.uk/report.pdf"
        with mock.patch.object(collector, "assert_safe_url", side_effect=identity):
            with mock.patch.object(collector, "read_response", return_value=("https://assets.publishing.service.gov.uk/robots.txt", b"User-agent: *\nDisallow: /", "text/plain")):
                allowed, note = collector.robots_permission(target, 1)
                self.assertFalse(allowed); self.assertIn("checked", note)
            for status in ("HTTP 404", "HTTP 410"):
                with mock.patch.object(collector, "read_response", side_effect=collector.CollectionError(status)):
                    allowed, note = collector.robots_permission(target, 1)
                    self.assertTrue(allowed); self.assertIn("RFC 9309", note)
            for status in ("HTTP 403", "HTTP 429", "HTTP 503"):
                with mock.patch.object(collector, "read_response", side_effect=collector.CollectionError(status)):
                    allowed, note = collector.robots_permission(target, 1)
                    self.assertIsNone(allowed); self.assertIn(status, note)
            with mock.patch.object(collector, "read_response", side_effect=TimeoutError("timed out")):
                allowed, note = collector.robots_permission(target, 1)
                self.assertIsNone(allowed); self.assertIn("timed out", note)

    def test_crawler_collision_and_size_cap_do_not_overwrite(self) -> None:
        exported = self.work / "export"; exported.mkdir()
        (exported / "one.html").write_text("<html>one</html>")
        csv_path = exported / "crawl.csv"
        csv_path.write_text("url,content_path,collection_id\nhttps://example.org/a,one.html,batch\n")
        first, _ = collector.import_crawl_export(csv_path, self.archive)
        second, _ = collector.import_crawl_export(csv_path, self.archive)
        self.assertEqual(first[0]["status"], "downloaded")
        self.assertEqual(second[0]["status"], "skipped")
        (exported / "one.html").write_text("<html>changed</html>")
        changed, _ = collector.import_crawl_export(csv_path, self.archive)
        self.assertEqual(changed[0]["status"], "blocked")
        capped, _ = collector.import_crawl_export(csv_path, self.work / "small", max_bytes=5)
        self.assertEqual(capped[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
