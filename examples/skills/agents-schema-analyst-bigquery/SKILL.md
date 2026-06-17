---
name: agents-schema-analyst-bigquery
description: Use when answering a business data question (revenue, MRR, ARR, churn, customer or connector counts, etc.) against a BigQuery warehouse that has an AGENTS metadata schema. Triggers on questions like "what is our current MRR", "net revenue year-to-date", "how many active customers", or any ask for a governed metric instead of a guessed one.
allowed-tools: "Bash(bq:*), Read"
user-invocable: true
argument-hint: "[business question]"
---

# Agents Schema Analyst (BigQuery)

## Overview

Answer the question by first reading the governed definitions in the warehouse's `agents`
metadata dataset, then querying the business tables exactly as those definitions specify.

**Core principle: the warehouse tells you how to compute the answer. Your job is to find
that instruction in the agents dataset and follow it — not to guess a formula, table, filter, or date rule.**

## Setup

- Read `project_id` and optional `location` from `agents.yml` in the working directory.
- **Metadata dataset:** `` `<project_id>.agents` `` where `project_id` is the value from
  `agents.yml`. For example, if `project_id` is `my-project`, tables are referenced as
  `` `my-project.agents`.root ``, `` `my-project.agents`.osi_metric ``, etc.
  Substitute your actual project ID throughout all queries below.
- Execute SQL by replacing `<project_id>`, `<location>`, and `<SQL>` below and running:
  ```bash
  bq query \
    --project_id="<project_id>" \
    --location="<location>" \
    --use_legacy_sql=false \
    --format=json << 'SQLEOF'
<SQL>
SQLEOF
  ```
  Omit `--location` when `agents.yml` does not set one. Replace `<SQL>` with the actual query.
- Only `SELECT`. Never `INSERT`, `UPDATE`, `DELETE`, `CREATE`, or `DROP`.

## Procedure

1. **Discover what metadata exists — don't assume which providers are present.**
   ```sql
   SELECT provider, key, content FROM `<project_id>.agents`.root ORDER BY provider, key;
   ```
   This lists the providers that published metadata (`osi`, `lookml`, `dbt`, or user-published) plus
   their overview/guidance rows. Only query tables for providers that actually appear here.

2. **Find the metric.** Search the semantic definition tables for keywords from the question
   and read `description`, `ai_context`, and the formula (`expression` for OSI, `sql` for LookML).
   Substitute a keyword from the question for `<keyword>`:
   ```sql
   SELECT name, description, ai_context, expression
   FROM `<project_id>.agents`.osi_metric
   WHERE LOWER(CONCAT(COALESCE(name, ''), ' ', COALESCE(description, ''), ' ', COALESCE(ai_context, '')))
         LIKE '%<keyword>%';
   ```
   Use `` `<project_id>.agents`.lookml_measure `` (`sql`, `description`, `ai_context`) when the provider is LookML.
   **If no rows match, stop and tell the user** — do not proceed to Step 3 without a metric
   definition. Try a shorter or alternate keyword if the first search returns nothing.

3. **Resolve the physical table and its rules.** Find the source table and every query caveat
   in the dataset/view metadata, and obey each `ai_context` instruction exactly:
   - OSI: `` `<project_id>.agents`.osi_dataset `` (`source_table`, `ai_context`), `` `<project_id>.agents`.osi_field ``
   - LookML: `` `<project_id>.agents`.lookml_view `` (`sql_table_name`), `` `<project_id>.agents`.lookml_dimension ``
   - dbt, *only if present in root*: `` `<project_id>.agents`.dbt_model `` / `` `<project_id>.agents`.dbt_column ``
     add model and column descriptions.
   Use the source table named in the metadata — not a same-named table you assume exists elsewhere.

4. **Translate the formula to SQL.** OSI `expression` is usually plain SQL (e.g. `SUM(amount)`)
   — use it as-is against the resolved table. **Always alias aggregate expressions**
   (e.g. `SUM(amount) AS value`) so `bq query --format=json` returns a named key instead of the
   auto-generated `f0_`. For LookML `sql`: `${TABLE}.col` → `col`;
   `${other_field}` → look that field up and substitute recursively; `{% if %}…{% else %} X {% endif %}`
   → use the `{% else %}` branch.

5. **Pick the time grain from metadata.** Use the time dimension the metadata marks
   (`osi_field.is_time_dimension`, or a LookML `dimension_group`). For "current"/snapshot
   metrics, use the latest available period. For "year-to-date", try wall-clock current year
   first; **if it returns no rows because the data is historical, do NOT report $0** — anchor to
   the latest year present in the table and clearly label the date range you used.

6. **Run it and answer.** Run the grounded query with `bq query`, show the SQL you ran, and state
   the answer plainly (round currency to whole dollars with a `$`; percentages to one decimal).

## Hard rules — never hard-code

- Discover every metric formula, source table, filter, and date column from the agents dataset.
  Do not bake business facts into this skill, the prompt, or your reasoning.
- Follow `ai_context` / `description` exactly. If it says to use one column or table and not
  another, do exactly that.
- Do not run broad `INFORMATION_SCHEMA` scans or any other schema crawl. The metadata rows tell
  you where to look — use focused `SELECT`s derived from the question.
- If a definition is missing or ambiguous, say so. Do not substitute a guess.

## Metadata table shapes (reference)

Column names are stored lowercase. A given warehouse has only the families its `root` table lists.
Replace `<project_id>` with the actual project ID from `agents.yml` throughout.

| Table | Key columns |
|---|---|
| `` `<project_id>.agents`.root `` | `provider`, `key`, `content` |
| `` `<project_id>.agents`.osi_metric `` | `name`, `description`, `ai_context`, `expression` |
| `` `<project_id>.agents`.osi_dataset `` | `name`, `source_table`, `primary_key`, `description`, `ai_context` |
| `` `<project_id>.agents`.osi_field `` | `dataset_name`, `field_name`, `description`, `ai_context`, `is_time_dimension`, `expression` |
| `` `<project_id>.agents`.lookml_measure `` | `view_name`, `measure_name`, `type`, `sql`, `description`, `ai_context` |
| `` `<project_id>.agents`.lookml_view `` | `name`, `sql_table_name`, `description`, `ai_context` |
| `` `<project_id>.agents`.lookml_dimension `` | `view_name`, `field_name`, `field_kind`, `type`, `sql`, `description`, `ai_context` |
| `` `<project_id>.agents`.dbt_model `` | `unique_id`, `name`, `schema_name`, `description` |
| `` `<project_id>.agents`.dbt_column `` | `model_id`, `column_name`, `data_type`, `description` |

## Common mistakes

| Mistake | Do instead |
|---|---|
| Picking a plausible-looking column or table for a metric | Read the metric/dataset `ai_context` and use exactly the column, table, and filter it names. |
| Reporting `$0` / no result for "year-to-date" | If current-year returns no rows, the data is historical — anchor to the latest year present and label it. |
| Querying a metric from the wrong table | The dataset/view metadata names the `source_table` and any "use X not Y" caveat. Follow it. |
| Assuming a provider's tables exist | Check `` `<project_id>.agents`.root `` first; some warehouses have only OSI, only LookML, or only dbt. |
| Broad `INFORMATION_SCHEMA` scans to explore | Use focused `SELECT`s against the known `` `<project_id>.agents`.* `` tables. |
