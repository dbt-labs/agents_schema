---
name: agents-schema-analyst
description: Use when answering a business data question (revenue, MRR, ARR, churn, customer or connector counts, etc.) against a warehouse that has an AGENTS metadata schema. Triggers on questions like "what is our current MRR", "net revenue year-to-date", "how many active customers", or any ask for a governed metric instead of a guessed one. Supports Snowflake and Databricks.
allowed-tools: "Bash(snow:*), Bash(python3:*), Read"
user-invocable: true
argument-hint: "[business question]"
---

# Agents Schema Analyst

## Overview

Answer the question by first reading the governed definitions in the warehouse's `AGENTS`
metadata schema, then querying the business tables exactly as those definitions specify.

**Core principle: the warehouse tells you how to compute the answer. Your job is to find
that instruction in `AGENTS.*` and follow it — not to guess a formula, table, filter, or date rule.**

This skill is warehouse-agnostic in both approach and tooling. It detects the warehouse type
from `agents.yml` and routes SQL execution to the appropriate client (Snowflake CLI or Databricks
Python connector). It works against any `AGENTS` schema — your own warehouse or a customer's —
because it discovers the metrics, tables, and rules at query time rather than hard-coding them.

## Setup

**Step 1 — Read `agents.yml` and establish two macros used throughout this skill:**

**`{{AGENTS_PREFIX}}`** — the schema prefix for all metadata queries:

| Warehouse | Value | Example |
|---|---|---|
| Snowflake | `agents_schema_name` from `agents.yml` uppercased, else `AGENTS` | `AGENTS` |
| Databricks | `catalog` from `agents.yml` + `.agents` (or + `.` + `agents_schema_name` lowercased if set) | `main.agents` |

**`{{run_sql "<SQL>"}}`** — how to execute a query:

**Snowflake:** Read `snow_cli_connection` from `agents.yml` if present, else run `snow connection list` and use the default (ask the user if ambiguous):
```bash
snow sql -c <connection> -q "<SQL>"
```

**Databricks:** Read `host`, `http_path`, `token`, and `catalog` from `agents.yml`. Run:
```bash
python3 - <<'PYEOF'
import databricks.sql, json, yaml
cfg = yaml.safe_load(open("agents.yml"))
conn = databricks.sql.connect(
    server_hostname=cfg["host"],
    http_path=cfg["http_path"],
    access_token=cfg["token"],
    catalog=cfg.get("catalog", "hive_metastore"),
)
cursor = conn.cursor()
sql = """
SELECT ...  -- replace with actual SQL
"""
cursor.execute(sql)
cols = [d[0] for d in cursor.description]
rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
print(json.dumps(rows, indent=2, default=str))
conn.close()
PYEOF
```
Replace the `sql = """..."""` line with the actual SQL query before running.

**Step 2 — Read-only guard:** Only `SELECT`. Never `INSERT`, `UPDATE`, `DELETE`, `CREATE`, or `DROP`.

## Procedure

1. **Discover what metadata exists — don't assume which providers are present.**
   ```sql
   SELECT provider, key, content FROM {{AGENTS_PREFIX}}.ROOT ORDER BY provider, key;
   ```
   This lists the providers that published metadata (`osi`, `lookml`, `dbt`, or user-published) plus
   their overview/guidance rows. Only query tables for providers that actually appear here.

2. **Find the metric.** Search the semantic definition tables for keywords from the question
   and read `DESCRIPTION`, `AI_CONTEXT`, and the formula (`EXPRESSION` for OSI, `SQL` for LookML).
   Substitute a keyword from the question for `<keyword>`:
   ```sql
   SELECT name, description, ai_context, expression
   FROM {{AGENTS_PREFIX}}.OSI_METRIC
   WHERE LOWER(name||' '||COALESCE(description,'')||' '||COALESCE(ai_context,''))
         LIKE '%<keyword>%';
   ```
   Use `{{AGENTS_PREFIX}}.LOOKML_MEASURE` (`sql`, `description`, `ai_context`) when the provider is LookML.

