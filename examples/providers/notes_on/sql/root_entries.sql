CREATE SCHEMA IF NOT EXISTS AGENTS;

CREATE TABLE IF NOT EXISTS AGENTS.ROOT (
  provider VARCHAR NOT NULL,
  key      VARCHAR NOT NULL,
  content  TEXT NOT NULL,
  PRIMARY KEY (provider, key)
);

MERGE INTO AGENTS.ROOT AS target
USING (
  SELECT 'notes_on' AS provider, 'overview' AS key,
         '# Notes On\nPortable, object-scoped annotations for warehouse schemas, tables, and columns.' AS content
  UNION ALL
  SELECT 'notes_on', 'schemata',
         'One row per note attached to a warehouse schema. See AGENTS.NOTES_ON_SCHEMATA.'
  UNION ALL
  SELECT 'notes_on', 'tables',
         'One row per note attached to a warehouse table. See AGENTS.NOTES_ON_TABLES.'
  UNION ALL
  SELECT 'notes_on', 'columns',
         'One row per note attached to a warehouse column. See AGENTS.NOTES_ON_COLUMNS.'
) AS source
ON target.provider = source.provider AND target.key = source.key
WHEN MATCHED THEN UPDATE SET target.content = source.content
WHEN NOT MATCHED THEN INSERT (provider, key, content)
VALUES (source.provider, source.key, source.content);
