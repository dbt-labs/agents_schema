# Contributing

Thanks for your interest in improving Agents Schema.

## Development

Install dependencies and run tests with `uv`:

```bash
uv sync
uv run pytest
```

## Pull Requests

Before opening a pull request, please:

- Keep changes focused on one behavior or documentation update.
- Add or update tests for code changes.
- Avoid committing real credentials, warehouse endpoints, customer names, or
  production metadata exports.
- Run `uv run pytest` locally when possible.
