"""Helpers shared by the Hello World tests (no broker, no core)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from manufacture import Module, RuntimeSettings
from manufacture.runtime import Runtime
from manufacture.testing import FakeTransport, source_trigger

EXAMPLE = Path(__file__).resolve().parent.parent
REPO = EXAMPLE.parent


@pytest.fixture(autouse=True)
def _no_ambient_mf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's MF_* variables must not leak into the tests."""
    import os

    for key in list(os.environ):
        if key.startswith("MF_"):
            monkeypatch.delenv(key)


def load_docs(path: Path = EXAMPLE / "pipeline.yaml") -> list[dict[str, Any]]:
    with path.open() as f:
        return [d for d in yaml.safe_load_all(f) if d is not None]


@dataclass
class SourceRun:
    on_start: list[dict[str, Any]]
    triggered: list[dict[str, Any]]


async def run_source(
    module: Module[Any], *triggers: tuple[str, dict[str, Any] | None]
) -> SourceRun:
    """Start the module like a replica would, deliver ``source.trigger`` messages
    ``(trigger_id, data)`` and return the ``run.requested`` payloads it published."""
    transport = FakeTransport()
    settings = RuntimeSettings(health_addr="", replica_id="test", module_heartbeat_s=3600)
    runtime = Runtime(module, settings=settings, transport=transport)
    await runtime.start()
    try:
        starts = sum(1 for s in module.sources if s.on_start)
        on_start = [p.payload for p in await transport.wait_for("run.requested", count=starts)]
        for trigger_id, data in triggers:
            pipeline = module.sources[0].pipeline
            delivery = await transport.deliver(
                source_trigger(pipeline, trigger_id=trigger_id, data=data)
            )
            assert await delivery.wait() == "acked"
        published = [p.payload for p in transport.of_type("run.requested")]
    finally:
        await runtime.stop()
    return SourceRun(on_start=on_start, triggered=published[len(on_start) :])
