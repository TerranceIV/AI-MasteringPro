"""Central config for the Gemini samples -- model choice, pricing, and client setup.

WHY THIS FILE EXISTS
--------------------
This is the Gemini twin of ../Samples/config.py (module 2.8). Same reasoning:
which model you call, and its price, should live in exactly ONE place. Swap
MODEL below (or the env var) and every sample in this folder picks it up.

Read README.md first -- it lists everything that differs between the Claude
API (../Samples) and the Gemini API (here). This file is where most of those
differences actually live in code.
"""
import os

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. WHICH MODEL
# ---------------------------------------------------------------------------
# "-latest" aliases exist SPECIFICALLY so you don't have to track model churn
# by hand -- Google hot-swaps them to the newest release in that family (with
# a 2-week email notice before any breaking change). As of 2026, Flash and
# Flash-Lite are the free-tier-eligible families; Pro is paid only. Override
# without editing this file:
#     $env:AI_MODEL = "gemini-pro-latest"
MODEL = os.environ.get("AI_MODEL", "gemini-flash-latest")

# Price per 1 MILLION tokens, (input, output), in USD -- list prices, and they
# go stale even faster here than in the Claude folder (three Flash generations
# shipped between March and August 2026 alone). Look it up, don't remember it:
# https://ai.google.dev/gemini-api/docs/pricing
PRICES = {
    "gemini-pro-latest":        (2.00, 12.00),  # deepest reasoning; paid tier only
    "gemini-flash-latest":      (1.50,  7.50),  # the workhorse -- free-tier eligible
    "gemini-flash-lite-latest": (0.30,  2.50),  # cheapest paid tier; also free-tier eligible
}


def cost_usd(usage_metadata, model: str = MODEL) -> float:
    """Turn a response's `usage_metadata` into dollars -- the Gemini twin of
    ../Samples/config.py's cost_usd().

    NOTE THE FIELD NAMES: Gemini's usage object is shaped nothing like
    Anthropic's. input_tokens -> prompt_token_count, output_tokens ->
    candidates_token_count, and thinking gets its OWN counter
    (thoughts_token_count) instead of being folded into output like Claude
    does. Port a cost tracer between vendors without checking this and it
    doesn't crash -- it just quietly under-reports.
    """
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    prompt = getattr(usage_metadata, "prompt_token_count", 0) or 0
    output = getattr(usage_metadata, "candidates_token_count", 0) or 0
    thoughts = getattr(usage_metadata, "thoughts_token_count", 0) or 0
    dollars = prompt * price_in + (output + thoughts) * price_out
    return dollars / 1_000_000


def get_client() -> genai.Client:
    """Return a Gemini client.

    ONE client covers both sync and async calls -- use `client.models` for
    sync, `client.aio.models` for async (see step2_first_call.py). This is a
    real difference from ../Samples/config.py, which has to hand back a
    separate Anthropic() vs AsyncAnthropic() instance depending on the mode.

    Credentials: GEMINI_API_KEY -- get one free, no card required, at
    https://aistudio.google.com/apikey. Do not attach a billing account to
    that Google Cloud project unless you mean to: doing so silently deletes
    the free tier and every call bills from the first token.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY first (see README.md).")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# 2. THE DIAL THAT REPLACES "EFFORT" -- AND WHY IT ISN'T THE SAME SHAPE
# ---------------------------------------------------------------------------
# ../Samples steers output with `effort` (low|medium|high|xhigh|max) because
# current Claude models REJECT `temperature`. Gemini does NOT reject
# temperature -- it works exactly like every pre-2026 tutorial says (pass
# `temperature=` on GenerateContentConfig if you want it).
#
# Gemini's thinking dial is `thinking_config.thinking_budget` -- a raw TOKEN
# COUNT, not a qualitative label -- passed inside GenerateContentConfig:
#     types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=N))
# Thinking is on by default on current Flash/Pro models, same trap as Claude's
# adaptive thinking: it eats into your output budget, so give
# max_output_tokens room rather than reusing a number tuned for a non-thinking
# model.
THINKING_BUDGET = int(os.environ.get("AI_THINKING_BUDGET", "1024"))
MAX_OUTPUT_TOKENS_DEFAULT = 4096
