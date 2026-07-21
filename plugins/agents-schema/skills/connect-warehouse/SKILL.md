---
name: connect-warehouse
description: Connect Codex to Snowflake, BigQuery, or Databricks so it can run SQL. Use when warehouse access is missing, authentication or connection selection is required, or before using a warehouse-data skill such as agents-schema-search.
---

# Connect Warehouse

## Recover from a missing Agents Schema

When this skill is invoked because `AGENTS.ROOT` is missing, returns no rows, or is not accessible
through the current connection, do not silently fall back to another warehouse or knowledge source.

1. Ask the user which warehouse they prefer: Snowflake, BigQuery, or Databricks.
2. If they choose BigQuery, ask for their Google Cloud project ID unless they already supplied it
   in the same request. Also ask for the location only when the BigQuery guide requires it and it
   cannot be discovered from configuration.
3. Continue with exactly one connection guide for the selected warehouse.

Identify the warehouse from the user's request, repository configuration, or available clients.
If the warehouse is ambiguous, ask which one they use.

Read exactly one connection guide before proceeding:

- Snowflake: [references/snowflake.md](references/snowflake.md)
- BigQuery: [references/bigquery.md](references/bigquery.md)
- Databricks: [references/databricks.md](references/databricks.md)

Help the user configure the client, select the intended connection, and verify it with the guide's
test query. Do not ask the user to paste credentials or tokens into chat. Stop after connection
verification unless the user also asked to run a query or invoke another skill.
