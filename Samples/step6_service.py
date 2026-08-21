"""
Step 6 Capstone -- serve the agent as a real service.

This file now delivers every bullet the Step 6 capstone promises:
  6.1 observability: a request id, a span-style trace line, tokens AND cost
  6.2 cost control: prompt caching (in step3_agent) + a right-sized model
  6.3 guardrails: input validation, output filtering
  6.4 security: API-key auth, an injection heuristic, least-privilege framing
  6.5 serving: async, a timeout, AND a streaming (SSE) endpoint

Governance -- redaction, audit trail, approval gates -- is module 6.7 and lives
in step6b_governance.py.

Run:   uv run --with "fastapi,uvicorn,anthropic" uvicorn step6_service:app --reload
Test:  $env:API_KEYS = "dev-key-123"        # then, in another terminal:
       curl -s localhost:8000/ask -H "content-type: application/json" \
            -H "x-api-key: dev-key-123" \
            -d '{"question":"Total residents across Dorm A and B?"}'
       curl -N localhost:8000/ask/stream -H "content-type: application/json" \
            -H "x-api-key: dev-key-123" \
            -d '{"question":"What are the quiet hours?"}'
Deps:  fastapi uvicorn anthropic
Env:   ANTHROPIC_API_KEY, API_KEYS (comma-separated)
"""
import asyncio
import json
import os
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import MODEL, cost_usd, get_client
from step3_agent import run as agent

app = FastAPI(title="Dorm Agent Service")
client = get_client(async_=True)

# 6.4 a crude injection heuristic -- real systems need far more (see OWASP LLM
# Top 10). Understand what this does NOT do: it cannot catch injection that
# arrives inside a RETRIEVED DOCUMENT rather than the user's message, which is
# the attack that actually matters for agents. Treat tool output as untrusted.
BLOCKLIST = ("ignore previous", "ignore all previous", "system prompt",
             "api key", "reveal your", "disregard the above")

TIMEOUT_SECONDS = 60


# --- 6.4  authentication ----------------------------------------------------
def require_api_key(x_api_key: str = Header(default="")) -> str:
    """The cheapest thing that turns a demo into a service.

    An agent endpoint with no auth is a bill anyone on the internet can run up
    on your behalf -- the LLM equivalent of an open relay.
    """
    allowed = {k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()}
    if not allowed:
        raise HTTPException(503, "server misconfigured: API_KEYS is not set")
    if x_api_key not in allowed:
        raise HTTPException(401, "missing or invalid x-api-key header")
    return x_api_key


class Ask(BaseModel):                                   # 6.3 input validation (1.3)
    question: str = Field(min_length=3, max_length=500)


class Answer(BaseModel):
    answer: str
    request_id: str
    usd: float
    ms: int


# --- 6.1  the tracer --------------------------------------------------------
class Trace:
    """One request's worth of observability.

    This is a hand-rolled span. Langfuse / LangSmith / Helicone give you this
    plus a UI plus retention -- but they all log these same fields, so build it
    once by hand and you will know what their dashboards are actually showing
    you.
    """

    def __init__(self, route: str):
        self.request_id = str(uuid.uuid4())[:8]
        self.route = route
        self.started = time.perf_counter()
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.cached_in = 0
        self.usd = 0.0

    def record(self, usage) -> None:
        """Called once per model call inside the agent loop."""
        self.calls += 1
        self.tokens_in += getattr(usage, "input_tokens", 0) or 0
        self.tokens_out += getattr(usage, "output_tokens", 0) or 0
        self.cached_in += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.usd += cost_usd(usage, MODEL)

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def emit(self, outcome: str) -> None:
        # Structured (JSON) log lines, not prose. The whole point is that a
        # machine can aggregate these -- "p95 latency", "cost per question",
        # "which route burns the most tokens" are all just queries over this.
        print(json.dumps({
            "request_id": self.request_id,
            "route": self.route,
            "outcome": outcome,
            "model": MODEL,
            "model_calls": self.calls,          # note: >1 per question. That's the loop.
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_cached": self.cached_in,
            "usd": round(self.usd, 6),
            "ms": self.ms,
        }), flush=True)


def guard_input(question: str) -> None:
    if any(bad in question.lower() for bad in BLOCKLIST):    # 6.4
        raise HTTPException(400, "request rejected by guardrail")


def guard_output(text: str) -> str:
    if "ANTHROPIC_API_KEY" in text or "sk-ant" in text:      # 6.3 output filter
        return "[response redacted by output guardrail]"
    return text


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/ask", response_model=Answer)
async def ask(body: Ask, _key: str = Depends(require_api_key)) -> Answer:
    trace = Trace("/ask")
    guard_input(body.question)

    try:
        # 6.5 the agent is async now, so no thread pool -- just await it with a
        # wall-clock cap. An agent loop with no timeout can spin until MAX_STEPS
        # while the caller's connection sits open.
        text = await asyncio.wait_for(
            agent(body.question, on_usage=trace.record), timeout=TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        trace.emit("timeout")
        raise HTTPException(504, "agent timed out")
    except Exception:
        trace.emit("error")
        raise HTTPException(500, "agent failed")

    trace.emit("ok")
    return Answer(answer=guard_output(text), request_id=trace.request_id,
                  usd=round(trace.usd, 6), ms=trace.ms)


@app.post("/ask/stream")
async def ask_stream(body: Ask, _key: str = Depends(require_api_key)):
    """6.5 Server-Sent Events -- the streaming shape a real UI consumes.

    Why this matters: an agent takes seconds. Without streaming the user stares
    at a spinner and your p95 latency IS your user experience. SSE is a plain
    HTTP response that never closes, with `data: ...` lines -- no WebSocket
    machinery needed for one-way output.

    Note this streams a SINGLE model answer, not the whole tool loop. Streaming
    an agent loop means choosing what the user sees: tokens, or tool-by-tool
    progress. That is a product decision, not a technical one.
    """
    trace = Trace("/ask/stream")
    guard_input(body.question)

    async def events():
        try:
            async with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                system="You are a dormitory operations assistant. Be concise.",
                messages=[{"role": "user", "content": body.question}],
            ) as stream:
                async for chunk in stream.text_stream:
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
                final = await stream.get_final_message()
            trace.record(final.usage)
            trace.emit("ok")
            yield f"data: {json.dumps({'done': True, 'usd': round(trace.usd, 6), 'request_id': trace.request_id})}\n\n"
        except Exception as exc:
            trace.emit("error")
            # An error mid-stream cannot become a 500 -- the headers are long
            # gone. You have to deliver failures IN the stream.
            yield f"data: {json.dumps({'error': type(exc).__name__})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"cache-control": "no-cache",
                                      "x-request-id": trace.request_id})
