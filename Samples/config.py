"""Central config for all samples -- model choice, provider choice, and pricing.

WHY THIS FILE EXISTS (module 2.8)
--------------------------------
Two things change constantly in AI engineering and should therefore live in
exactly ONE place: which model you call, and which provider you call it through.
Everything else in this repo imports from here, so a rename or a platform move
is a one-line edit instead of a grep-and-pray.

If a sample suddenly fails with "model not found", the model id was most likely
renamed -- change MODEL below and every sample picks it up.
"""
import os

import anthropic

# ---------------------------------------------------------------------------
# 1. WHICH MODEL  (module 2.8 -- model choice)
# ---------------------------------------------------------------------------
# Sonnet is the teaching default: near-Opus quality on agentic work at a third
# of the price, which matters when you are going to run these samples dozens of
# times while learning. Override without editing this file:
#     $env:AI_MODEL = "claude-opus-5"
MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5")

# Price per 1 MILLION tokens, (input, output), in USD. Used by the cost logger
# in step6_service.py. These are list prices and they DO go stale -- the habit
# to build is "look it up, don't remember it."
PRICES = {
    "claude-opus-5":    (5.00, 25.00),   # deepest reasoning; reach for it when correctness > cost
    "claude-sonnet-5":  (3.00, 15.00),   # the workhorse -- default for production volume
    "claude-haiku-4-5": (1.00,  5.00),   # cheap + fast; classification, routing, cheap subagents
}

# Cache pricing is a MULTIPLIER on the input price, not a separate number:
CACHE_WRITE_MULTIPLIER = 1.25   # first call pays a premium to populate the cache
CACHE_READ_MULTIPLIER = 0.10    # every later call reads it back at ~90% off


def cost_usd(usage, model: str = MODEL) -> float:
    """Turn a response's `usage` object into dollars.

    This is the whole of "cost observability" (module 6.2) -- there is no magic
    to it. Note that cached input is billed at a DIFFERENT rate from fresh
    input, which is why caching shows up as a real number here.
    """
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    fresh = getattr(usage, "input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0

    dollars = (
        fresh * price_in
        + cache_write * price_in * CACHE_WRITE_MULTIPLIER
        + cache_read * price_in * CACHE_READ_MULTIPLIER
        + out * price_out
    )
    return dollars / 1_000_000


# ---------------------------------------------------------------------------
# 2. WHICH PROVIDER  (module 2.8 -- portability)
# ---------------------------------------------------------------------------
# The SAME Claude model is reachable through several platforms. The request
# shape is identical; only the client constructor and the credential source
# change. This matters enormously in enterprise and government work, where you
# usually consume AI through a procured cloud platform rather than calling
# api.anthropic.com directly.
#
# Pick one with:   $env:AI_PROVIDER = "bedrock"   (default: "anthropic")
PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")


def get_client(async_: bool = False):
    """Return a client for the configured provider.

    Every client returned here exposes the same `.messages.create(...)` /
    `.messages.stream(...)` surface, which is the entire point: your agent code
    does not know or care which platform it is running against.
    """
    if PROVIDER == "anthropic":
        # Credentials: ANTHROPIC_API_KEY, or an `ant auth login` profile.
        return anthropic.AsyncAnthropic() if async_ else anthropic.Anthropic()

    if PROVIDER == "bedrock":
        # AWS credentials come from the normal boto3/AWS chain. Note that
        # Bedrock model ids carry an "anthropic." prefix: "anthropic.claude-sonnet-5".
        cls = _resolve("AnthropicBedrockMantle", async_)
        return cls(aws_region=os.environ.get("AWS_REGION", "us-east-1"))

    if PROVIDER == "vertex":
        # GCP credentials come from Application Default Credentials.
        # Install with: uv add "anthropic[vertex]"
        cls = _resolve("AnthropicVertex", async_)
        return cls(
            project_id=os.environ["GCP_PROJECT_ID"],
            region=os.environ.get("GCP_REGION", "global"),
        )

    if PROVIDER == "foundry":
        cls = _resolve("AnthropicFoundry", async_)
        return cls(api_key=os.environ["FOUNDRY_API_KEY"],
                   resource=os.environ["FOUNDRY_RESOURCE"])

    raise SystemExit(
        f"Unknown AI_PROVIDER={PROVIDER!r}. "
        "Expected one of: anthropic, bedrock, vertex, foundry."
    )


def _resolve(name: str, async_: bool):
    """Look up a client class on the SDK, preferring the async variant.

    We LOOK IT UP rather than hardcode the async spelling: the async classes
    follow an `Async`-prefix convention, but SDK support varies by platform and
    version, and inventing a class name that does not exist is a worse failure
    than a clear message. Checking `dir(anthropic)` is exactly what you would do
    yourself.
    """
    if async_:
        async_cls = getattr(anthropic, f"Async{name}", None)
        if async_cls is not None:
            return async_cls
        raise SystemExit(
            f"This SDK version has no Async{name}. Either use the sync client "
            f"for PROVIDER={PROVIDER!r} (wrap calls in asyncio.to_thread), or "
            f"check `python -c \"import anthropic; print(dir(anthropic))\"`."
        )
    cls = getattr(anthropic, name, None)
    if cls is None:
        raise SystemExit(
            f"This SDK version has no {name}. Upgrade with `uv add -U anthropic`."
        )
    return cls


# ---------------------------------------------------------------------------
# 3. THINGS THAT CHANGED AND WILL BITE YOU  (module 2.4, rewritten)
# ---------------------------------------------------------------------------
# Current-generation models (Sonnet 5, Opus 5, Opus 4.7/4.8) REJECT the sampling
# knobs that older tutorials all reach for:
#
#   temperature / top_p / top_k  -> 400 error if set to a non-default value
#   thinking.budget_tokens       -> 400 error (replaced by adaptive thinking)
#   assistant-turn prefill       -> 400 error
#
# You steer these models with PROMPTING and with `effort`, not with temperature.
# EFFORT is the modern dial: low | medium | high | xhigh | max, passed as
# output_config={"effort": "..."} -- it controls how much the model thinks
# before answering, which is the knob that actually moves quality now.
EFFORT = os.environ.get("AI_EFFORT", "high")

# Adaptive thinking is ON BY DEFAULT on these models. That has a consequence
# people trip over: `max_tokens` caps thinking + answer TOGETHER, so a budget
# that was fine on an older model can now truncate the answer. Give it room.
MAX_TOKENS_DEFAULT = 4096
