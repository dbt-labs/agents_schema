CREATE OR REPLACE VIEW AGENTS.NOTES_ON_SCHEMATA_CONTEXT AS
SELECT
  schema_name,
  COUNT(*) AS notes_on_count,
  MAX(importance) AS notes_on_highest_importance,
  ARRAY_AGG(
    OBJECT_CONSTRUCT_KEEP_NULL(
      'note_id', note_id,
      'kind', kind,
      'tags', tags,
      'title', title,
      'content', content,
      'author', author,
      'source', source,
      'confidence', confidence,
      'importance', importance,
      'created_at', created_at,
      'updated_at', updated_at
    )
  ) AS notes_on_notes
FROM AGENTS.NOTES_ON_SCHEMATA
GROUP BY schema_name;

CREATE OR REPLACE VIEW AGENTS.NOTES_ON_TABLES_CONTEXT AS
SELECT
  table_catalog,
  table_schema,
  table_name,
  COUNT(*) AS notes_on_count,
  MAX(importance) AS notes_on_highest_importance,
  ARRAY_AGG(
    OBJECT_CONSTRUCT_KEEP_NULL(
      'note_id', note_id,
      'kind', kind,
      'tags', tags,
      'title', title,
      'content', content,
      'author', author,
      'source', source,
      'confidence', confidence,
      'importance', importance,
      'created_at', created_at,
      'updated_at', updated_at
    )
  ) AS notes_on_notes
FROM AGENTS.NOTES_ON_TABLES
GROUP BY table_catalog, table_schema, table_name;

CREATE OR REPLACE VIEW AGENTS.NOTES_ON_COLUMNS_CONTEXT AS
SELECT
  table_catalog,
  table_schema,
  table_name,
  column_name,
  COUNT(*) AS notes_on_count,
  MAX(importance) AS notes_on_highest_importance,
  ARRAY_AGG(
    OBJECT_CONSTRUCT_KEEP_NULL(
      'note_id', note_id,
      'kind', kind,
      'tags', tags,
      'title', title,
      'content', content,
      'author', author,
      'source', source,
      'confidence', confidence,
      'importance', importance,
      'created_at', created_at,
      'updated_at', updated_at
    )
  ) AS notes_on_notes
FROM AGENTS.NOTES_ON_COLUMNS
GROUP BY table_catalog, table_schema, table_name, column_name;
