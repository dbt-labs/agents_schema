# Databricks

Use the Databricks SQL Connector for Python.

1. Read `host`, `http_path`, `token`, and `catalog` from `agents.yml`. Ask the user to add any
   missing value without pasting secrets into chat.
2. Install `databricks-sql-connector` when `databricks.sql` is unavailable.
3. Verify the connection by replacing `<SQL>` with `SELECT 1`:

   ```bash
   python3 - <<'PYEOF'
   import databricks.sql
   import json
   import yaml

   cfg = yaml.safe_load(open("agents.yml"))
   with databricks.sql.connect(
       server_hostname=cfg["host"],
       http_path=cfg["http_path"],
       access_token=cfg["token"],
       catalog=cfg["catalog"],
   ) as connection:
       with connection.cursor() as cursor:
           cursor.execute("""
   <SQL>
           """)
           columns = [column[0] for column in cursor.description]
           rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
           print(json.dumps(rows, indent=2, default=str))
   PYEOF
   ```
