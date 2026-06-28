"""
agents.py
---------
Prompts, JSON schemas, and message-builders for each of the four agents.

Agent 1 — Vision   : reads the waveform PNG -> structured anomaly
Agent 2 — Code ×K  : hypothesises which line caused the anomaly
Agent 3 — Verifier : judges whether a hypothesis explains the waveform
Agent 4 — Patch    : writes the concrete line edit

All outputs use strict JSON schemas — never parse free text.
"""

import json


# ===========================================================================
# AGENT 1 — VISION
# ===========================================================================

VISION_SYSTEM = """You are a hardware verification expert reading a digital waveform image.
Your job is to identify the most obvious anomaly in the signal behaviour.

Rules:
- Describe what you see factually (signal names, values, timing).
- State what the correct behaviour should be.
- Be concise — one or two sentences per field.
- Do NOT speculate about the cause or the source code yet.
"""

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "signals_observed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Names of signals visible in the waveform",
        },
        "anomaly": {
            "type": "string",
            "description": "One sentence: what is wrong with the waveform (e.g. 'count reaches 10 before wrapping')",
        },
        "expected_behaviour": {
            "type": "string",
            "description": "One sentence: what the correct waveform should show",
        },
        "affected_signal": {
            "type": "string",
            "description": "The single signal most clearly showing the anomaly",
        },
    },
    "required": ["signals_observed", "anomaly", "expected_behaviour", "affected_signal"],
    "additionalProperties": False,
}


def vision_messages(png_path: str) -> list:
    """Build the image+prompt message list for the Vision agent (multimodal)."""
    from cerebras import image_msg
    prompt = (
        "This is a digital timing waveform from an RTL simulation. "
        "Identify the most obvious anomaly in the signal behaviour. "
        "Respond ONLY with the JSON schema — no preamble."
    )
    return image_msg(png_path, prompt)


# --- Text fallback: used when multimodal image input is not enabled ---------
# Same task as the image Vision agent, but the waveform arrives as a
# signal-transition table (see render.describe_waveform) instead of a PNG.

VISION_TEXT_SYSTEM = """You are a hardware verification expert analysing a digital waveform.
The waveform is provided as per-clock-cycle value sequences, not an image.
Your job is to identify the single most obvious anomaly in the signal behaviour.

How to read it:
- Each data signal is listed as its value on cycle 1, 2, 3, ...
- The clock and reset are normal test scaffolding. Do NOT report clock period
  or reset timing as the anomaly — focus on the DATA signals.
- Look for a data signal whose value SEQUENCE is wrong: a count that exceeds its
  modulus, a state that never reaches its final value, an output with the wrong
  delay, a signal stuck at x, etc.

Rules:
- Describe what you see factually (signal name, the offending values).
- State what the correct sequence should be.
- Be concise — one or two sentences per field.
- Do NOT speculate about the cause or the source code yet.
"""


def vision_text_messages(description: str) -> list:
    """Build the text-only message list for the Vision agent."""
    prompt = (
        "This is a digital timing waveform from an RTL simulation, given as a "
        "signal-transition table (each entry is value@time_in_ns):\n\n"
        f"{description}\n\n"
        "Identify the most obvious anomaly in the signal behaviour. "
        "Respond ONLY with the JSON schema — no preamble."
    )
    return [
        {"role": "system", "content": VISION_TEXT_SYSTEM},
        {"role": "user",   "content": prompt},
    ]


