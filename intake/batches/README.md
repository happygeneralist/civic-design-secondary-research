# Intake batches

`official_send_pdf_candidates_2026-10-22.csv` is the operational input for the automated PDF/data workflow. Import it with `import-urls`, review it with `discover-pdfs`, then dry-run and fetch an approval-reviewed subset.

`verified_send_documents_2026-10-22.csv` is retained as historical discovery/source metadata. It contains HTML decision and publication-page URLs and is not an automated acquisition input for this PDF-first pilot. Collect that material with Site Scraper and use `import-crawl-export`; do not convert it to PDF.
