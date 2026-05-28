# Releasing

This package is published to PyPI as `agents-schema`.

Publishing should happen through PyPI Trusted Publishing from GitHub Actions.
Configure a pending publisher in PyPI before the first release:

```text
PyPI Project Name: agents-schema
Owner: fivetran
Repository name: agents_schema
Workflow name: publish-pypi.yml
Environment name: pypi
```

The publisher expects `.github/workflows/publish-pypi.yml` to publish on the
GitHub `release: published` event.

## Release Checklist

1. Update the version in `pyproject.toml` and `uv.lock`.
2. Run tests:

   ```bash
   uv run python -m unittest discover -s tests
   ```

3. Build and check distributions:

   ```bash
   rm -rf dist
   uv build
   uvx twine check dist/*
   ```

4. Commit the release changes.
5. Tag the release:

   ```bash
   git tag v0.0.5
   git push origin main --tags
   ```

6. In GitHub, create and publish a Release for the tag.

Publishing the GitHub Release triggers `.github/workflows/publish-pypi.yml`,
which publishes to PyPI using Trusted Publishing.

PyPI versions are immutable. If a release is wrong, publish a new version.