def vision_hybrid_messages(png_path: str, description: str) -> list:
    """Multimodal Vision agent: the waveform IMAGE plus the exact per-cycle table.

    The image satisfies the multimodal use-case; the table keeps the anomaly
    precise (the model reads numbers instead of guessing from pixels). Best of
    both — used when multimodal is enabled on the model/org.
    """
    import base64
    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    prompt = (
        "This is a digital timing waveform from an RTL simulation. The IMAGE shows "
        "the waveform; the table below gives the exact per-clock-cycle values for "
        "the same signals.\n\n"
        f"{description}\n\n"
        "Identify the single most obvious anomaly in the DATA signals. "
        "Respond ONLY with the JSON schema — no preamble."
    )
    return [
        {"role": "system", "content": VISION_TEXT_SYSTEM},
        {"role": "user", "content": [
            {"type": "text",      "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]},
    ]


# ===========================================================================
# AGENT 2 — CODE (called K times in parallel)
# ===========================================================================

CODE_SYSTEM = """You are an RTL debug expert.
You are given:
  1. A description of a waveform anomaly
  2. The full Verilog source of the module under test

Your job is to identify the exact line of source code that causes the anomaly.

Rules:
- Return exactly ONE hypothesis.
- You MUST quote the exact text that appears on your chosen line.
- The line_no must be the 1-indexed line number in the source.
- Be specific about the bug class.
- Do NOT suggest edits yet — just diagnose.
"""

CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "line_no": {
            "type": "integer",
            "description": "1-indexed line number in the Verilog source",
        },
        "quoted_code": {
            "type": "string",
            "description": "Exact text that appears on that line (copy-paste, no paraphrase)",
        },
        "hypothesis": {
            "type": "string",
            "description": "One sentence: why this line causes the observed anomaly",
        },
        "bug_class": {
            "type": "string",
            "enum": [
                "off_by_one",
                "missing_reset",
                "blocking_assignment",
                "wrong_comparison",
                "wrong_operator",
                "missing_condition",
                "wrong_constant",
                "other",
            ],
        },
    },
    "required": ["line_no", "quoted_code", "hypothesis", "bug_class"],
    "additionalProperties": False,
}


def code_messages(rtl_lines: list[str], anomaly: dict) -> list:
    """Build the message list for one Code agent call."""
    rtl_text = "\n".join(
        f"{i+1:3d}  {line}"
        for i, line in enumerate(rtl_lines)
    )
    content = (
        f"WAVEFORM ANOMALY:\n"
        f"  Signal:   {anomaly.get('affected_signal', 'unknown')}\n"
        f"  Problem:  {anomaly.get('anomaly', '')}\n"
        f"  Expected: {anomaly.get('expected_behaviour', '')}\n\n"
        f"RTL SOURCE:\n```verilog\n{rtl_text}\n```\n\n"
        "Identify the exact line causing this anomaly. "
        "Respond ONLY with the JSON schema."
    )
    return [
        {"role": "system", "content": CODE_SYSTEM},
        {"role": "user",   "content": content},
    ]


# ===========================================================================
# AGENT 3 — VERIFIER
# ===========================================================================

VERIFIER_SYSTEM = """You are a senior RTL verification engineer.
You are given:
  1. A waveform anomaly description
  2. A hypothesis about which line of code causes it
  3. The full RTL source

Your job is to judge whether the hypothesis actually explains the observed anomaly.
Be strict — only accept hypotheses that causally connect the cited code to the waveform behaviour.
"""

VERIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["accept", "reject"],
        },
        "confidence": {
            "type": "integer",
            "description": "0–100 confidence that this hypothesis is correct",
        },
        "reason": {
            "type": "string",
            "description": "One sentence explaining the verdict",
        },
    },
    "required": ["verdict", "confidence", "reason"],
    "additionalProperties": False,
}


def verifier_messages(hypothesis: dict, anomaly: dict, rtl_lines: list[str]) -> list:
    """Build the message list for one Verifier call."""
    rtl_text = "\n".join(
        f"{i+1:3d}  {line}"
        for i, line in enumerate(rtl_lines)
    )
    content = (
        f"WAVEFORM ANOMALY:\n"
        f"  {anomaly.get('anomaly', '')}\n\n"
        f"HYPOTHESIS:\n"
        f"  Line {hypothesis['line_no']}: {hypothesis['quoted_code']}\n"
        f"  Claim: {hypothesis['hypothesis']}\n\n"
        f"RTL SOURCE:\n```verilog\n{rtl_text}\n```\n\n"
        "Does this hypothesis causally explain the observed anomaly? "
        "Respond ONLY with the JSON schema."
    )
    return [
        {"role": "system", "content": VERIFIER_SYSTEM},
        {"role": "user",   "content": content},
    ]


# ===========================================================================
# AGENT 4 — PATCH
# ===========================================================================

PATCH_SYSTEM = """You are an RTL bug-fix engineer.
You are given a verified hypothesis about the bug and the full RTL source.
Produce the minimal SET of line edits that together fix the bug.

Rules:
- Prefer the smallest change. Most bugs need ONE edit; some need a few — e.g. a
  blocking '=' that must become non-blocking '<=' across several lines.
- Each edit's 'before' must be an exact substring that appears on its line_no
  (copy it verbatim, not a paraphrase).
- 'after' is the replacement for that substring.
- Include every edit required for the fixed module to pass its testbench.
"""

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "description": "One or more line edits that together fix the bug",
            "items": {
                "type": "object",
                "properties": {
                    "line_no": {"type": "integer", "description": "1-indexed line to edit"},
                    "before":  {"type": "string",  "description": "Exact substring on that line to replace"},
                    "after":   {"type": "string",  "description": "Replacement substring"},
                },
                "required": ["line_no", "before", "after"],
                "additionalProperties": False,
            },
        },
        "rationale": {
            "type": "string",
            "description": "One sentence: why these changes fix the bug",
        },
    },
    "required": ["edits", "rationale"],
    "additionalProperties": False,
}


def patch_messages(hypothesis: dict, rtl_lines: list[str]) -> list:
    """Build the message list for the Patch agent."""
    rtl_text = "\n".join(
        f"{i+1:3d}  {line}"
        for i, line in enumerate(rtl_lines)
    )
    content = (
        f"BUG LOCATION:\n"
        f"  Line {hypothesis['line_no']}: {hypothesis['quoted_code']}\n"
        f"  Bug class: {hypothesis.get('bug_class', 'unknown')}\n"
        f"  Hypothesis: {hypothesis['hypothesis']}\n\n"
        f"RTL SOURCE:\n```verilog\n{rtl_text}\n```\n\n"
        "Produce the minimal set of edits that fixes the bug. "
        "Respond ONLY with the JSON schema."
    )
    return [
        {"role": "system", "content": PATCH_SYSTEM},
        {"role": "user",   "content": content},
    ]