3. **Resolve the physical table and its rules.** Find the source table and every query caveat
   in the dataset/view metadata, and obey each `AI_CONTEXT` instruction exactly:
   - OSI: `{{AGENTS_PREFIX}}.OSI_DATASET` (`source_table`, `ai_context`), `{{AGENTS_PREFIX}}.OSI_FIELD`
   - LookML: `{{AGENTS_PREFIX}}.LOOKML_VIEW` (`sql_table_name`), `{{AGENTS_PREFIX}}.LOOKML_DIMENSION`
   - dbt, *only if present in ROOT*: `{{AGENTS_PREFIX}}.DBT_MODEL` / `{{AGENTS_PREFIX}}.DBT_COLUMN` add model and
     column descriptions.
   Use the source table named in the metadata — not a same-named table you assume exists elsewhere.

4. **Translate the formula to SQL.** OSI `EXPRESSION` is usually plain SQL (e.g. `SUM(amount)`)
   — use it as-is against the resolved table. For LookML `SQL`: `${TABLE}.col` → `col`;
   `${other_field}` → look that field up and substitute recursively; `{% if %}…{% else %} X {% endif %}`
   → use the `{% else %}` branch.

5. **Pick the time grain from metadata.** Use the time dimension the metadata marks
   (`OSI_FIELD.IS_TIME_DIMENSION`, or a LookML `dimension_group`). For "current"/snapshot
   metrics, use the latest available period. For "year-to-date", try wall-clock current year
   first; **if it returns no rows because the data is historical, do NOT report $0** — anchor to
   the latest year present in the table and clearly label the date range you used.

6. **Run it and answer.** Run the grounded query with `{{run_sql}}`, show the SQL you ran, and state
   the answer plainly (round currency to whole dollars with a `$`; percentages to one decimal).

## Hard rules — never hard-code

- Discover every metric formula, source table, filter, and date column from `AGENTS.*`. Do not
  bake business facts into this skill, the prompt, or your reasoning.
- Follow `AI_CONTEXT` / `DESCRIPTION` exactly. If it says to use one column or table and not
  another, do exactly that.
- Do not run `SHOW TABLES`, `GET_DDL` (Snowflake), `SHOW TABLES IN`, `DESCRIBE TABLE` (Databricks),
  or any broad schema crawl. The metadata rows tell you where to look — use focused `SELECT`s
  derived from the question.
- If a definition is missing or ambiguous, say so. Do not substitute a guess.

## Metadata table shapes (reference)

Column names are stored **lowercase** in Databricks and case-insensitively in Snowflake.
Use lowercase column names in SELECT — they resolve on both warehouses.
A given warehouse has only the families its ROOT lists.

| Table | Key columns (lowercase — work on both warehouses) |
|---|---|
| `{{AGENTS_PREFIX}}.root` | `provider`, `key`, `content` |
| `{{AGENTS_PREFIX}}.osi_metric` | `name`, `description`, `ai_context`, `expression` |
| `{{AGENTS_PREFIX}}.osi_dataset` | `name`, `source_table`, `primary_key`, `description`, `ai_context` |
| `{{AGENTS_PREFIX}}.osi_field` | `dataset_name`, `field_name`, `description`, `ai_context`, `is_time_dimension`, `expression` |
| `{{AGENTS_PREFIX}}.lookml_measure` | `view_name`, `measure_name`, `type`, `sql`, `description`, `ai_context` |
| `{{AGENTS_PREFIX}}.lookml_view` | `name`, `sql_table_name`, `description`, `ai_context` |
| `{{AGENTS_PREFIX}}.lookml_dimension` | `view_name`, `field_name`, `field_kind`, `type`, `sql`, `description`, `ai_context` |
| `{{AGENTS_PREFIX}}.dbt_model` | `unique_id`, `name`, `schema_name`, `description` |
| `{{AGENTS_PREFIX}}.dbt_column` | `model_id`, `column_name`, `data_type`, `description` |

## Common mistakes

| Mistake | Do instead |
|---|---|
| Picking a plausible-looking column or table for a metric | Read the metric/dataset `AI_CONTEXT` and use exactly the column, table, and filter it names. |
| Reporting `$0` / no result for "year-to-date" | If current-year returns no rows, the data is historical — anchor to the latest year present and label it. |
| Querying a metric from the wrong table | The dataset/view metadata names the `source_table` and any "use X not Y" caveat. Follow it. |
| Assuming a provider's tables exist | Check `{{AGENTS_PREFIX}}.root` first; some warehouses have only OSI, only LookML, or only dbt. |
| `SHOW TABLES` / `GET_DDL` (Snowflake) or `SHOW TABLES IN` / `DESCRIBE TABLE` (Databricks) to explore | Use focused `SELECT`s against the known `{{AGENTS_PREFIX}}.*` tables. |
