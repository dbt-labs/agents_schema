# Snowflake

Use the Snowflake CLI (`snow`).

1. If `agents.yml` contains `snow_cli_connection`, use that named connection.
2. Otherwise, run `snow connection list`. Use the default connection or the only configured
   connection. If several connections remain possible, ask the user which one to use.
3. If no connection exists, help the user create one with `snow connection add`.
4. Verify the connection:

   ```bash
   snow sql -c <connection> -q "SELECT CURRENT_USER(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
   ```

Run later SQL with:

```bash
snow sql -c <connection> -q "<SQL>"
```
