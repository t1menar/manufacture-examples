"""hello-exclaim: appends ``"!"`` and prints the result (``hello world!``) to stdout."""

from __future__ import annotations

from manufacture import Context, Module
from pydantic import BaseModel


class Text(BaseModel):
    text: str


app = Module("hello-exclaim", version="0.1.0")


@app.step(input=Text, output=Text)
async def handle(ctx: Context, inp: Text) -> Text:
    result = inp.text + "!"
    print(result, flush=True)  # the e2e test looks for this line in the container log
    ctx.log.info("pipeline finished", text=result)
    return Text(text=result)


if __name__ == "__main__":
    app.run()
