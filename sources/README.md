# Sources

This folder contains public secondary research sources used by the Civic Design Intelligence work.

Each source should have its own folder with a stable `SRC_000` identifier and a readable slug.

## Folder naming

Use:

```text
SRC_001_short_source_slug
```

Examples:

```text
SRC_001_ofsted_local_area_send_report
SRC_002_send_green_paper
SRC_003_charity_report_parent_experience
```

Use plain ASCII, lower case and underscores for the slug.

## Minimum files

Each source folder should normally contain:

```text
source.md
extracts.md
evidence-map.md
```

Optional:

```text
original/
  README.md
```

Use `original/` only where storing the public file in Git is lawful, useful and proportionate.

## Source lifecycle

Suggested source-level statuses:

```text
not_started
candidate
partial
ingested
superseded
out_of_scope
```

Do not use these statuses to imply that evidence or analysis objects have been reviewed or validated.

## Relationship to civic-design-intelligence

A source folder can exist here before it is used.

Once it is used to create evidence, the design intelligence repository should contain:

- a matching source or research-study record
- selected evidence extracts
- linked analysis objects, where appropriate

Update `evidence-map.md` in this repository after structured evidence or analysis objects are created.
