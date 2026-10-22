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

## Discover SEND PDFs from verified Ofsted provider archives

`discover-ofsted` is the bounded online discovery step. It only visits a supplied CSV of authority-to-provider-page associations that have been independently verified against the 153-authority seed. It requests the provider pages only after terms acknowledgement and robots approval, extracts only labelled area/local SEND inspection or SEND monitoring/follow-up PDF links, and writes no report bytes.

Start by reconciling against the maintained PDF candidate list so that the resulting review CSV contains only URLs not already known to the manifest:

```bash
python3 scripts/send_collect.py import-urls \
  --input intake/batches/official_send_pdf_candidates_2026-10-22.csv \
  --manifest intake/run-output/send-manifest.json \
  --output intake/run-output/official-send-pdf-manifest.json

python3 scripts/send_collect.py discover-ofsted \
  --input intake/seeds/ofsted_provider_archives_pilot.csv \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --archive-root /path/outside/git/send-archive \
  --output intake/run-output/ofsted-send-novel-candidates.csv \
  --run-root /path/outside/git/send-discovery-runs \
  --execute --accept-terms reports.ofsted.gov.uk --limit 5 --rate-limit 1
```

The candidate CSV is compatible with `import-urls` and preserves the provider archive URL, local authority/ONS code, raw source label, publication date and Ofsted report type. An inspection date is populated only where it is structurally adjacent to the report-group heading; `inspection_date_evidence` records that limited inference. Otherwise it is intentionally blank/`unconfirmed`. Review the provider page and PDF before relying on a date or importing it; discovery does not retrieve the linked PDFs.

```bash
python3 scripts/send_collect.py import-urls \
  --input intake/run-output/ofsted-send-novel-candidates.csv \
  --manifest intake/run-output/official-send-pdf-manifest.json \
  --output intake/run-output/discovered-ofsted-manifest.json

python3 scripts/send_collect.py discover-pdfs \
  --manifest intake/run-output/discovered-ofsted-manifest.json \
  --collection-id ofsted-provider-discovery-YYYY-MM-DD \
  --output intake/run-output/discovered-ofsted-review.csv

python3 scripts/send_collect.py fetch \
  --manifest intake/run-output/discovered-ofsted-manifest.json \
  --archive-root /path/outside/git/send-archive \
  --collection-id ofsted-provider-discovery-YYYY-MM-DD --limit 10
```

Only after that dry-run review and a separate `files.ofsted.gov.uk` terms acknowledgement should an approved subset be fetched. The discovery run reports visited provider archives, SEND candidates found, novel URLs and any authority pages with no matching SEND report; it does not infer that the remaining authorities lack an inspection.

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

### Archive integrity check

Before a live fetch, the archive root must be a pre-existing durable location outside both this checkout and temporary directories. Do not create a substitute archive under `/tmp` or `/private/tmp`. After a fetch, independently verify that every `state.json` hash has a matching object path whose SHA-256 equals the state key, and retain the resulting count with the fetch run manifest. A missing object, malformed metadata file or mismatched hash is a stop condition: do not continue or overwrite the archive.

The archive location is intentionally not recorded in Git. The operator must provide it at execution time; this read-only command reports object, hash and metadata failures without changing the archive:

```bash
python3 scripts/send_collect.py verify-archive \
  --archive-root /durable/external/send-archive --json
```

## Continuation result: 22 October 2026

