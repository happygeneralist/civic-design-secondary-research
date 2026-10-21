from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


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
        collector.write_run(self.archive, "fetch", [
            {"source_key": "a", "status": "downloaded", "host": "files.ofsted.gov.uk", "local_authority": "Essex"},
            {"source_key": "b", "status": "blocked", "host": "www.lgo.org.uk", "local_authority": "Essex"},
        ])
        report = collector.status_report(manifest, self.archive)
        self.assertEqual(report["registered"], 469)
        self.assertEqual(report["outcomes"]["downloaded"], 1)
        self.assertEqual(report["outcomes"]["blocked"], 1)
        self.assertEqual(report["authority_coverage"]["covered"], 1)

    def test_existing_repository_source_is_skipped_unless_explicitly_requested(self) -> None:
        manifest = collector.catalogue(ROOT / "intake/seeds/SEND_all_153_local_authorities.csv", ROOT / "intake/seeds/direct_sources.csv")
        args = SimpleNamespace(accept_terms=[], limit=1, source_key=["essex-ofsted-2026"], include_known_source=False,
                               execute=True, timeout=1, max_bytes=100, retries=0, backoff=0, rate_limit=0)
        events, _ = collector.fetch(manifest, self.archive, args)
        self.assertEqual(events[0]["status"], "skipped")
        self.assertEqual(events[0]["reason"], "already held in repository source archive")


if __name__ == "__main__":
    unittest.main()
