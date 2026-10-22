# SEND rapid-collection runbook

This is a source discovery and acquisition tool. It does **not** create, assess or validate CDI evidence or knowledge objects. A downloaded item is only a source candidate with acquisition provenance.

## Before every run

1. Check the publisher's current terms, reuse/licence conditions and `robots.txt` for each host. Do not bypass either, authentication, access controls or rate limits.
2. Use an archive directory outside this Git checkout. The collector writes original bytes, checksums, per-object metadata and local run manifests there; it does not add raw content to Git.
3. Start with dry-run and a small, named subset. The 153-authority CSV is discovery-only: its 459 URLs are constructed search/index entry points, not 459 reports.

## First bounded Essex/national run

From the repository root, create the manifest and inspect the direct queue:

```bash
python3 scripts/send_collect.py catalogue --output intake/run-output/send-manifest.json
python3 scripts/send_collect.py status --manifest intake/run-output/send-manifest.json --archive-root /path/outside/git/send-archive
python3 scripts/send_collect.py fetch --manifest intake/run-output/send-manifest.json --archive-root /path/outside/git/send-archive --source-key essex-lgo-25-018-721 --source-key national-send-inspections-main --limit 2
```

The last command is deliberately dry-run. After checking current terms/reuse conditions for the exact hosts and confirming robots access, explicitly opt in:

```bash
python3 scripts/send_collect.py fetch --manifest intake/run-output/send-manifest.json --archive-root /path/outside/git/send-archive --execute --accept-terms www.lgo.org.uk --accept-terms www.gov.uk --source-key essex-lgo-25-018-721 --source-key national-send-inspections-main --limit 2 --rate-limit 2
```

An unavailable or disallowing `robots.txt`, terms not acknowledged on the command line, a private/network or cross-host redirect, a size-cap breach, or an HTTP failure is recorded as blocked or failed. Do not override these safeguards. The existing Essex Ofsted PDF is skipped because the repository already holds it; use `--include-known-source` only where a fresh external copy is genuinely necessary. Repeat the same command safely: source-key and checksum state avoid blind re-downloads and duplicate bytes.

## Broader collection from verified individual URLs

Do not fetch authority listing, category listing or constructed search entries as though they were reports. Add verified individual official URLs through `import-urls`; this creates a new manifest and never edits the supplied Perplexity seeds. The importer accepts only the narrow official host allow-list for this pilot, rejects directory/search/collection URLs, and requires title, document class, verification state and a rights-check note.

```bash
python3 scripts/send_collect.py import-urls --input intake/batches/verified_send_documents_2026-10-22.csv --manifest intake/run-output/send-manifest.json --output intake/run-output/verified-send-manifest.json
python3 scripts/send_collect.py fetch --manifest intake/run-output/verified-send-manifest.json --archive-root /path/outside/git/send-archive --collection-id verified-send-2026-10-22 --limit 20
```

The batch selector follows merged URLs as well as newly imported ones, so a URL that was already a direct seed is not duplicated. Imported untrusted URLs cannot select arbitrary hosts, use proxy settings, follow cross-host document redirects, or set an archive root inside this Git checkout.

For a bounded direct queue, use `--source-key` and a limit. Expand only after reviewing the status result:

```bash
python3 scripts/send_collect.py fetch --manifest intake/run-output/send-manifest.json --archive-root /path/outside/git/send-archive --execute --accept-terms files.ofsted.gov.uk --accept-terms www.lgo.org.uk --source-key essex-ofsted-2026 --source-key essex-lgo-25-018-721 --source-key essex-lgo-21-016-894 --limit 3 --rate-limit 2
python3 scripts/send_collect.py status --manifest intake/run-output/send-manifest.json --archive-root /path/outside/git/send-archive --json
```

To share the acquisition catalogue without raw source bytes or local paths, create an explicitly metadata-only export:

```bash
python3 scripts/send_collect.py export-metadata --archive-root /path/outside/git/send-archive --output intake/run-output/send-archive-metadata.json
```

## External site-scraper export

The importer accepts CSV with `url` and optional `title`, `captured_at`, `collection_id`, plus one of `content_path`, `text` or `html`. A `content_path` must be relative to the export directory; path escapes are refused. The crawler's capture and metadata are archived as crawler-supplied, not as independently downloaded or verified material.

```bash
python3 scripts/send_collect.py import-crawl-export --input /path/permitted-scraper-export.csv --archive-root /path/outside/git/send-archive
python3 scripts/send_collect.py status --archive-root /path/outside/git/send-archive
```

The included `tests/fixtures/sample-crawl-export.csv` is a format example only.

## What the status means

- `registered`: records in the current normalized catalogue, including discovery-only entries.
- `downloaded`: original bytes stored for a newly acquired source.
- `skipped`: source key already exists in the external archive.
- `duplicate`: different source key with an identical SHA-256 object; bytes are stored once.
- `blocked`: safety/permission guard stopped acquisition.
- `failed`: an attempted operation did not complete.

The status report deliberately retains verification, reuse and coverage caveats. Archive success is not source validation, evidence extraction or CDI ingestion.

`latest_run_outcomes` describes only the most recent run. `archive.externally_held_sources` and `unique_content_objects` are durable archive-state counts, so a later `skipped` result never erases the fact that a source was obtained. A PDF held in this Git repository is deliberately not counted as externally archived.

## Verified batch result: 22 October 2026

`intake/batches/verified_send_documents_2026-10-22.csv` contains 20 individual URLs: 14 LGSCO SEND decisions (including Essex and contrasting authorities), 3 Ofsted local-area SEND PDFs, and 3 national GOV.UK reports. Its safe dry-run selected all 20 and wrote no content.

After checking GOV.UK terms/OGL and the OGL statement in the Ofsted PDFs, a bounded six-item live attempt stored all 3 GOV.UK pages and all 3 Ofsted PDFs in an external temporary archive. The initial three Ofsted attempts were blocked because their official robots redirect host was not yet allow-listed; the collector was corrected to allow that official host **only for robots policy retrieval**, and the retry downloaded all three. The 14 LGSCO decisions remain dry-run-only: the LGSCO copyright page timed out during preparation, so its terms were not acknowledged and no LGSCO downloads were attempted.