The continuation checked Ofsted’s [terms of use](https://reports.ofsted.gov.uk/terms-and-conditions) and [copyright notice](https://reports.ofsted.gov.uk/copyright) before retrieval. The site says most content is Crown copyright under the Open Government Licence, subject to stated exceptions. It also requires lawful, non-disruptive use and says its terms may change, so check again for every future run. The collector checked robots access for each provider-page request and each PDF retrieval; it did not bypass an access control or a robots restriction.

The ten reviewed direct PDFs from the original five provider pages were dry-run and then acquired at one request per second into the durable archive outside Git. Result: **downloaded 10, resumed/skipped 0, duplicate 0, blocked 0, failed 0**. `verify-archive` immediately afterwards found **29 objects, 29 valid, 0 failed and 0 orphaned source references**.

The verified provider mapping now has 25 authorities (the original five plus 20 additions) with exact ONS-code reconciliation against the 153-authority seed. A bounded one-request-per-second pass visited all 25 official provider pages, found **57** labelled SEND reports and yielded **40** novel direct-PDF candidates after reconciliation with the reviewed ten, the maintained manifest and the durable archive. No mapped provider page lacked a matching SEND report. The 40 review candidates cover 20 newly mapped authorities: 24 local-area SEND inspections, 14 area SEND full inspections and two monitoring inspections.

After reviewing those candidates, a five-authority subset (Barking and Dagenham, Barnet, Barnsley, Bath and North East Somerset, and Bedford) was dry-run and acquired at one request per second. Result: **downloaded 5, resumed/skipped 0, duplicate 0, blocked 0, failed 0**. The second integrity check found **34 objects, 34 valid, 0 failed and 0 orphaned source references**. The durable archive now covers 21 of 153 authorities; the combined review manifest has 71 direct-document candidates covering 35 authorities. These are acquisition and discovery coverage figures only, not claims about the absence of reports in the remaining authorities.

Five source-context spot checks distinguish provider-page publication dates from document inspection dates: Barking and Dagenham was inspected 27–31 March 2017 and published 29 June 2017; Barnet 17–21 January 2022 and 24 March 2022; Barnsley 2–6 February 2026 and 18 May 2026; Bath and North East Somerset 15–19 June 2026 and 2 September 2026; Bedford 18–22 November 2024 and 4 February 2025. The raw Ofsted labels and provider-page publication dates are retained as provenance; the downloaded PDFs were used only to spot-check date context. Do not promote either field to CDI evidence without document-level human review.

To continue the expanded provider batch, use the verified mapping seed, then review the generated CSV before importing it. Keep the discovery-run root outside Git; the command writes a `runs/` subdirectory below it:

```bash
python3 scripts/send_collect.py discover-ofsted \
  --input intake/seeds/ofsted_provider_archives_verified_2026-10-22.csv \
  --manifest intake/run-output/discovered-ofsted-manifest.json \
  --archive-root /durable/external/send-archive \
  --output intake/run-output/ofsted-provider-expansion-review.csv \
  --run-root /durable/external/ofsted-discovery \
  --execute --accept-terms reports.ofsted.gov.uk --limit 25 --rate-limit 1
```

Import that reviewed CSV, run `discover-pdfs`, then dry-run a small explicit `--source-key` subset. Only after rechecking `files.ofsted.gov.uk` terms and robots should the same keys be run with `--execute --accept-terms files.ofsted.gov.uk --rate-limit 1`. Record the run manifest and integrity result before increasing either the authority or document limit.

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

## Earlier pilot record: 22 October 2026

The reviewed batch has 21 direct PDF candidates: 17 Ofsted/CQC area SEND reports (including the CDI-held Essex report) and four DfE research/evaluation PDFs. It covers 17 of the directory's 153 authorities at the candidate stage.

The dry-run selected eight records: seven were ready for retrieval and the CDI-held Essex report was skipped. Earlier run notes reported 13 stored Ofsted/CQC PDFs (with two resumed/skipped) and 16 externally held Ofsted/CQC PDFs across 16 authorities, plus three pre-existing GOV.UK HTML originals. Those historical holdings must be re-verified against the actual durable archive before they are used as a current count.

The four DfE PDF URLs on `assets.publishing.service.gov.uk` were deliberately blocked in the initial pilot because the host returned HTTP 404 for `robots.txt`; no workaround was attempted. The collector now implements the narrow RFC 9309 treatment for that result: only `404` and `410` mean no robots rules were found, after the existing host, terms and request-safety controls pass. `401`, `403`, `429`, other 4xx responses, 5xx responses, timeouts and unsafe redirects remain blocked.

The five-page Ofsted provider-archive discovery pilot visited all five verified pages, found 15 labelled SEND PDF links and produced 10 novel URLs after reconciliation with the maintained official-PDF manifest. It downloaded no new report bytes.
