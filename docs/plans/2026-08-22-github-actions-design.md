# GitHub Actions CI Design

## Goal

Add one required-quality workflow that reproduces the repository's authoritative `make verify`
gate for pull requests and pushes to `main`.

## Chosen approach

Use one Ubuntu job named `verify`. It checks out the repository, installs the locked Python and
Web toolchains, starts the existing PostgreSQL/Redis/MinIO Docker Compose services, upgrades a fresh
database to Alembic head, and runs `make verify` in Fixture Mode.

This is preferred over split Python/Web jobs because `make verify` is already the repository's
single acceptance contract. A multi-platform matrix is deferred because the locked runtime is Linux
containers and no cross-platform gate is required by the current milestone.

## Trigger and safety design

- Trigger for pull requests targeting `main`, pushes to `main`, and manual dispatch.
- Grant only read access to repository contents.
- Cancel superseded runs for the same workflow and ref.
- Use Fixture Mode and local development service credentials only.
- Do not configure provider credentials, Live Broker settings, or real-money paths.
- Always print Docker service status and logs when the verification job fails.

## Verification design

A repository contract test will assert the workflow's triggers, least-privilege permission, locked
runtime setup, service startup, migration, and `make verify` command. The test must fail while the
workflow is absent and pass after the minimal workflow is added. Final acceptance is a fresh local
`make verify`, followed by the actual GitHub Actions result on PR #5.
