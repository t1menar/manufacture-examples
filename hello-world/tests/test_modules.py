"""Each module on its own and the whole chain, through ``manufacture.testing``."""

from __future__ import annotations

from typing import Any

import pytest
from manufacture import Module
from manufacture.testing import call_step

from modules.exclaim.main import app as exclaim
from modules.hello.main import app as hello
from modules.init.main import app as init
from modules.world.main import app as world

from .conftest import run_source

TRIGGER = "0b0c5a4e-8f0e-4b8a-9d3c-4f1e2a3b4c5d"


async def test_init_starts_one_run_with_empty_text() -> None:
    result = await run_source(init)
    [run] = result.on_start
    assert run["pipeline"] == "hello-world"
    assert run["data"] == {"text": ""}
    assert run["dedup_key"]  # a fresh id per replica start


async def test_init_starts_a_run_per_trigger() -> None:
    result = await run_source(init, (TRIGGER, None))
    [run] = result.triggered
    assert run == {
        "pipeline": "hello-world",
        "data": {"text": ""},
        "dedup_key": TRIGGER,
        "trigger_id": TRIGGER,
    }


@pytest.mark.parametrize(
    ("module", "text", "expected"),
    [
        (hello, "", "hello"),
        (world, "hello", "hello world"),
        (exclaim, "hello world", "hello world!"),
    ],
    ids=["hello-hello", "hello-world", "hello-exclaim"],
)
async def test_step_appends_its_suffix(module: Module[Any], text: str, expected: str) -> None:
    result = await call_step(module, {"text": text})
    assert result.output == {"text": expected}


async def test_exclaim_prints_the_result(capsys: pytest.CaptureFixture[str]) -> None:
    await call_step(exclaim, {"text": "hello world"})
    assert "hello world!" in capsys.readouterr().out.splitlines()


async def test_whole_chain(capsys: pytest.CaptureFixture[str]) -> None:
    """What the core does with these modules: data flows '' -> 'hello' -> ' world' -> '!'."""
    [run] = (await run_source(init)).on_start
    data = run["data"]
    for module in (hello, world, exclaim):
        output = (await call_step(module, data)).output
        data = {**data, **output}  # merge: data (JSON Merge Patch of a flat object)
    assert data == {"text": "hello world!"}
    assert capsys.readouterr().out.splitlines()[-1] == "hello world!"


@pytest.mark.parametrize(
    "bad", [{}, {"text": 1}, {"txt": ""}], ids=["missing", "not-a-string", "typo"]
)
async def test_invalid_input_fails_fatal(bad: dict[str, object]) -> None:
    result = await call_step(hello, bad)
    assert not result.succeeded
    assert result.payload["class"] == "fatal"
    assert result.payload["code"] == "input_invalid"
