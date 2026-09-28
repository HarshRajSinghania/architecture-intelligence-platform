# Contributing

Thanks for considering a contribution. This project is pre-1.0 (PoC / hardening stage) — expect the
occasional breaking change, and please open an issue before starting significant work so it doesn't
go to waste.

## Development setup

```bash
uv sync                                # install dependencies (Python 3.13, see .python-version)
cp .env.example .env                   # fill in NEO4J_PASSWORD; OPENAI_API_KEY is optional
```

See [`docs/development.md`](docs/development.md) for running the app locally (with or without
Docker), the runtime demo, and the full test layout.

## Test, lint, and format commands

```bash
uv run pytest tests/unit               # fast, no external dependencies
uv run pytest tests/integration        # Testcontainers-backed, needs Docker
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run pyright                         # type check (app/)
```

These are exactly what `.github/workflows/ci.yml` runs on every push and pull request, plus a
`pip-audit` dependency-security scan (`.github/workflows/ci.yml`'s `dependency-audit` job).

## Branch workflow

Fork the repository, branch off `main`, and open a pull request against `main`. Keep PRs focused —
one logical change per PR is much easier to review than a bundle of unrelated ones.

## Commit expectations

Write commit messages that explain *why*, not just *what* — the diff already shows what changed.
Squash-merge is fine; you don't need to hand-craft a perfectly linear history before opening a PR.

## Pull request rules

A PR must, at minimum:

- [ ] tests green (`uv run pytest tests/unit tests/integration`)
- [ ] lint green (`uv run ruff check .`)
- [ ] format green (`uv run ruff format --check .`)
- [ ] type check green (`uv run pyright`)
- [ ] no secrets included (credentials, API keys, real customer/production data)
- [ ] documentation updated when applicable (`README.md`/`docs/` if behavior, an endpoint, or a
      config option changed)

A new **adapter** (declared or runtime source) additionally needs:

- [ ] unit tests
- [ ] an integration fixture (see `tests/fixtures/` and `examples/`)
- [ ] adapter documentation (see the adapter contribution guide below)

CI (`.github/workflows/ci.yml`) enforces the tests/lint/format checks automatically; the rest is
reviewed by a maintainer.

## Adapter contribution guide

AIP has two extension points: a **declared architecture source** (produces an `ArchitectureModel`)
and a **runtime observation source** (produces an `ObservationBatch`). See
[`docs/adapter-development.md`](docs/adapter-development.md) for the full contract each must honor —
deterministic entity IDs, every fact carrying traceable evidence, never guessing an identity from an
unreliable signal, and an explicit attribute allowlist for anything derived from external telemetry.
There's no plugin registry yet; a new adapter is wired in the same way the existing ones are — see
that doc's "Wiring a new adapter in" section.

## Reporting a security vulnerability

Do **not** open a public issue — see [`SECURITY.md`](SECURITY.md).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
