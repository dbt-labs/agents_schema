---
name: agents-schema-analyst
description: Use when answering a business data question (revenue, net revenue, MRR, ARR, churn, customer or connector counts, etc.) against a Snowflake warehouse that has an AGENTS metadata schema. Triggers on questions like "what is our current MRR", "net revenue year-to-date", "how many active customers", or any ask for a governed metric instead of a guessed one.
allowed-tools: "Bash(snow:*), Read"
user-invocable: true
argument-hint: "[business question]"
---

# Agents Schema Analyst

## Overview

Answer the question by first reading the governed definitions in the warehouse's `AGENTS`
metadata schema, then querying the business tables exactly as those definitions specify.

**Core principle: the warehouse tells you how to compute the answer. Your job is to find
that instruction in `AGENTS.*` and follow it — not to guess a formula, table, filter, or date rule.**

This skill is warehouse-agnostic in spirit but Snowflake-specific in tooling: it queries
through the Snowflake CLI (`snow`). It works against any `AGENTS` schema, for this demo or a
customer's own warehouse, because it discovers everything at query time.

## Setup

- Query Snowflake **read-only** with: `snow sql -c <connection> -q "<SQL>"`.
- **Connection:** read `snow_cli_connection` from an `agents.yml` in the working directory if
  present. Otherwise run `snow connection list` and use the default (or the only) connection;
  if it is ambiguous, ask the user which connection to use.
- **Metadata schema:** use `agents_schema_name` from `agents.yml` uppercased, else `AGENTS`.
- Only `SELECT` / `SHOW`. Never write, create, or drop.

## Procedure

1. **Discover what metadata exists — don't assume which providers are present.**
   ```sql
   SELECT provider, key, description FROM AGENTS.ROOT ORDER BY provider, key;
   ```
   This lists the providers that published metadata (`osi`, `lookml`, `dbt`, or custom) plus
   their overview/guidance rows. Only query tables for providers that actually appear here.

2. **Find the metric.** Search the semantic definition tables for keywords from the question
   and read `DESCRIPTION`, `AI_CONTEXT`, and the formula (`EXPRESSION` for OSI, `SQL` for LookML):
   ```sql
   SELECT name, description, ai_context, expression
   FROM AGENTS.OSI_METRIC
   WHERE LOWER(NAME||' '||COALESCE(DESCRIPTION,'')||' '||COALESCE(AI_CONTEXT,''))
         LIKE '%revenue%';
   ```
   Use `AGENTS.LOOKML_MEASURE` (`SQL`, `DESCRIPTION`, `AI_CONTEXT`) when the provider is LookML.

3. **Resolve the physical table and its rules.** Find the source table and every query caveat
   in the dataset/view metadata, and obey each `AI_CONTEXT` instruction exactly:
   - OSI: `AGENTS.OSI_DATASET` (`SOURCE_TABLE`, `AI_CONTEXT`), `AGENTS.OSI_FIELD`
   - LookML: `AGENTS.LOOKML_VIEW` (`SQL_TABLE_NAME`), `AGENTS.LOOKML_DIMENSION`
   - dbt, *only if present in ROOT*: `AGENTS.DBT_MODEL` / `AGENTS.DBT_COLUMN` add model and
     column descriptions.
   Use the source table named in the metadata — not a same-named table you assume exists elsewhere.

4. **Translate the formula to SQL.** OSI `EXPRESSION` is usually plain SQL (e.g. `SUM(net_revenue)`)
   — use it as-is against the resolved table. For LookML `SQL`: `${TABLE}.col` → `col`;
   `${other_field}` → look that field up and substitute recursively; `{% if %}…{% else %} X {% endif %}`
   → use the `{% else %}` branch.

5. **Pick the time grain from metadata.** Use the time dimension the metadata marks
   (`OSI_FIELD.IS_TIME_DIMENSION`, or a LookML `dimension_group`). For "current"/snapshot
   metrics, use the latest available period. For "year-to-date", try wall-clock current year
   first; **if it returns no rows because the data is historical, do NOT report $0** — anchor to
   the latest year present in the table and clearly label the date range you used.

6. **Run it and answer.** Run the grounded query with `snow sql`, show the SQL you ran, and state
   the answer plainly (round currency to whole dollars with a `$`; percentages to one decimal).

## Hard rules — never hard-code

- Discover every metric formula, source table, filter, and date column from `AGENTS.*`. Do not
  bake business facts into this skill, the prompt, or your reasoning.
- Follow `AI_CONTEXT` / `DESCRIPTION` exactly. If it says "use net_revenue, not gross_revenue,"
  do that.
