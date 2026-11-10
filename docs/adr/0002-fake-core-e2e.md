# ADR 0002: Hello World end-to-end on the SDK fake core

- Status: proposed
- Date: 2026-11-10
- SDK: `manufacture-sdk-python` PR #4 (`manufacture.fakecore`), pinned by commit in `versions.env`
- Contract: 0.2.1

## Context

The compose e2e against the real core (examples PR #2) waits for the core engine and its
runtime driver. Until then, and afterwards as the fast check, the examples need a
pipeline-level test that runs in every CI build without Docker.

## Decision

- `hello-world/tests/test_fakecore_e2e.py` runs the real `pipeline.yaml` and the four real
  modules on `manufacture.fakecore.FakeCore`:
  - the first run comes from `hello-init`'s `on_start` and ends `succeeded` with
    `{"text": "hello world!"}`, three stages, one attempt each, and `hello world!` printed
    by `hello-exclaim`;
  - the "Run" button path: `source.trigger` → `run.requested` (dedup by `trigger_id`) → run;
  - six more runs are shared by both `hello-hello` replicas (`replicas: 2` in the spec);
  - data that violates `context.schema` is refused.
- Each test runs over the in-memory broker always, and over RabbitMQ when
  `MF_TEST_AMQP_URL` is set. CI job `fakecore` provides a `rabbitmq:4-management` service
  and also runs the CLI (`make fakecore`, `make fakecore BROKER=amqp`).
- The SDK pin moves to the commit of SDK PR #4. While that PR is not merged this PR stays a
  **draft**; after the merge the pin is moved to the merge commit on SDK `main` (one commit:
  `versions.env`, `pyproject.toml`, `uv.lock`, checked by `test_sdk_pin_is_consistent`).

## Consequences

- A broken module contract (wrong envelope, wrong output) fails here before any image is
  built: the fake core validates every message against the vendored envelope schema.
- The fake core is not the core (no database, API, CEL, blobs): the compose e2e stays the
  check against the real one.
