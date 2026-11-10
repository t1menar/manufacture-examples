# ADR 0002: Hello World e2e on docker compose (E2)

- Status: accepted (draft until a runnable core image exists)
- Date: 2026-11-10

## Context

The cross-repo e2e (core design doc §1.4) runs Hello World on the real core with
PostgreSQL, RabbitMQ and MinIO. On 2026-11-10 manufacture-core has no engine, docker driver or
image yet (C4–C6). The e2e is still needed for the work that does not depend on the core: a
reproducible infrastructure, module images from the pinned SDK, and a checker written against
the core's OpenAPI.

## Decision

- **`e2e/compose.yml`** contains postgres 17, `rabbitmq:4-management`, MinIO (`cgr.dev/chainguard/minio`: MinIO stopped publishing
  `minio/minio` to Docker Hub and Quay) with a bucket-init job (`amazon/aws-cli`),
  and a `registry:2` on `localhost:5001` (the registry the Module specs use). It also has the core in a
  `core` profile, with its image from `CORE_IMAGE`.
- **`e2e/run.sh`** is the single entry point, used locally and in CI. It reads `versions.env`, and
  the environment overrides it. It brings up the infrastructure and probes it, then builds and pushes
  the module images. With `CORE_IMAGE` set, it also starts the core and runs the checker. While
  `CORE_IMAGE` is empty, the core part is reported as skipped and the run still passes.
- **`e2e/hello_world_e2e.py`** checks through the public API only, with no `mfctl` or Docker
  label conventions: `/readyz`, `apply`, runs, run detail, module logs, `/metrics`. It uses only
  the standard library, so it runs on any CI image. The admin token comes from the environment
  and is never printed.
- **The checker is tested now** against a stub gateway (`e2e/tests/`) that "executes" the pipeline
  with the real modules through `manufacture.testing`. This covers the API shapes, the failure
  paths (a failed run, wrong data, missing metric, logs returning 501, a wrong token) and the
  context-shape ambiguity.
- **CI**: the `e2e` job runs on every PR, nightly and on `workflow_dispatch` (inputs
  `core_image`, `sdk_ref`). This follows the design doc; the version matrix comes later.

## Consequences

- When the core ships C4–C6, enabling the full e2e is a one-line change: `CORE_IMAGE` in
  `versions.env`. Anything still missing is listed in `e2e/README.md`.
- Until then the PR stays a draft. Its CI is green, but it checks only what exists.
