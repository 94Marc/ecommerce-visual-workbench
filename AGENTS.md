# AGENTS.md

## Project contract

`ecommerce-visual-workbench` is a cross-border e-commerce image production system. Phase 1 closes the workflow from product data and immutable source assets through rules, simulated generation, review, and ZIP export. It does not implement orders, inventory, purchasing, logistics, customer service, finance, advertising, or automatic listing.

## Architecture rules

- Keep `apps/api` a modular monolith; domain modules must not import HTTP routers from one another.
- Workers in `services/` communicate through stable job payloads and repository/service interfaces.
- Platform-specific behavior belongs under `platforms/<platform>` or rule data, never in generic domain code.
- Every asset transformation creates a new `AssetVersion`. Never mutate or delete the original version through application flows.
- Store object keys in PostgreSQL; store bytes in MinIO/S3-compatible storage.
- Monetary, dimension, and weight values use explicit units and decimal-compatible database types.
- API timestamps are timezone-aware UTC. Public IDs are UUIDs.

## Development workflow

1. Update or add tests with each module.
2. Run the narrow module tests, then the full test suite before handoff.
3. Keep commits scoped to one business module.
4. Update docs when contracts, states, or platform rules change.
5. Prefer the codebase-memory MCP graph for code discovery; fall back to text search for literals and configuration.

## Commands

- API tests: `python -m pytest apps/api/tests`
- API lint: `python -m ruff check apps/api services`
- Web checks: `npm run lint --workspace @ecommerce-visual-workbench/web`
- Web tests: `npm run test --workspace @ecommerce-visual-workbench/web`
- Local stack: `docker compose -f infra/docker/compose.yaml up -d`

