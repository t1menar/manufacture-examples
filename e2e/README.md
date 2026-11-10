# Hello World e2e on docker compose

`e2e/run.sh` brings up the stack from [`compose.yml`](compose.yml), builds the four module images,
and checks that Hello World runs end to end on the core
([`hello_world_e2e.py`](hello_world_e2e.py)). The success criteria come from the design doc, §10.3:

- the run that `hello-init` requests on start `succeeded`, with `data.text == "hello world!"` and all 3 steps `succeeded`;
- a manual run (`POST /api/v1/pipelines/hello-world/runs`, which sends `source.trigger` to `hello-init`) succeeds too;
- `hello world!` appears in the `hello-exclaim` logs (`GET /api/v1/modules/hello-exclaim/logs`);
- `mf_runs_finished_total{pipeline="hello-world",status="succeeded"}` grows on `/metrics`. This check only
  warns until core C8 ships; `E2E_REQUIRE_METRICS=1` makes it fail instead.

```bash
e2e/run.sh                                   # needs Docker with compose v2 and GNU make
CORE_IMAGE=ghcr.io/t1menar/manufacture-core:main e2e/run.sh
SDK_REF=<sdk commit> E2E_KEEP=1 e2e/run.sh   # other SDK for the images; keep the stack up
```

| Service | Image | Host port |
|---|---|---|
| postgres | `postgres:17-alpine` | — |
| rabbitmq | `rabbitmq:4-management` | 5672, 15672 |
| minio (+ `minio-init`: bucket `mf-blobs`) | `minio/minio` | — |
| registry (module images) | `registry:2` | 5001 |
| core (profile `core`) | `$CORE_IMAGE` | 8080 |

The credentials in `compose.yml` are throwaway local values. `run.sh` generates the admin token and never prints it.

## Status: waiting for a runnable core

`CORE_IMAGE` in `versions.env` is **empty**, so `run.sh` runs in *infra mode*. In this mode it:
- brings up PostgreSQL, RabbitMQ, MinIO and the registry and probes each of them;
- builds the module images, pushes them to `localhost:5001`, and checks that they load their modules;
- reports the core part as **skipped**.

The checker itself is tested in CI against a stub of the gateway (`e2e/tests/`), which runs the real modules.

As of manufacture-core `main` on 2026-11-10 there is only C3 (store, apply, gateway, mfctl, panel), so the full e2e needs the following from the core:

1. **C4 engine:** a linear pipeline runs: it consumes `run.requested`, sends `step.requested`, applies `step.succeeded`, and retries/times out.
2. **C5 registration:** the core accepts `module.online` (contract 0.2.1, SDK `manufacture-sdk-python`) and shows replica status.
3. **C6 docker driver and image:**
   - **Image:** `ghcr.io/t1menar/manufacture-core:<tag>` (`:main`, `:pr-<n>`), entrypoint `manufacture`, command `serve`. It applies migrations on start, or there is a documented `migrate` step.
   - **Driver containers:** started with `MF_RUNTIME=docker` through `/var/run/docker.sock` and attached to the compose network, so modules reach `rabbitmq` and `minio` by name. `compose.yml` passes `MF_DOCKER_NETWORK=mf-e2e_default`; the actual variable name is up to the core.
   - **Driver env:** the module env it passes, with addresses as seen from that network: `MF_AMQP_URL` (per-module RabbitMQ user), `MF_MODULE_NAME`, `MF_REPLICA_ID`, `MF_S3_*`.
   - **Image pulls:** the driver can pull from `localhost:5001`, or uses local images. Images are built on the same Docker host.
   - **Container labels:** module containers carry `manufacture.dev/module=<name>`, so `run.sh` can dump their logs on failure.
4. **Gateway endpoints:**
   - `GET /api/v1/modules/{name}/logs` works for the docker driver (not 501).
   - `RunDetail.context` has an agreed shape. The design doc shows `{run, data}`, while the OpenAPI text says "current run data"; the checker accepts both for now.
5. **C8 metrics (optional for now):** `mf_runs_finished_total` on `/metrics`.

When the core publishes an image, set `CORE_IMAGE` in `versions.env` (a pinned tag, later a digest) in a fix-forward PR. The `e2e` CI job then runs the full check. A different image can also be tried with `workflow_dispatch` (input `core_image`).
