# SEND PDF collection runbook

This tool is a source discovery and acquisition workflow. It does **not** create, assess or validate CDI evidence or knowledge objects. A downloaded file is a source candidate with acquisition provenance only.

## Scope for this pilot

The automated path is intentionally PDF/data-first:

- Ofsted/CQC area SEND inspection PDFs;
- GOV.UK and Department for Education SEND research/evaluation PDFs;
- individually verified official local-authority SEND strategy or evaluation PDFs; and
- other directly downloadable official research documents.

The Perplexity-derived 153-local-authority CSV is a discovery directory, not a document queue. Its constructed links are retained to measure coverage and guide human discovery, but the collector never fetches them as reports.

HTML pages, Local Offer sites and Ombudsman decisions are deliberately outside the automatic fetch path. Collect those with Site Scraper and import its local export with `import-crawl-export`; crawler-provided material stays distinct from independently retrieved originals. The collector never converts HTML into a synthetic PDF.

## Before every run

1. Check the publisher's current terms, reuse/licence conditions and `robots.txt` for every collection host. Do not bypass any of them, authentication, access controls or rate limits.
2. Use a durable archive directory **outside** this Git checkout. The collector writes original bytes, checksums, per-object metadata and run manifests there; it does not add source bytes to Git.
3. Start with the candidate review and a small dry-run. Only pass `--execute --accept-terms HOST` after the human running the command has checked that host's terms and reuse conditions.

## Simple PDF workflow

From the repository root, create the normalized source directory and add the maintained official-PDF batch:

```bash
python3 scripts/send_collect.py catalogue --output intake/run-output/send-manifest.json
python3 scripts/send_collect.py import-urls \
  --input intake/batches/official_send_pdf_candidates_2026-10-22.csv \
  --manifest intake/run-output/send-manifest.json \
  --output intake/run-output/official-send-pdf-manifest.json
```

Review the exact direct document candidates before attempting retrieval. This command does not contact any publisher:

```bash
python3 scripts/send_collect.py discover-pdfs \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --collection-id official-send-pdf-2026-10-22 \
  --output intake/run-output/official-send-pdf-review.csv
```

Run a bounded dry-run first (again, no network retrieval):

```bash
python3 scripts/send_collect.py fetch \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive \
  --collection-id official-send-pdf-2026-10-22 --limit 8
```

After checking the current terms and reuse conditions for `files.ofsted.gov.uk` and `assets.publishing.service.gov.uk`, retrieve the reviewed eight-document batch at a courteous rate:

```bash
python3 scripts/send_collect.py fetch \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive \
  --execute --accept-terms files.ofsted.gov.uk \
  --accept-terms assets.publishing.service.gov.uk \
  --collection-id official-send-pdf-2026-10-22 --limit 8 --rate-limit 2
```

Only expand after reviewing the report. The Essex PDF already held in the CDI repository is intentionally skipped, so a bounded collection may include a skip.

```bash
python3 scripts/send_collect.py status \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive --json
```

`discover-pdfs` and `fetch` select only `direct_pdf` and `direct_data` records. Verified direct official PDF/data URLs can be submitted through `import-urls` only on the narrowly approved publisher hosts. Directory, search and collection URLs are refused.

## Expanding coverage safely

For each authority, use the directory as a starting point to find an individual, direct official PDF. Review the document URL, publisher, licence/terms, provenance and authority identifier, then add one CSV row matching `official_send_pdf_candidates_2026-10-22.csv`. Do not add a category page, search results page or a general Local Offer page.

Create a new named batch, import it into the manifest, run `discover-pdfs`, then dry-run and execute a small approval-reviewed subset. The host allow-list is deliberately narrow; a new local-authority host requires a separate security and terms review before it can be enabled. Do not use a proxy, URL credentials, redirects to another host or an in-checkout archive to work around that control.

For a larger already-reviewed batch, change only the limit after inspecting status:

```bash
python3 scripts/send_collect.py fetch \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive \
  --execute --accept-terms files.ofsted.gov.uk \
  --accept-terms assets.publishing.service.gov.uk \
  --collection-id official-send-pdf-2026-10-22 --limit 20 --rate-limit 2
```

## Site Scraper import for HTML material

The import path accepts CSV with `url` and optional `title`, `captured_at`, `collection_id`, plus one of `content_path`, `text` or `html`. A `content_path` must stay within the export directory. Captures remain labelled as externally supplied material and are never represented as a direct download or a PDF.

```bash
python3 scripts/send_collect.py import-crawl-export \
  --input /path/site-scraper-export.csv \
  --archive-root /path/outside/git/send-archive
```

## Status and metadata-only sharing

```bash
python3 scripts/send_collect.py status \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive

python3 scripts/send_collect.py export-metadata \
  --archive-root /path/outside/git/send-archive \
  --output intake/run-output/send-archive-metadata.json
```

- `registered` includes discovery-only records as well as candidates.
- `candidate_coverage` shows direct PDF/data candidates and the number of covered authorities against the directory's 153 authorities.
- `downloaded` is a newly stored source; `duplicate` means a new source relationship shares existing bytes; `skipped` means an existing archive entry or known CDI-held source; `blocked` means a safety/permission guard stopped the attempt; `failed` means an attempted operation did not complete.

The report retains durable archive counts as well as latest-run counts. Acquisition success does not validate a document or create CDI evidence.

## Pilot result: 22 October 2026

The reviewed batch has 21 direct PDF candidates: 17 Ofsted/CQC area SEND reports (including the CDI-held Essex report) and four DfE research/evaluation PDFs. It covers 17 of the directory's 153 authorities at the candidate stage.

The dry-run selected eight records: seven were ready for retrieval and the CDI-held Essex report was skipped. After checking the current [GOV.UK terms and conditions](https://www.gov.uk/help/terms-conditions) and [Ofsted copyright terms](https://reports.ofsted.gov.uk/copyright), and acknowledging the relevant hosts on the command line, the live pilot stored 13 Ofsted/CQC PDFs (two more were resumed/skipped because they were already archived). The durable external archive now holds 16 Ofsted/CQC PDFs across 16 authorities, plus three pre-existing GOV.UK HTML originals retained from the earlier pilot.

The four DfE PDF URLs on `assets.publishing.service.gov.uk` were deliberately blocked in the initial pilot because the host returned HTTP 404 for `robots.txt`; no workaround was attempted. The collector now implements the narrow RFC 9309 treatment for that result: only `404` and `410` mean no robots rules were found, after the existing host, terms and request-safety controls pass. `401`, `403`, `429`, other 4xx responses, 5xx responses, timeouts and unsafe redirects remain blocked.
