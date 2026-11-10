"""Hello World end-to-end check against a running core (design doc §10.3).

Talks only to the core's public API (``api/openapi.yaml`` of manufacture-core, gateway 0.3.0):

1. wait for ``/readyz``;
2. ``POST /api/v1/apply`` with ``hello-world/pipeline.yaml``;
3. wait for the run that ``hello-init`` requests on start: ``succeeded``,
   ``data.text == "hello world!"``, all three steps ``succeeded``;
4. ``POST /api/v1/pipelines/hello-world/runs`` (source trigger -> ``hello-init``) and wait for
   a second successful run;
5. ``hello world!`` is in the ``hello-exclaim`` logs (``GET /api/v1/modules/{name}/logs``);
6. ``mf_runs_finished_total{pipeline="hello-world",status="succeeded"}`` grew on ``/metrics``
   (a warning only, unless ``--require-metrics``: the metric arrives with core C8).

Standard library only. The admin token comes from ``MF_ADMIN_TOKEN`` and is never printed.
Exit code 0 on success, 1 on a failed check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIPELINE = "hello-world"
EXPECTED_TEXT = "hello world!"
FINAL_MODULE = "hello-exclaim"
STAGES = ("hello", "world", "exclaim")
TERMINAL_FAILURES = {"failed", "cancelled", "needs_attention"}
METRIC = re.compile(
    r'^mf_runs_finished_total\{(?=[^}]*pipeline="hello-world")(?=[^}]*status="succeeded")[^}]*\}\s+([0-9.eE+-]+)\s*$',
    re.MULTILINE,
)


_sleep = time.sleep  # replaced in tests


class CheckFailed(Exception):
    """An end-to-end expectation did not hold."""


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.body)


class Core:
    """Minimal client of the core gateway."""

    def __init__(self, url: str, token: str, *, timeout_s: float = 10) -> None:
        self.url = url.rstrip("/")
        self._token = token
        self.timeout_s = timeout_s

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        auth: bool = True,
    ) -> Response:
        req = urllib.request.Request(self.url + path, data=body, method=method)  # noqa: S310 (URL from the operator)
        if body is not None:
            req.add_header("Content-Type", content_type)
        if auth:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                return Response(resp.status, resp.read(), dict(resp.headers))
        except urllib.error.HTTPError as err:
            return Response(err.code, err.read(), dict(err.headers))

    def ok(self, method: str, path: str, **kwargs: Any) -> Response:
        resp = self.request(method, path, **kwargs)
        if not 200 <= resp.status < 300:
            raise CheckFailed(f"{method} {path}: HTTP {resp.status}: {resp.body[:500]!r}")
        return resp


def log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def wait_until(what: str, timeout_s: float, probe: Any, *, interval_s: float = 1.0) -> Any:
    """Call ``probe()`` until it returns a truthy value; ``CheckFailed`` from it is final."""
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while True:
        try:
            if result := probe():
                return result
        except CheckFailed:
            raise
        except (OSError, ValueError) as exc:  # connection refused, bad JSON while starting
            last_error = f" (last error: {type(exc).__name__}: {exc})"
        if time.monotonic() >= deadline:
            raise CheckFailed(f"timed out after {timeout_s:.0f}s waiting for {what}{last_error}")
        _sleep(interval_s)


def wait_ready(core: Core, timeout_s: float) -> None:
    wait_until(
        "/readyz", timeout_s, lambda: core.request("GET", "/readyz", auth=False).status == 200
    )
    log("core is ready")


def apply_spec(core: Core, spec: Path) -> None:
    resp = core.ok("POST", "/api/v1/apply", body=spec.read_bytes(), content_type="application/yaml")
    results = resp.json().get("results", [])
    log("applied: " + ", ".join(f"{r['kind']}/{r['name']} {r['action']}" for r in results))


def runs_of(core: Core) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = core.ok(
        "GET", f"/api/v1/runs?pipeline={PIPELINE}&limit=50"
    ).json()["items"]
    return items


def run_data(detail: dict[str, Any]) -> dict[str, Any]:
    """Run data from ``RunDetail.context``. The design doc shows ``{run, data, ...}``; the
    OpenAPI text says "current run data": accept both until the core settles it."""
    context: dict[str, Any] = detail.get("context") or {}
    data = context.get("data", context)
    return data if isinstance(data, dict) else {}


def wait_for_success(core: Core, timeout_s: float, *, exclude: set[str]) -> dict[str, Any]:
    """Wait for a new run (id not in ``exclude``) to succeed; fail fast if it fails."""

    def probe() -> dict[str, Any] | None:
        for run in runs_of(core):
            if run["id"] in exclude:
                continue
            if run["status"] in TERMINAL_FAILURES:
                raise CheckFailed(
                    f"run {run['id']} ended {run['status']}: {run.get('error') or run.get('attention')}"
                )
            if run["status"] == "succeeded":
                return run
        return None

    run: dict[str, Any] = wait_until(f"a succeeded {PIPELINE} run", timeout_s, probe)
    detail = core.ok("GET", f"/api/v1/runs/{run['id']}").json()
    data = run_data(detail)
    if data.get("text") != EXPECTED_TEXT:
        raise CheckFailed(
            f"run {run['id']}: data.text = {data.get('text')!r}, want {EXPECTED_TEXT!r}"
        )
    steps = {s["stage"]: s["status"] for s in detail.get("steps", [])}
    if steps != dict.fromkeys(STAGES, "succeeded"):
        raise CheckFailed(f"run {run['id']}: steps {steps}")
    log(
        f"run {run['id']} succeeded with data.text={EXPECTED_TEXT!r} (trigger {run.get('trigger')})"
    )
    return run


def trigger_run(core: Core) -> None:
    resp = core.ok("POST", f"/api/v1/pipelines/{PIPELINE}/runs", body=b"{}")
    if resp.status == 202:
        log(f"source triggered: trigger_id={resp.json()['trigger_id']}")
    else:  # 201: the core started the run itself
        log(f"run created: {resp.json()['id']}")


def check_logs(core: Core, timeout_s: float) -> None:
    def probe() -> bool:
        resp = core.request("GET", f"/api/v1/modules/{FINAL_MODULE}/logs?tail=1000")
        if resp.status == 501:
            raise CheckFailed(f"the runtime driver cannot read logs (501): {resp.body[:200]!r}")
        if resp.status != 200:
            return False
        # Lines may carry a replica/timestamp prefix from the driver.
        lines = resp.body.decode(errors="replace").splitlines()
        return any(line.rstrip().endswith(EXPECTED_TEXT) for line in lines)

    wait_until(f"{EXPECTED_TEXT!r} in the {FINAL_MODULE} logs", timeout_s, probe)
    log(f"{FINAL_MODULE} printed {EXPECTED_TEXT!r}")


def finished_metric(core: Core) -> float | None:
    resp = core.request("GET", "/metrics", auth=False)
    if resp.status != 200:
        return None
    values = [float(m) for m in METRIC.findall(resp.body.decode(errors="replace"))]
    return sum(values) if values else None


def check_metric(core: Core, before: float | None, *, require: bool) -> None:
    if before is None:
        if require:
            raise CheckFailed(
                'mf_runs_finished_total{pipeline="hello-world",status="succeeded"} is missing'
            )
        log("WARNING: mf_runs_finished_total is not exported yet (core C8); metric check skipped")
        return

    def grown() -> float | None:
        value = finished_metric(core)
        return value if value is not None and value >= before + 1 else None

    after = wait_until("mf_runs_finished_total to grow by 1", 30, grown)
    log(f"mf_runs_finished_total grew {before} -> {after}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default=os.environ.get("MF_URL", "http://127.0.0.1:8080"))
    p.add_argument(
        "--spec",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "hello-world" / "pipeline.yaml",
    )
    p.add_argument("--timeout", type=float, default=180, help="seconds per wait")
    p.add_argument(
        "--require-metrics", action="store_true", help="fail if mf_runs_finished_total is missing"
    )
    args = p.parse_args(argv)
    token = os.environ.get("MF_ADMIN_TOKEN", "")
    if not token:
        print("MF_ADMIN_TOKEN is not set", file=sys.stderr)
        return 2
    core = Core(args.url, token)
    try:
        wait_ready(core, args.timeout)
        apply_spec(core, args.spec)
        first = wait_for_success(core, args.timeout, exclude=set())
        before = finished_metric(core)
        trigger_run(core)
        wait_for_success(core, args.timeout, exclude={first["id"]})
        check_logs(core, args.timeout)
        check_metric(core, before, require=args.require_metrics)
    except CheckFailed as exc:
        log(f"FAILED: {exc}")
        return 1
    log("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
