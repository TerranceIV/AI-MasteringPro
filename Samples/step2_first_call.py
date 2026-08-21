"""
Step 2 Capstone -- your FIRST real LLM feature.

One structured-output call + one STREAMED ASYNC call + a token count. This is
the exact seam where Step 1's mock becomes real:
  - a Pydantic model (1.3) becomes the tool input_schema (2.6)
  - effort is set deliberately (2.4 -- see the note below, this replaces temperature)
  - the reply is streamed token-by-token over async (2.7 / 1.2)
  - tokens are counted before sending (2.2)

Run:   uv run step2_first_call.py
Deps:  anthropic pydantic          (uv add anthropic pydantic)
Env:   ANTHROPIC_API_KEY=sk-ant-...
"""
import asyncio
import os
from typing import Literal

from pydantic import BaseModel, Field

from config import EFFORT, MAX_TOKENS_DEFAULT, MODEL, get_client

client = get_client()                    # 2.8 provider-agnostic (see config.py)
aclient = get_client(async_=True)        # 1.2 the ASYNC client -- used for streaming


# --- 2.6  structured output: Pydantic model -> tool schema -> validate back --
class Sentiment(BaseModel):
    label: Literal["positive", "negative", "neutral"] = Field(description="overall sentiment")
    confidence: float = Field(ge=0, le=1, description="0..1 confidence in the label")
    reason: str = Field(description="one short clause explaining the call")


def classify(text: str) -> Sentiment:
    tools = [{
        "name": "record_sentiment",
        "description": "Record the sentiment of the user's text.",
        "input_schema": Sentiment.model_json_schema(),   # 1.3 -> 2.6
    }]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_DEFAULT,
        # 2.4 THE BIG CHANGE: current models (Sonnet 5, Opus 5, Opus 4.7+) return a
        # 400 if you set temperature / top_p / top_k to a non-default value. Every
        # tutorial written before 2026 says `temperature=0` here -- that request now
        # FAILS. You steer these models with the prompt and with `effort` instead.
        # (temperature=0 never actually guaranteed identical output anyway.)
        output_config={"effort": EFFORT},
        tools=tools,
        tool_choice={"type": "tool", "name": "record_sentiment"},  # force the tool
        messages=[{"role": "user", "content": f"Classify the sentiment of: {text!r}"}],
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    return Sentiment.model_validate(block.input)          # 1.3 validate on the way back


# --- 2.7 / 1.2  streaming, for real, on the async client ---------------------
async def stream_reply(prompt: str) -> None:
    """Note the `async with` + `async for`.

    This is why Step 1 drilled async: while these tokens arrive one at a time,
    the event loop is free to serve other requests. The sync version of this
    function would block a whole web worker for the entire response.
    """
    async with aclient.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS_DEFAULT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:             # arrives token-by-token
            print(text, end="", flush=True)
        final = await stream.get_final_message()
    print(f"\n[output tokens: {final.usage.output_tokens}]")


# --- 2.2  count tokens before you send (cost + context budgeting) -----------
def count(prompt: str) -> int:
    ct = client.messages.count_tokens(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return ct.input_tokens


async def main() -> None:
    review = "The delivery was two days late, but support fixed it in minutes."
    # 2.2 COST INTUITION: you pay per token, INPUT and OUTPUT billed separately.
    #   An agent loop re-sends the whole history every turn, so tokens -- and cost --
    #   grow fast. Real cost = input_tokens * price_in + output_tokens * price_out
    #   (prices live in config.py). Count BEFORE sending to stay within budget.
    #   Careful: token counts are MODEL-SPECIFIC. Current models use a newer
    #   tokenizer that produces ~30% more tokens for the same text than the last
    #   generation, so never reuse a count measured against an older model.
    print(f"input tokens for this prompt: {count(review)}")   # 2.2

    result = classify(review)                             # 2.6
    print("structured result:", result.model_dump())

    print("\nstreaming answer:")
    await stream_reply("In one sentence, why is async important when building agents?")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    asyncio.run(main())
