"""hello-init: the source of the Hello World pipeline.

Starts one run with an empty string when the replica starts, and one more on every
``source.trigger`` (the "Run" button in the admin panel, ``mfctl run hello-world``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from manufacture import Module, RunRequest, SourceContext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

app = Module("hello-init", version="0.1.0")


# TEMPORARY: `on_start` runs in every replica of this module (replicas: 1 here). Schedules
# move into the core (architect, ADR 0003 Q4); then the first run comes from the core via
# source.trigger and `on_start=True` goes away. See docs/adr/0001-hello-world.md.
@app.source(pipeline="hello-world", on_start=True)
async def start(ctx: SourceContext) -> AsyncIterator[RunRequest]:
    yield RunRequest(data={"text": ""}, dedup_key=ctx.trigger_id)


if __name__ == "__main__":
    app.run()
