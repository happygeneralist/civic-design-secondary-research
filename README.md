# Civic design secondary research

This repository stores public secondary research sources used by the Civic Design Intelligence repository.

It is a source archive, not the structured intelligence repository.

Raw or lightly processed public sources live here. Structured evidence, user needs, civic needs, pain points, behaviours, insights, themes and pattern sensemaking live in [`civic-design-intelligence`](https://github.com/happygeneralist/civic-design-intelligence).

## Core principle

```text
Public secondary source archive
→ source record
→ evidence extracts
→ candidate needs, pain points, behaviours, civic needs and insights
→ cross-source patterns
```

This repository preserves source provenance. It should not become the place where research interpretation is reviewed, validated or maintained.

## Local sources and reusable objects

A local source can provide evidence for a reusable need, pain point, behaviour, civic need or insight in the structured intelligence repository.

For example, a local SEND inspection report may show that a general SEND pathway need is not being met in one area. That does not make the underlying need local-only, and it does not prove national prevalence or severity.

Use this repository to preserve the local source context:

- which source was used;
- which part of the source was selected;
- what locality, publisher and publication context apply;
- which structured evidence or analysis objects the source later supports.

Use `civic-design-intelligence` for the interpretation work: deciding whether a candidate object is general, umbrella-level, localised, comparative, evidence-only or still immature.

## What belongs here

Use this repository for:

- public reports
- inspection reports
- local authority strategies
- national policy documents
- charity and third sector reports
- public research papers or summaries
- source inventories
- download metadata
- publisher metadata
- checksums, where useful
- raw or lightly processed public source files that should not live in the structured intelligence repository

## What does not belong here

Do not use this repository for:

- canonical evidence objects
- user needs
- civic needs
- pain points
- behaviours
- insights
- themes
- review or validation decisions
- private, sensitive or non-public research material
- personal data or identifiable case material

Those belong in the design intelligence repository only when they have been safely structured and appropriately anonymised.

## Repository relationship

This repository holds source material and source-level documentation.

The design intelligence repository holds source records, evidence extracts and derived knowledge objects.

A source used in structured analysis should normally have:

1. a folder in this repository
2. a `source.md` file in that folder
3. an `evidence-map.md` file linking to structured objects, once ingestion has started
4. a matching source or research-study record in the design intelligence repository

## Minimum source workflow

1. Add a source folder using the next `SRC_000` identifier.
2. Complete `source.md` with source metadata.
3. Add the public URL and archive reference.
4. Add the raw public file only if lawful, useful and appropriate.
5. Add candidate extracts to `extracts.md` only where helpful.
6. Create a matching source record in `civic-design-intelligence` before creating evidence objects.
7. Create selected evidence extracts in `civic-design-intelligence`.
8. Update `evidence-map.md` with the linked evidence and analysis object IDs.

## Important guardrails

- Do not ingest entire reports exhaustively by default.
- Do not treat report findings as validated user needs.
- Do not copy large public corpora into this repository before testing the workflow.
- Do not treat a local source as proof of national prevalence or severity.
- Do not create local-only interpretations here when the source may support reusable objects in `civic-design-intelligence`.
- Do not store sensitive or private material here.
- Preserve source provenance, publication details and retrieval dates.
- Keep interpretation in the structured intelligence repository.

## Folder pattern

Use this pattern for sources:

```text
sources/
  SRC_001_short_source_slug/
    source.md
    extracts.md
    evidence-map.md
    original/
      README.md
```

The `original/` folder is optional. Use it only for public files that should be archived in Git.

## Related repository

- [`civic-design-intelligence`](https://github.com/happygeneralist/civic-design-intelligence)
