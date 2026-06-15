# Notes On Provider Spec

`notes_on` is an optional provider for teams that want a durable note layer on
warehouse schemas, tables, and columns. It is not part of the core Agents Schema
spec and does not require other providers or consumers to adopt this shape.

## Provider Rows

```text
provider  key       content
notes_on  overview  Portable, object-scoped annotations for warehouse schemas, tables, and columns.
notes_on  schemata  One row per note attached to a warehouse schema. See AGENTS.NOTES_ON_SCHEMATA.
notes_on  tables    One row per note attached to a warehouse table. See AGENTS.NOTES_ON_TABLES.
notes_on  columns   One row per note attached to a warehouse column. See AGENTS.NOTES_ON_COLUMNS.
```

## Tables

```sql
CREATE OR REPLACE TABLE AGENTS.NOTES_ON_SCHEMATA (
  note_id     VARCHAR NOT NULL,
  schema_name VARCHAR NOT NULL,
  kind        VARCHAR NOT NULL,
  tags        VARIANT,
  title       VARCHAR,
  content     TEXT NOT NULL,
  author      VARCHAR,
  source      VARCHAR,
  confidence  FLOAT,
  importance  FLOAT,
  created_at  TIMESTAMP,
  updated_at  TIMESTAMP,
  PRIMARY KEY (note_id)
);

CREATE OR REPLACE TABLE AGENTS.NOTES_ON_TABLES (
  note_id       VARCHAR NOT NULL,
  table_catalog VARCHAR,
  table_schema  VARCHAR NOT NULL,
  table_name    VARCHAR NOT NULL,
  kind          VARCHAR NOT NULL,
  tags          VARIANT,
  title         VARCHAR,
  content       TEXT NOT NULL,
  author        VARCHAR,
  source        VARCHAR,
  confidence    FLOAT,
  importance    FLOAT,
  created_at    TIMESTAMP,
  updated_at    TIMESTAMP,
  PRIMARY KEY (note_id)
);

CREATE OR REPLACE TABLE AGENTS.NOTES_ON_COLUMNS (
  note_id       VARCHAR NOT NULL,
  table_catalog VARCHAR,
  table_schema  VARCHAR NOT NULL,
  table_name    VARCHAR NOT NULL,
  column_name   VARCHAR NOT NULL,
  kind          VARCHAR NOT NULL,
  tags          VARIANT,
  title         VARCHAR,
  content       TEXT NOT NULL,
  author        VARCHAR,
  source        VARCHAR,
  confidence    FLOAT,
  importance    FLOAT,
  created_at    TIMESTAMP,
  updated_at    TIMESTAMP,
  PRIMARY KEY (note_id)
);
```

## Required Fields

Every note requires `note_id`, `kind`, and `content`.

Schema notes also require `schema_name`. Table notes require `table_schema` and
`table_name`. Column notes require `table_schema`, `table_name`, and
`column_name`.

`table_catalog` is optional because many local metadata systems identify tables
within one active database. Providers that can populate it should do so.

## Kind

`kind` is a required string that lets consumers filter broad categories without
parsing note text. Examples include `unit_rule`, `grain_warning`, `time_policy`,
`join_warning`, `pii`, and `business_definition`.

## Scores

`confidence` is an optional trust score in `[0, 1]`.

`importance` is an optional retrieval salience score in `[0, 1]`.

## Tags

`tags` is an optional array of strings. It is intended for loose facets such as
`finance`, `pii`, `unit`, or `agent_generated`, not a required taxonomy.

## Context Aggregation

These tables are one row per note. Context views that expose one row per schema,
table, or column should aggregate notes into an array rather than concatenate
text. The example implementation publishes `notes_on_notes` as an array of note
objects alongside `notes_on_count` and `notes_on_highest_importance`.
