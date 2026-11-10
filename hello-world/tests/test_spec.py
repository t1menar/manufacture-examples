"""pipeline.yaml agrees with the module code and the vendored contract.

``manufacture validate --strict`` from manufacture-core is run by CI (``make validate``); these
tests cover what the core validator cannot know: the Python code behind each module.
"""

from __future__ import annotations

import re
import tomllib
from typing import Any

import pytest
from manufacture import Module
from manufacture.contract import validate_resource

from modules.exclaim.main import app as exclaim
from modules.hello.main import app as hello
from modules.init.main import app as init
from modules.world.main import app as world

from .conftest import EXAMPLE, REPO, load_docs

APPS: dict[str, Module[Any]] = {m.name: m for m in (init, hello, world, exclaim)}
DIRS = {
    "hello-init": "init",
    "hello-hello": "hello",
    "hello-world": "world",
    "hello-exclaim": "exclaim",
}


def by_kind(kind: str) -> list[dict[str, Any]]:
    return [d for d in load_docs() if d["kind"] == kind]


@pytest.mark.parametrize("doc", load_docs(), ids=lambda d: f"{d['kind']}/{d['metadata']['name']}")
def test_resource_matches_sdk_vendored_schema(doc: dict[str, Any]) -> None:
    assert validate_resource(doc) == []


def test_every_module_has_code_and_vice_versa() -> None:
    names = {d["metadata"]["name"] for d in by_kind("Module")}
    assert names == set(APPS)
    for name, folder in DIRS.items():
        assert (EXAMPLE / "modules" / folder / "main.py").is_file(), name


@pytest.mark.parametrize("doc", by_kind("Module"), ids=lambda d: d["metadata"]["name"])
def test_image_name_and_version_match_the_module(doc: dict[str, Any]) -> None:
    name = doc["metadata"]["name"]
    repo, tag = doc["spec"]["image"].rsplit(":", 1)
    assert repo == f"localhost:5001/mf-{name}"
    assert tag == APPS[name].version


def test_pipeline_wiring() -> None:
    [pipeline] = by_kind("Pipeline")
    spec = pipeline["spec"]
    assert spec["trigger"]["source"] == "hello-init"
    assert [s.pipeline for s in init.sources] == [pipeline["metadata"]["name"]]
    steps = [stage["step"]["module"] for stage in spec["stages"]]
    assert steps == ["hello-hello", "hello-world", "hello-exclaim"]
    for module in steps:
        assert APPS[module].kinds == ["step"]
    assert init.kinds == ["source"]


def test_context_schema_matches_the_step_models() -> None:
    [pipeline] = by_kind("Pipeline")
    context = pipeline["spec"]["context"]["schema"]
    for name in ("hello-hello", "hello-world", "hello-exclaim"):
        step = APPS[name].manifest()["step"]  # the schemas announced in module.online
        for schema in (step["input_schema"], step["output_schema"]):
            assert schema["required"] == context["required"]
            assert {k: v["type"] for k, v in schema["properties"].items()} == {
                k: v["type"] for k, v in context["properties"].items()
            }


def test_sdk_pin_is_consistent() -> None:
    env = dict(
        line.split("=", 1)
        for line in (REPO / "versions.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert re.fullmatch(r"[0-9a-f]{40}", env["SDK_REF"]), "pin the SDK to a full commit SHA"
    assert re.fullmatch(r"[0-9a-f]{40}", env["CORE_REF"]), "pin the core to a full commit SHA"
    project = tomllib.loads((REPO / "pyproject.toml").read_text())
    source = project["tool"]["uv"]["sources"]["manufacture-sdk"]
    assert source == {"git": env["SDK_REPO"], "rev": env["SDK_REF"]}
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    [sdk] = [p for p in lock["package"] if p["name"] == "manufacture-sdk"]
    assert sdk["source"]["git"].endswith("#" + env["SDK_REF"])
