# Example Providers

This directory contains optional provider examples for Agents Schema.

Example providers are not part of the core Agents Schema contract. They show how
a team can use the extension model:

- choose a provider name
- isolate provider-owned tables with that prefix
- optionally publish provider-authored rows into `AGENTS.ROOT`
- keep implementation-specific opinions outside the core package

An example provider can later move to its own repository/package or be promoted
into the core project if the community agrees it should become a standard
provider.
