"""
cerebras.py
-----------
Thin wrapper around the Cerebras inference API.
Uses the OpenAI-compatible client pointed at api.cerebras.ai.
"""

import os
import time
import base64
import json
import asyncio
import collections
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env before reading any keys, so every module that imports cerebras
# (app.py, orchestrator.py, ...) gets the credentials automatically.
load_dotenv()

# --- Rate limiting -----------------------------------------------------------
# The free Cerebras tier is ~5 requests/min, 30K tokens/min. A naive 8-call
# debug round bursts straight past 5 RPM, the client back-off-retries, and you
# get 60-120s hangs + 429s. We pace ourselves with a rolling-window limiter so
# the loop NEVER 429s. Raise CEREBRAS_RPM (and concurrency) when your hackathon
# tier (100 RPM) lands — then the 5-way fan-out runs truly in parallel.
CEREBRAS_RPM             = int(os.environ.get("CEREBRAS_RPM", "5"))
CEREBRAS_MAX_CONCURRENCY = int(os.environ.get("CEREBRAS_MAX_CONCURRENCY", "5"))

_req_times = collections.deque()   # monotonic timestamps of recent requests
_rl_lock   = asyncio.Lock()
_sem       = asyncio.Semaphore(CEREBRAS_MAX_CONCURRENCY)


async def _pace():
    """Block until issuing one more request keeps us under CEREBRAS_RPM."""
    async with _rl_lock:
        while True:
            now = time.monotonic()
            while _req_times and now - _req_times[0] >= 60.0:
                _req_times.popleft()
            if len(_req_times) < CEREBRAS_RPM:
                _req_times.append(now)
                return
            await asyncio.sleep(60.0 - (now - _req_times[0]) + 0.05)


client = AsyncOpenAI(
    base_url="https://api.cerebras.ai/v1",
    api_key=os.environ.get("CEREBRAS_API_KEY", ""),
    # The pacer prevents 429s within a clean run; these retries absorb residual
    # ones (e.g. a re-run within the same minute) so an agent WAITS rather than
    # silently dropping out as an empty/culled response.
    max_retries=3,
    timeout=90.0,
)

baseline_client = AsyncOpenAI(
    base_url=os.environ.get("BASELINE_BASE_URL", "https://api.openai.com/v1"),
    api_key=os.environ.get("BASELINE_API_KEY", "sk-placeholder"),
    timeout=120.0,        # baseline GPU host is deliberately the slow one
)

# Override via CEREBRAS_MODEL in .env. Swap to "gemma-4-31b" once your
# Cerebras access (incl. multimodal for the Vision agent) lands.
MODEL          = os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b")
BASELINE_MODEL = os.environ.get("BASELINE_MODEL", "gpt-4o-mini")

# Default reasoning_effort. gpt-oss-120b accepts only low|medium|high;
# gemma-4-31b also accepts "none". Override with CEREBRAS_EFFORT in .env.
DEFAULT_EFFORT = os.environ.get("CEREBRAS_EFFORT", "low")


async def call(
    messages: list,
    schema: dict | None = None,
    effort: str | None = None,
    temperature: float = 0.4,
    use_baseline: bool = False,
) -> object:
    """
    Fire a single chat-completion request.

    messages     : OpenAI-format message list
    schema       : optional JSON Schema for strict structured output
    effort       : reasoning_effort — "none"|"low"|"medium"|"high"
                   (defaults to DEFAULT_EFFORT / $CEREBRAS_EFFORT)
    temperature  : 0.0 for Verifier, 0.7 for Code agents (diversity)
    use_baseline : route to slow GPU host for the side-by-side timer
    """
    c     = baseline_client if use_baseline else client
    model = BASELINE_MODEL  if use_baseline else MODEL

    kwargs = dict(model=model, messages=messages, temperature=temperature)

    if not use_baseline:
        kwargs["reasoning_effort"] = effort or DEFAULT_EFFORT

    if schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": schema},
        }

    # Cerebras calls go through the concurrency gate + RPM pacer; the baseline
    # (slow GPU host) is intentionally unthrottled so the comparison is honest.
    if use_baseline:
        return await c.chat.completions.create(**kwargs)

    async with _sem:
        await _pace()
        return await c.chat.completions.create(**kwargs)


def image_msg(png_path: str, prompt: str) -> list:
    """
    Build a message list containing a base64-encoded PNG.
    Call this ONLY for the Vision agent — image is sent exactly once.
    """
    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return [{"role": "user", "content": [
        {"type": "text",      "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]


def parse_json(response) -> dict:
    """Extract and parse JSON from a completion response."""
    text = (response.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def timing_summary(response) -> dict:
    """Pull latency numbers from a Cerebras response.

    Cerebras returns `time_info` as a dict, e.g.
    {queue_time, prompt_time, completion_time, total_time}. There is no
    direct TTFT / tokens-per-second field, so we derive them:
      ttft           ~= queue_time + prompt_time  (time before first token)
      tokens_per_sec  = completion_tokens / completion_time
    """
    usage = response.usage
    info  = getattr(response, "time_info", None)

    def g(key):
        if info is None:
            return None
        return info.get(key) if isinstance(info, dict) else getattr(info, key, None)

    total_time      = g("total_time")
    completion_time = g("completion_time")
    queue_time      = g("queue_time")  or 0
    prompt_time     = g("prompt_time") or 0
    completion_tok  = getattr(usage, "completion_tokens", None) if usage else None

    ttft = (queue_time + prompt_time) if info is not None else None
    tps  = (completion_tok / completion_time) if (completion_tok and completion_time) else None

    return {
        "ttft_ms":            round(ttft * 1000)            if ttft is not None            else None,
        "total_ms":           round(total_time * 1000)      if total_time is not None      else None,
        # generation-only: pure decode time + output tokens (the fair compare basis)
        "completion_ms":      round(completion_time * 1000) if completion_time is not None else None,
        "completion_tokens":  completion_tok,
        "tokens_per_sec":     round(tps)                    if tps is not None             else None,
        "total_tokens":       usage.total_tokens if usage else None,
    }
