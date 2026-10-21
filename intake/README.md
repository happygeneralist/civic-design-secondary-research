# SEND rapid collection pilot — Codex hand-off

**Status:** Implementation inputs and work brief, not a completed collector. Work item: [secondary research #3](https://github.com/happygeneralist/civic-design-secondary-research/issues/3). Branch: `codex/send-rapid-collection-pilot`.

## Scope and timebox

Make a **working collection pilot** within the next few days. This is a source archive and download pipeline, **not** the CDI evidence/object ingestion pipeline. Avoid building a crawler framework or database before there is a working importer, bounded fetcher and manifest. Keep changes small and reviewable.

## Supplied data

- `intake/seeds/SEND_all_153_local_authorities.csv` is the **unaltered supplied CSV**: 153 unique local authority rows with ONS codes and 3 constructed discovery/search links per authority. They are **not** 459 identified reports. Perplexity explicitly describes them as constructed, mostly unchecked entry points.
- `intake/seeds/direct_sources.csv` is a short, manually transcribed **candidate seed list** from the accompanying Perplexity PDF. The PDF calls some Essex links verified, but this repository has **not** independently fetched them. Separate `source_verification` from `retrieval_status`. The list includes document pages, search/index pages and one existing PDF (`SRC_001`).
- The user also uploaded an HTML version of the 153-authority directory, duplicating the CSV. No need to import it as 153 extra records.
- PDFs and websites may have different usage/republication rights. Raw archived content must not automatically be committed to public Git.

## Exact first task for Codex

Read #3, this document, root `README.md`, `templates/`, existing `SRC_001`, and CDI `docs/Source_capture_workflow.md`, `docs/Non_linear_research_ingestion.md`, and `docs/Roadmap_cursor.md`. Check branch and working tree. **Implement**, don't merely draft a plan.

Create a small Python 3 standard-library-first `scripts/send_collect.py` CLI (or explain dependency choice) and offline tests under `tests/`:

1. `catalogue`: load 153-authority seed and direct sources; produce a normalized **machine-readable manifest**, preserving provenance, local authority/ONS code, source class, verification and collection/retrieval state. Keep `discovery_url` distinct from `document_url`. Assert 153 and 459 in tests.
2. `fetch`: default **dry-run**; `--execute` explicitly opts in. By default retrieve only `direct_pdf` and `direct_html`, not search or category listings. Set timeouts, size cap, retries/backoff, per-host rate limits, user-agent identifying the research purpose, redirect verification, and structured errors. Check `robots.txt` and usage terms before running collection; no bypass or unauthorised access. Defend against file/private-network URLs and redirects (SSRF).
3. Store original bytes outside Git using a configurable `--archive-root`, SHA-256, URL and timestamp. Track canonical URL aliases, duplicate hashes and previously obtained source keys. No blind overwrites. Keep local run manifests in ignored directories, with an optional publishable metadata-only export (no copyrighted full text or personal data).
4. `import-crawl-export`: accept a **CSV export from an external site scraper** containing `url`, optional `title`, `captured_at`, `content_path`/text/HTML, and `collection_id`. Validate files/paths, preserve origin, store raw captures outside Git, log acquisition vs crawler-supplied metadata separately. Never assume search/index or whole crawls are validated reports.
5. `status`: counts by discovery / document candidate / successful / failed / skipped / duplicate / blocked, summarise host and authority coverage, print unresolved verification/reuse caveats.
6. Provide copy-and-paste commands for a first small Essex/national test, then capped batches covering more authorities using separately resolved **individual** report URLs. Generated per-authority search links should seed discovery only. An explicit separate `discover` command or adapter may extract bounded same-origin report links where legal and technically safe, but do not treat keyword search HTML as a report archive.
7. Fix the **small metadata inconsistency**: the existing `SRC_001` source folder contains the original PDF, although `source.md` and `original/README.md` say it is not stored. Make this a separate, obvious administrative commit or PR if practical, preserving research meaning.
8. Add `.gitignore` for run output and downloaded content. Include offline automated tests, sample scraper export, and a `docs/rapid-collection-runbook.md`. Document real verified results honestly. Do not claim a bulk run if network access is unavailable.

## Non-negotiable semantics

- No user needs, civic needs, pain points, insights or CDI evidence objects generated in this task.
- Do not mark sources as human reviewed or validated.
- Do not infer national prevalence from one local source.
- Keep original/source URL, fetched final URL, content checksum, retrieval date/time, archive path, publisher, collection provenance and relevant locality.
- Limit raw public Git commits; a local/non-Git archive is acceptable for the initial test.
- Keep source cataloguing fast; detailed `source.md`/cross-repo `evidence-map.md` records are needed only when the source is actively selected for CDI analysis.
- Never scrape sites that forbid it or circumvent rate limits, authentication or access controls.
- Don't publish detailed private research-orchestration prompts/rubrics from `design-intelligence-orchestration`.
- Use a **draft PR** with what changed, tests, known failures, first-run commands, source counts, and next immediate steps. Do not merge without approval.

## First-day success

At minimum, running the CLI from a fresh clone should register 153 local authorities, produce a separate direct URL queue, dry-run safely, fetch a bounded set of allowed real sources to a local archive, rerun without duplicating material, and generate a human-readable inventory/status summary. **Collection success is independent of semantic ingestion.**
