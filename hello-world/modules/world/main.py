"""hello-world: appends ``" world"`` to ``text``."""

from __future__ import annotations

from manufacture import Context, Module
from pydantic import BaseModel


class Text(BaseModel):
    text: str


app = Module("hello-world", version="0.1.0")


@app.step(input=Text, output=Text)
async def handle(ctx: Context, inp: Text) -> Text:
    return Text(text=inp.text + " world")


if __name__ == "__main__":
    app.run()
