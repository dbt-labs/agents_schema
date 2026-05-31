# Memory Setup

## When to use memory

Memory is the lightweight path to anchored, agent-retrievable notes — query
rules, join caveats, unit conversions, status meanings, and grain warnings —
for deployments that **do not run a semantic layer**.

If you already maintain an OSI semantic model, prefer object-local `ai_context`
on the relevant dataset, field, or metric: it carries the same notes right on
the object and memory is largely redundant. Reach for memory when you have no
semantic layer, or for notes about raw warehouse objects that OSI does not
model. See [SPEC.md](./SPEC.md) for the full table contract.

## Prerequisites

The workflow needs destination warehouse credentials so it can create and
replace tables in the `AGENTS` schema.

Create one required GitHub Actions secret in the repository that calls these
workflows: `WAREHOUSE_CREDENTIALS`.

Snowflake is the only supported destination today, with more destination
support coming soon. We recommend key-pair authentication:

**Example key-pair auth secret:**

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
private_key_pem: |
  -----BEGIN ENCRYPTED PRIVATE KEY-----
  MIIEvQIBADANBgkqh...
  -----END ENCRYPTED PRIVATE KEY-----
private_key_passphrase: your-passphrase   # only if the key is encrypted
```

**Note:**
- `role` is optional.
- An unencrypted key uses `-----BEGIN PRIVATE KEY-----` / `-----END PRIVATE KEY-----` markers and omits `private_key_passphrase`.

## Author a memory file

The CLI reads a single YAML file. Each memory has an id, a kind, durable
`content`, and one or more anchors that attach it to the objects where it is
relevant.

```yaml
memories:
  - memory_id: stripe_amounts_are_cents
    memory_kind: unit_rule
    title: Stripe amounts
    content: Stripe amount columns are stored in cents; divide by 100 for dollar measures.
    source: memories.yaml
    confidence: 0.9        # optional, 0..1
    anchors:
      - anchor_id: invoice_amount_due
        anchor_type: column
        schema_name: stripe
        table_name: invoice
        column_name: amount_due

  - memory_id: ticket_assignee_join
    memory_kind: join_rule
    content: For ticket owner reporting, join ticket.assignee_id to user.id.
    anchors:
      - anchor_id: ticket_to_user
        anchor_type: relationship
        relationship_name: ticket_to_user   # optional label
        from_schema: zendesk
        from_table: ticket
        from_columns: [assignee_id]
        to_schema: zendesk
        to_table: user
        to_columns: [id]
```

Anchor types and the locator columns each one uses:

| `anchor_type` | Required locators | Optional |
|---|---|---|
| `column` | `table_name`, `column_name` | `schema_name` |
| `table` | `table_name` | `schema_name` |
| `metric` | `metric_id` | |
| `relationship` | `from_table`, `to_table` | `from_schema`, `to_schema`, `from_columns`/`to_columns` (paired, equal length), `relationship_name` |

Validation fails fast on unknown fields, wrong scalar types, a `confidence`
outside `0..1`, duplicate memory ids, duplicate anchors, unsupported anchor
types, locators that do not belong to the anchor type, and missing required
locators.

## Run the Memory Sync Workflow

```yaml
name: Agents Schema Memory

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-memory:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-memory.yml@v0.0.6
    with:
      memory-file: memory.yml
    secrets: inherit
```

`memory-file` is required — set it to the path of your memory YAML file. The
example uses `memory.yml`; change it to match your repository.

The workflow writes:

- `AGENTS.MEMORY`
- `AGENTS.MEMORY_ANCHOR`

These jobs do not need to depend on dbt, Looker, or OSI jobs unless your
repository has its own ordering requirement.
