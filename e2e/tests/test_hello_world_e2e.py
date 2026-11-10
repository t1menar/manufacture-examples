"""The e2e checker against a stub of the core gateway.

The stub serves the API shapes of manufacture-core ``api/openapi.yaml`` and "executes" the
pipeline by calling the real Hello World modules through ``manufacture.testing``, so the
checker is exercised end to end without a core (no runnable core image exists yet).
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from manufacture.testing import call_step
from tests.conftest import run_source  # hello-world/tests (SDK call_source arrives in SDK PR #3)

from e2e import hello_world_e2e as e2e
from modules.exclaim.main import app as exclaim
from modules.hello.main import app as hello
from modules.init.main import app as init
from modules.world.main import app as world

TOKEN = "t" * 40


@dataclass
class StubCore:
    """Behaviour switches for the failure tests."""

    fail_run: bool = False
    wrong_text: bool = False
    metrics: bool = True
    logs_status: int = 200
    runs: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    applied: list[bytes] = field(default_factory=list)

    def execute(self, data: dict[str, Any], trigger: dict[str, str]) -> None:
        """Run the 3 stages with the real modules (what the engine would do)."""
        steps: list[dict[str, Any]] = []
        for stage, module in zip(e2e.STAGES, (hello, world, exclaim), strict=True):
            result = asyncio.run(call_step(module, data))
            data = {**data, **result.output}
            steps.append(
                {
                    "stage": stage,
                    "stage_index": len(steps),
                    "step_id": stage,
                    "module": module.name,
                    "status": "succeeded",
                    "visits": 1,
                    "attempts": [],
                    "output": result.output,
                }
            )
        if self.wrong_text:
            data = {"text": "hello world?"}
        self.logs.append(f"hello-exclaim-1 | {data['text']}")
        run_id = str(uuid.uuid4())
        run = {
            "id": run_id,
            "pipeline": e2e.PIPELINE,
            "revision": 1,
            "stage_index": 2,
            "trigger": trigger,
            "created_at": "2026-11-10T20:00:00Z",
            "status": "failed" if self.fail_run else "succeeded",
        }
        if self.fail_run:
            run["error"] = {"class": "fatal", "code": "boom", "message": "stub failure"}
        self.runs.insert(0, run)
        self.details[run_id] = {
            "run": run,
            "steps": steps,
            "snapshots": [],
            "context": {"run": {"id": run_id}, "data": data},
        }

    def on_apply(self, body: bytes) -> None:
        self.applied.append(body)
        for req in asyncio.run(run_source(init)).on_start:
            self.execute(req["data"], {"kind": "source", "by": "hello-init"})

    def on_trigger(self) -> str:
        trigger_id = str(uuid.uuid4())
        for req in asyncio.run(run_source(init, (trigger_id, None))).triggered:
            self.execute(req["data"], {"kind": "manual"})
        return trigger_id

    def metrics_text(self) -> str:
        ok = sum(1 for r in self.runs if r["status"] == "succeeded")
        return (
            "# TYPE mf_runs_finished_total counter\n"
            f'mf_runs_finished_total{{pipeline="hello-world",status="succeeded"}} {ok}\n'
            'mf_runs_finished_total{pipeline="other",status="succeeded"} 7\n'
        )


def make_handler(stub: StubCore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def send(self, status: int, body: Any, content_type: str = "application/json") -> None:
            raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            if self.headers.get("Authorization") == f"Bearer {TOKEN}":
                return True
            self.send(401, {"title": "unauthorized"})
            return False

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/readyz":
                return self.send(200, "ok", "text/plain")
            if path == "/metrics":
                return self.send(200 if stub.metrics else 404, stub.metrics_text(), "text/plain")
            if not self.authorized():
                return None
            if path == "/api/v1/runs":
                return self.send(200, {"items": stub.runs})
            if path.startswith("/api/v1/runs/"):
                return self.send(200, stub.details[path.rsplit("/", 1)[1]])
            if path == "/api/v1/modules/hello-exclaim/logs":
                return self.send(stub.logs_status, "\n".join(stub.logs), "text/plain")
            return self.send(404, {"title": "not found"})

        def do_POST(self) -> None:
            if not self.authorized():
                return None
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path == "/api/v1/apply":
                assert self.headers["Content-Type"] == "application/yaml"
                stub.on_apply(body)
                return self.send(
                    200,
                    {
                        "applied": True,
                        "results": [
                            {
                                "kind": "Pipeline",
                                "name": "hello-world",
                                "action": "created",
                                "revision": 1,
                            }
                        ],
                    },
                )
            if self.path == "/api/v1/pipelines/hello-world/runs":
                return self.send(202, {"trigger_id": stub.on_trigger()})
            return self.send(404, {"title": "not found"})

    return Handler


@pytest.fixture
def stub() -> StubCore:
    return StubCore()


@pytest.fixture
def url(stub: StubCore) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(stub))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def run_checker(url: str, monkeypatch: pytest.MonkeyPatch, *extra: str, token: str = TOKEN) -> int:
    monkeypatch.setenv("MF_ADMIN_TOKEN", token)
    monkeypatch.setattr(e2e, "_sleep", lambda _s: None)
    return e2e.main(["--url", url, "--timeout", "2", *extra])


def test_passes_against_a_working_core(
    url: str, stub: StubCore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_checker(url, monkeypatch, "--require-metrics") == 0
    out = capsys.readouterr().out
    assert "PASSED" in out
    assert "mf_runs_finished_total grew 1.0 -> 2.0" in out
    assert TOKEN not in out
    assert stub.applied and b"kind: Pipeline" in stub.applied[0]
    assert len(stub.runs) == 2


def test_failed_run_fails_fast(
    url: str, stub: StubCore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub.fail_run = True
    assert run_checker(url, monkeypatch) == 1
    assert "ended failed" in capsys.readouterr().out


def test_wrong_text_fails(
    url: str, stub: StubCore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub.wrong_text = True
    assert run_checker(url, monkeypatch) == 1
    assert "data.text = 'hello world?'" in capsys.readouterr().out


def test_missing_metric_warns_unless_required(
    url: str, stub: StubCore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub.metrics = False
    assert run_checker(url, monkeypatch) == 0
    assert "metric check skipped" in capsys.readouterr().out
    stub.runs.clear()
    assert run_checker(url, monkeypatch, "--require-metrics") == 1


def test_logs_not_supported_fails(
    url: str, stub: StubCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub.logs_status = 501
    assert run_checker(url, monkeypatch) == 1


def test_wrong_token_fails(
    url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_checker(url, monkeypatch, token="wrong" * 8) == 1
    assert "HTTP 401" in capsys.readouterr().out


def test_token_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_ADMIN_TOKEN", raising=False)
    assert e2e.main(["--url", "http://127.0.0.1:9"]) == 2


@pytest.mark.parametrize(
    ("context", "data"),
    [({"run": {}, "data": {"text": "x"}}, {"text": "x"}), ({"text": "x"}, {"text": "x"}), ({}, {})],
    ids=["design-doc-shape", "data-only", "empty"],
)
def test_run_data_accepts_both_context_shapes(
    context: dict[str, Any], data: dict[str, Any]
) -> None:
    assert e2e.run_data({"context": context}) == data
