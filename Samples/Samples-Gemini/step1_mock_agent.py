"""
Step 1 Capstone -- a MOCK async agent loop (NO real LLM, NO API key).

This file is IDENTICAL to ../Samples/step1_mock_agent.py on purpose. There is
no vendor-specific code in it at all -- decorators, async, Pydantic schemas,
retry, and JSON parsing don't know or care whether Step 2 ends up calling
Claude or Gemini. That is exactly the point of doing Step 1 before picking a
vendor: the *shape* of agent code is the reusable 80%; the provider is a
detail you plug in afterwards (see step2_first_call.py for where that
actually happens, and how much less it changes than you'd expect).

  1.1 decorators + a tool registry          1.5 retry with exponential backoff
  1.2 async / gather / Semaphore            1.6 config from an env var
  1.3 Pydantic tool schemas + validation    1.7 uv-runnable single file
  1.4 defensive messy-JSON parsing

Run:   uv run step1_mock_agent.py
Deps:  pydantic          (uv add pydantic)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field, ValidationError


# --- 1.3  tool argument models (a Pydantic model == the tool's contract) ----
class WeatherArgs(BaseModel):
    city: str = Field(description="City name")
    units: Literal["c", "f"] = "c"


class AddArgs(BaseModel):
    a: float
    b: float


# --- 1.1  a tool registry populated by a decorator --------------------------
@dataclass
class Tool:
    name: str
    fn: Callable[..., Awaitable[str]]
    args_model: type[BaseModel]
    schema: dict


TOOLS: dict[str, Tool] = {}


def tool(model: type[BaseModel]):
    """Register an async function as a tool, deriving its JSON schema from `model` (1.3)."""
    def decorator(fn: Callable[..., Awaitable[str]]):
        TOOLS[fn.__name__] = Tool(fn.__name__, fn, model, model.model_json_schema())
        return fn
    return decorator


# --- 1.5  retry with exponential backoff + jitter ---------------------------
class RetryableError(Exception):
    """Recoverable failure -- worth retrying (e.g. a 503)."""


def with_retry(attempts: int = 4, base: float = 0.05):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except RetryableError:
                    if i == attempts - 1:
                        raise
                    delay = base * (2 ** i) + random.random() * base  # backoff + jitter
                    await asyncio.sleep(delay)
        return wrapper
    return decorator


# --- 1.2 + 1.6  a mock async "API" standing in for a real LLM/tool endpoint --
# Construct the Semaphore lazily so it binds to the running loop.
_MAX = int(os.environ.get("MAX_CONCURRENCY", "3"))  # 1.6 config from env
_sem: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_MAX)
    return _sem


@with_retry()
async def mock_call(payload: dict) -> str:
    async with _semaphore():                       # 1.2 cap concurrency
        await asyncio.sleep(random.random() * 0.05)  # NOT time.sleep -- that blocks (1.2)
        if random.random() < 0.5:                  # simulate a flaky endpoint
            raise RetryableError("503 overloaded")
        # Return messy JSON wrapped in prose ON PURPOSE, so 1.4 has to work for its living.
        return f"Sure!\n```json\n{json.dumps(payload)}\n```\nhope that helps"


# --- 1.4  defensive JSON extraction (LLM output is *almost* JSON) -----------
def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in: {text!r}")
    return json.loads(match.group(0))


# --- tool implementations ---------------------------------------------------
@tool(WeatherArgs)
async def get_weather(city: str, units: str = "c") -> str:
    raw = await mock_call({"temp": random.randint(20, 34), "units": units, "city": city})
    data = extract_json(raw)
    return f"{data['temp']}°{data['units'].upper()} in {data['city']}"


@tool(AddArgs)
async def add(a: float, b: float) -> str:
    return str(a + b)


# --- the agent loop (a mock "planner" produces the tool calls) --------------
async def dispatch(name: str, args: dict) -> str:
    """Validate args against the tool's Pydantic model (1.3), then call it."""
    spec = TOOLS[name]
    try:
        valid = spec.args_model.model_validate(args)
    except ValidationError as e:
        return f"ERROR: bad args for {name} -- {e.error_count()} problem(s)"
    try:
        return await spec.fn(**valid.model_dump())
    except Exception as exc:  # 1.5 retries exhausted, or any other tool failure -- still just data
        return f"ERROR: {name} failed -- {exc}"


async def main() -> None:
    print("Registered tools:", list(TOOLS))
    print("Example schema (get_weather):")
    print(json.dumps(TOOLS["get_weather"].schema, indent=2))

    # A "plan" a real LLM would emit. We run all tool calls CONCURRENTLY (1.2).
    plan = [
        ("get_weather", {"city": "Singapore", "units": "c"}),
        ("get_weather", {"city": "Tokyo", "units": "f"}),
        ("add", {"a": 21, "b": 21}),
        ("get_weather", {"city": "Oslo", "units": "x"}),   # purposely will be invalid -> caught by 1.3
    ]
    results = await asyncio.gather(*(dispatch(name, args) for name, args in plan))

    print("\nResults:")
    for (name, args), result in zip(plan, results):
        print(f"  {name}({args}) -> {result}")


if __name__ == "__main__":
    asyncio.run(main())
