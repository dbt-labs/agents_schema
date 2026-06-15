CREATE SCHEMA IF NOT EXISTS AGENTS;

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
