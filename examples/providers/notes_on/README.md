# Notes On Provider

`notes_on` is an optional Agents Schema provider for durable notes attached to
warehouse schemas, tables, and columns. Teams can add it when this note layer is
useful for their agents, catalogs, review workflows, or analytics tooling.

It is not a core provider and does not require everyone adopting Agents Schema
to adopt this note shape. The package does not modify the core `agents-schema`
CLI, core `ROOT_ENTRIES`, or core `SPEC.md`; it publishes its own prefixed
tables and registers provider-authored metadata in `AGENTS.ROOT`.

## Tables

The provider writes:

- `AGENTS.NOTES_ON_SCHEMATA`
- `AGENTS.NOTES_ON_TABLES`
- `AGENTS.NOTES_ON_COLUMNS`

It also upserts provider-authored root rows:

- `(notes_on, overview)`
- `(notes_on, schemata)`
- `(notes_on, tables)`
- `(notes_on, columns)`

## Install And Run

From this directory:

```bash
uv run agents-schema-notes-on --notes-file notes.yml
```

The command reads Snowflake credentials from `WAREHOUSE_CREDENTIALS`, using the
same YAML/JSON shape as the core package.

The command replaces the three `AGENTS.NOTES_ON_*` tables and upserts the
provider's own `AGENTS.ROOT` rows. That root write is provider-owned metadata,
not a change to the core provider registry.

## Source File

See [notes.yml](notes.yml) for a complete example.

```yaml
column_notes:
  - note_id: stripe_invoice_amount_due_cents
    table_schema: stripe
    table_name: invoice
    column_name: amount_due
    kind: unit_rule
    tags: [stripe, money]
    content: Stripe amount columns are stored in cents; divide by 100 for dollar measures.
    author: analyst@example.com
    confidence: 0.9
    importance: 1.0
```

## Context Views

The source tables are one row per note, not one row per database object. A
generic `AGENTS.SCHEMATA`, `AGENTS.TABLES`, or `AGENTS.COLUMNS` enrichment
should aggregate them before joining. See
[sql/context_views.sql](sql/context_views.sql) for one possible aggregation
shape using a `VARIANT` array of note objects.

## Optional Fields

`kind` is required so consumers can filter broad categories such as
`unit_rule`, `grain_warning`, or `time_policy`.

`tags` is optional and deliberately loose. It is useful for lightweight facets
like `finance`, `pii`, or `agent_generated`, but this example does not require a
shared taxonomy.

`confidence` and `importance` are optional floats in `[0, 1]`. Use `confidence`
for trust in the note and `importance` for retrieval salience when prompt budget
is limited.
