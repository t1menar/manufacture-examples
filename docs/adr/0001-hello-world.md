# ADR 0001: Hello World example (E1)

- Status: accepted
- Date: 2026-11-10
- Contract: 0.2.1 (manufacture-core `contract-v0.2.1`), SDK `manufacture-sdk-python@d7caeca`

## Context

Hello World (core design doc §10) is the smallest end-to-end pipeline: four modules build
`"hello world!"` from `""` and the last one prints it. It is the first user of the SDK and
the fixture of the cross-repo e2e test (E2).

## Decision

- **Layout.** `hello-world/pipeline.yaml` (4 `Module` + 1 `Pipeline`, as in §10.1) and
  `hello-world/modules/{init,hello,world,exclaim}/main.py`, one file per module, the code from
  §10.2. One shared `hello-world/Dockerfile` (`ARG MODULE`) builds
  `localhost:5001/mf-hello-<module>:0.1.0`.
- **Deviation from §10.2:** `app.run()` is guarded by `if __name__ == "__main__":` so the
  tests can import the modules. The container still runs `python main.py`.
- **Pins in one place.** `versions.env` holds `SDK_REF` (a full commit SHA on SDK `main`) and
  `CORE_REF` (the commit of `contract-v0.2.1`). `pyproject.toml` takes the SDK as a git
  dependency on the same SHA (`[tool.uv.sources]`), and the images install the GitHub archive
  of that SHA (no git in the image). `test_sdk_pin_is_consistent` keeps the pins identical in
  `versions.env`, `pyproject.toml` and `uv.lock`. The SDK is not on PyPI yet.
- **Checks (CI).**
  - `ruff`, `mypy --strict`, `pytest` (Python 3.12, 3.13).
  - `manufacture validate --strict -f hello-world/`: the core's own validator, built with
    `go install` from `CORE_REF`. `--strict` turns references to unknown modules into errors.
  - Module unit tests through `manufacture.testing` (`call_step`, and `FakeTransport` with the
    runtime for the source). Every message the modules publish is validated against the
    envelope schema by `FakeTransport`.
  - Spec/code agreement: module names, image names and tags, stage order, step kinds, and that
    the step input/output schemas announced in `module.online` match `spec.context.schema`.
  - The images build and load their module (`mf-module manifest main:app`).
- **What E1 does not rely on.** Contract 0.3.0 is in preparation (step keys/visits,
  `step.waiting`, usage, confirm, run lifecycle events, fake core). Hello World uses only
  `step.requested → step.succeeded` and one source. The only part expected to change is
  the start of the run: the source's `on_start=True` is **temporary** until schedules move to
  the core (answer to SDK ADR 0003 Q4). It is marked as such in `modules/init/main.py`.

## Consequences

- Bumping the SDK is a one-commit change: `SDK_REF` in `versions.env` and `pyproject.toml`,
  then `uv lock`.
- The examples are built against an exact SDK and contract. E2 (compose e2e) reuses the same
  images and pins.
