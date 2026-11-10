# manufacture-examples

Example pipelines and modules for [Manufacture](https://github.com/t1menar/manufacture-core),
written with the [Python SDK](https://github.com/t1menar/manufacture-sdk-python).

| Example | What it shows |
|---|---|
| [`hello-world/`](hello-world/) | 4 modules: `""` → `"hello"` → `" world"` → `"!"`, the last prints `hello world!` |

## Hello World

```
hello-init (source) ──run.requested {text: ""}──▶ core
  stage hello   → hello-hello   (×2 replicas)  "" → "hello"
  stage world   → hello-world                  "hello" → "hello world"
  stage exclaim → hello-exclaim                "hello world" → "hello world!"  (printed to stdout)
```

- Spec: [`hello-world/pipeline.yaml`](hello-world/pipeline.yaml)
- Code: [`hello-world/modules/*/main.py`](hello-world/modules/)
- Notes: [ADR 0001](docs/adr/0001-hello-world.md)

Try a module without a broker or core:

```bash
uv sync --locked
echo '{"text": "hello world"}' > /tmp/in.json
uv run mf-module test hello-world/modules/exclaim/main.py:app --input /tmp/in.json   # prints hello world!
uv run mf-module manifest hello-world/modules/hello/main.py:app                      # what module.online announces
```

Images (Docker), with the SDK pinned in [`versions.env`](versions.env):

```bash
make -C hello-world images      # localhost:5001/mf-hello-{init,hello,world,exclaim}:0.1.0
make -C hello-world manifests   # smoke test of the images
```

The whole pipeline end-to-end without the platform, on the SDK fake core
([SDK ADR 0004](https://github.com/t1menar/manufacture-sdk-python/blob/main/docs/adr/0004-fake-core.md)):
the real spec and the four real modules, the module protocol over an in-memory broker or a
real RabbitMQ. Notes: [ADR 0003](docs/adr/0003-fake-core-e2e.md).

```bash
make fakecore                    # mf-fakecore: waits for the on_start run, prints "hello world!"
make test                        # includes hello-world/tests/test_fakecore_e2e.py (memory broker)
make test MF_TEST_AMQP_URL=amqp://guest:guest@127.0.0.1:5672/   # + the same tests over RabbitMQ
```

Running on a core (`make up`, `mfctl apply -f hello-world/`) arrives with the compose e2e (E2).

## Development

Requires [uv](https://docs.astral.sh/uv/), Python 3.12+, and Go (for `manufacture validate`).

```bash
make sync       # SDK at SDK_REF + dev tools
make check      # ruff, mypy --strict, pytest, manufacture validate --strict
make validate   # only the core validator (built from CORE_REF in versions.env)
```

## License

MIT
