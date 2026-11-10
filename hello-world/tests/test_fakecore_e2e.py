"""Hello World end-to-end on the SDK fake core: the real modules, the real spec, the
module protocol over an in-memory broker (always) or RabbitMQ (``MF_TEST_AMQP_URL``).

No platform: the fake core plays the engine. It is not the core (see SDK ADR 0004);
the compose e2e in ``e2e/`` stays the check against the real one.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from manufacture.fakecore import FakeCore, Run

from modules.exclaim.main import app as exclaim
from modules.hello.main import app as hello
from modules.init.main import app as init
from modules.world.main import app as world

from .conftest import EXAMPLE

# Read at import: the autouse fixture in conftest removes MF_* variables from the tests.
AMQP_URL = os.environ.get("MF_TEST_AMQP_URL", "")
SPEC = EXAMPLE / "pipeline.yaml"
MODULES = [init, hello, world, exclaim]

BROKERS = [
    "memory",
    pytest.param(
        "amqp",
        marks=pytest.mark.skipif(not AMQP_URL, reason="set MF_TEST_AMQP_URL for RabbitMQ"),
    ),
]


@pytest.fixture(params=BROKERS)
async def core(request: pytest.FixtureRequest) -> AsyncIterator[FakeCore]:
    async with FakeCore(SPEC, MODULES, broker=request.param, amqp_url=AMQP_URL or None) as fc:
        yield fc


def assert_hello_world(run: Run) -> None:
    assert run.status == "succeeded", run.to_dict()
    assert run.data == {"text": "hello world!"}
    assert [(s.stage, s.module, s.status) for s in run.steps] == [
        ("hello", "hello-hello", "succeeded"),
        ("world", "hello-world", "succeeded"),
        ("exclaim", "hello-exclaim", "succeeded"),
    ]
    assert all(len(s.attempts) == 1 for s in run.steps)


async def test_first_run_comes_from_init_on_start(
    capsys: pytest.CaptureFixture[str],  # before ``core``: capture from the first replica on
    core: FakeCore,
) -> None:
    [run] = await core.wait_for_runs("hello-world", timeout=30)
    assert_hello_world(run)
    assert (run.trigger.kind, run.trigger.by) == ("source", "hello-init")
    assert "hello world!" in capsys.readouterr().out.splitlines()  # what exclaim prints


async def test_run_button_triggers_the_source(core: FakeCore) -> None:
    await core.wait_for_runs("hello-world", timeout=30)  # the on_start run
    trigger_id = await core.trigger("hello-world")
    [run] = await core.wait_for_runs("hello-world", trigger_id=trigger_id, timeout=30)
    assert_hello_world(run)
    assert run.dedup_key == trigger_id


async def test_runs_are_spread_over_both_hello_replicas(core: FakeCore) -> None:
    await core.wait_for_replicas(5)  # init, hello x2, world, exclaim
    await core.wait_for_runs("hello-world", timeout=30)
    runs = [await core.start_run("hello-world", {"text": ""}) for _ in range(6)]
    for run in runs:
        assert_hello_world(await core.wait(run.id, timeout=30))
    used = {r.step("hello").attempts[0].replica_id for r in runs}
    assert used == {"hello-hello-0", "hello-hello-1"}


async def test_spec_input_is_enforced(core: FakeCore) -> None:
    with pytest.raises(ValueError, match="invalid_data"):
        await core.start_run("hello-world", {})