- Do not run `SHOW TABLES`, `GET_DDL`, or broad schema crawls. The metadata rows tell you where
  to look — use focused `SELECT`s derived from the question.
- If a definition is missing or ambiguous, say so. Do not substitute a guess.

## Metadata table shapes (reference)

Identifiers are UPPERCASE in Snowflake. A given warehouse has only the families its ROOT lists.

| Table | Key columns |
|---|---|
| `AGENTS.ROOT` | `PROVIDER`, `KEY`, `DESCRIPTION` |
| `AGENTS.OSI_METRIC` | `NAME`, `DESCRIPTION`, `AI_CONTEXT`, `EXPRESSION` |
| `AGENTS.OSI_DATASET` | `NAME`, `SOURCE_TABLE`, `PRIMARY_KEY`, `DESCRIPTION`, `AI_CONTEXT` |
| `AGENTS.OSI_FIELD` | `DATASET_NAME`, `FIELD_NAME`, `DESCRIPTION`, `AI_CONTEXT`, `IS_TIME_DIMENSION`, `EXPRESSION` |
| `AGENTS.LOOKML_MEASURE` | `VIEW_NAME`, `MEASURE_NAME`, `TYPE`, `SQL`, `DESCRIPTION`, `AI_CONTEXT` |
| `AGENTS.LOOKML_VIEW` | `NAME`, `SQL_TABLE_NAME`, `DESCRIPTION`, `AI_CONTEXT` |
| `AGENTS.LOOKML_DIMENSION` | `VIEW_NAME`, `FIELD_NAME`, `FIELD_KIND`, `TYPE`, `SQL`, `DESCRIPTION`, `AI_CONTEXT` |
| `AGENTS.DBT_MODEL` | `UNIQUE_ID`, `NAME`, `SCHEMA_NAME`, `DESCRIPTION` |
| `AGENTS.DBT_COLUMN` | `MODEL_ID`, `COLUMN_NAME`, `DATA_TYPE`, `DESCRIPTION` |

## Common mistakes

| Mistake | Do instead |
|---|---|
| Using `gross_revenue` (or any plausible-looking column) for "revenue" | Read the metric's `AI_CONTEXT`; use the column it names (often `net_revenue`). |
| Reporting `$0` / no result for "year-to-date" | If current-year returns no rows, the data is historical — anchor to the latest year present and label it. |
| Querying a metric from the wrong table | The dataset/view metadata names the `SOURCE_TABLE` and any "use X not Y" caveat. Follow it. |
| Assuming `DBT_*` (or any provider) tables exist | Check `AGENTS.ROOT` first; some warehouses have only OSI or only LookML. |
| `SHOW TABLES` / `GET_DDL` to explore | Use focused `SELECT`s against the known `AGENTS.*` tables. |

## Worked example

**Question:** "What is our current total MRR broken down by plan tier, and what is our net
revenue from orders year-to-date?"

1. `AGENTS.ROOT` → providers present: `osi`, `lookml` (no `dbt`).
2. `AGENTS.OSI_METRIC` → `total_net_revenue` = `SUM(net_revenue)`, ai_context: *"Always use
   net_revenue (not gross_revenue) for P&L."* `total_mrr` = `SUM(mrr)`, ai_context: *"Use
   mtr_mrr … fct_subscriptions has no mrr column."*
3. `AGENTS.OSI_DATASET` → `orders` → `snowflake_summit26_demo.fct_orders`; `mrr_snapshots` →
   `snowflake_summit26_demo.mtr_mrr`.
4. MRR by plan, latest month:
   ```sql
   SELECT plan, SUM(mrr) AS mrr
   FROM snowflake_summit26_demo.mtr_mrr
   WHERE month = (SELECT MAX(month) FROM snowflake_summit26_demo.mtr_mrr)
   GROUP BY plan ORDER BY mrr DESC;
   ```
   → enterprise **$2,495**, pro **$1,639**, starter **$147** (total **$4,281**).
5. Net revenue YTD: wall-clock current year returns no rows (orders end 2024-12), so anchor to
   the latest year present and say so:
   ```sql
   SELECT SUM(net_revenue) AS net_ytd
   FROM snowflake_summit26_demo.fct_orders
   WHERE created_at >= DATE_TRUNC('year',
         (SELECT MAX(created_at) FROM snowflake_summit26_demo.fct_orders));
   ```
   → **$14,533** for 2024 (gross would have been $14,832 — the $299 gap is refunds, which is
   exactly why the metric says net).
