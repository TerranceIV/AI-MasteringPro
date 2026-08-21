"""
Step 2 Capstone (Gemini twin) -- your FIRST real LLM feature, on Gemini
instead of Claude.

Same three concepts as ../Samples/step2_first_call.py: structured output, a
streamed async call, and counting tokens before you send. The CONCEPTS
transfer one-for-one; the API SHAPE does not. Every difference below is a
deliberate teaching point, called out where it happens -- not a random
rewrite.

Run:   uv run step2_first_call.py
Deps:  google-genai pydantic          (uv add google-genai pydantic)
Env:   GEMINI_API_KEY=...             (free, no card: https://aistudio.google.com/apikey)
"""
import asyncio
from typing import Literal

from google.genai import types
from pydantic import BaseModel, Field

from config import MAX_OUTPUT_TOKENS_DEFAULT, MODEL, THINKING_BUDGET, get_client

client = get_client()   # ONE client for both sync and async calls -- see config.py


# --- structured output: Gemini has a NATIVE mode for this --------------------
# Claude has no response-schema mode (as of the Anthropic samples), so
# ../Samples/step2_first_call.py fakes structured output by forcing a tool
# call and manually validating the tool_use block. Gemini instead has a
# dedicated response_schema + response_mime_type pair on GenerateContentConfig,
# and hands back an ALREADY-VALIDATED object via `response.parsed` -- no
# forcing, no manual model_validate on the way back.
class Sentiment(BaseModel):
    label: Literal["positive", "negative", "neutral"] = Field(description="overall sentiment")
    confidence: float = Field(ge=0, le=1, description="0..1 confidence in the label")
    reason: str = Field(description="one short clause explaining the call")


def classify(text: str) -> Sentiment:
    response = client.models.generate_content(
        model=MODEL,
        contents=f"Classify the sentiment of: {text!r}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Sentiment,   # pass the Pydantic CLASS directly
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        ),
    )
    # `.parsed` is the SDK's own validated instance. If your installed
    # google-genai version predates this convenience field, the fallback is
    # `Sentiment.model_validate_json(response.text)` -- same idea as Claude's
    # manual validate, just one line instead of digging a tool_use block out
    # of response.content first.
    return response.parsed


# --- streaming, on the SAME client via the .aio namespace --------------------
async def stream_reply(prompt: str) -> None:
    """Note there's no separate async client to construct here -- config.py's
    single genai.Client exposes `.aio.models` for every async call. Compare
    with the Anthropic folder, which has to build Anthropic() and
    AsyncAnthropic() as two different objects.
    """
    final_usage = None
    stream = await client.aio.models.generate_content_stream(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS_DEFAULT,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        ),
    )
    async for chunk in stream:                      # arrives token-by-token, same idea as 2.7
        if chunk.text:
            print(chunk.text, end="", flush=True)
        if chunk.usage_metadata:
            final_usage = chunk.usage_metadata       # usage rides along with each chunk
    print(f"\n[output tokens: {final_usage.candidates_token_count}]")


# --- count tokens before you send (cost + context budgeting) -----------------
def count(prompt: str) -> int:
    result = client.models.count_tokens(model=MODEL, contents=prompt)
    return result.total_tokens


async def main() -> None:
    review = "The delivery was two days late, but support fixed it in minutes."
    # COST INTUITION, same as 2.2: you pay per token, input and output billed
    # separately -- but on Gemini, THINKING tokens get their own counter
    # (thoughts_token_count) instead of hiding inside the output count the way
    # Claude does it. See cost_usd() in config.py for where that matters.
    print(f"input tokens for this prompt: {count(review)}")

    result = classify(review)
    print("structured result:", result.model_dump())

    print("\nstreaming answer:")
    await stream_reply("In one sentence, why is async important when building agents?")


if __name__ == "__main__":
    asyncio.run(main())
