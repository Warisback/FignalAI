"""
hunt_agent.py
-------------
The agent layer for the coverage-driven hunt (hunt.py).

The model only writes STIMULUS (what to drive); a deterministic template wraps it
into a valid, compilable testbench. This keeps the hard, error-prone scaffolding
(port wiring, clock, $dumpvars, $finish) correct and constrains the agent to the
part it's good at: choosing input values that exercise the uncovered bits.

  parse_ports(rtl)            -> (module_name, [{name,dir,width}])
  build_tb(module, ports, …)  -> testbench text with the stimulus spliced in
  agent_generator(...)        -> a gen_stimulus(round, holes, rtl_lines) callback
                                 for hunt.hunt_coverage()
"""

import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
_client = OpenAI(base_url="https://api.cerebras.ai/v1",
                 api_key=os.environ.get("CEREBRAS_API_KEY", ""))
_MODEL  = os.environ.get("CEREBRAS_MODEL", "gemma-4-31b")
_EFFORT = os.environ.get("CEREBRAS_EFFORT", "none")


# ---------------------------------------------------------------------------
# RTL port parsing (ANSI-style module headers)
# ---------------------------------------------------------------------------

def parse_ports(rtl_text: str):
    m = re.search(r"module\s+(\w+)\s*\((.*?)\)\s*;", rtl_text, re.S)
    if not m:
        return None, []
    name, body = m.group(1), m.group(2)
    ports = []
    for d, hi, lo, nm in re.findall(
        r"(input|output|inout)\s+(?:reg\s+|wire\s+)?(?:\[(\d+):(\d+)\]\s*)?(\w+)", body
    ):
        width = (int(hi) - int(lo) + 1) if hi != "" else 1
        ports.append({"name": nm, "dir": d, "width": width})
    return name, ports


def _clk_name(ports):
    for p in ports:
        if p["dir"] == "input" and "clk" in p["name"].lower():
            return p["name"]
    return None


# ---------------------------------------------------------------------------
# Deterministic testbench template
# ---------------------------------------------------------------------------

def drivable_inputs(ports, clk=None):
    clk = clk or _clk_name(ports)
    return [p for p in ports if p["dir"] == "input" and p["name"] != clk]


def build_tb(module: str, ports: list, vectors: list) -> str:
    """Build a testbench that applies each input VECTOR for one clock cycle.

    vectors : list of value-lists, each in drivable-input order. Applying one
    vector per @(posedge clk) guarantees every vector is actually sampled — the
    agent only chooses values, never timing.
    """
    clk   = _clk_name(ports)
    drive = drivable_inputs(ports, clk)
    decls, conns = [], []
    for p in ports:
        w = "" if p["width"] == 1 else f"[{p['width']-1}:0] "
        kind = "reg " if p["dir"] == "input" else "wire "
        decls.append(f"  {kind}{w}{p['name']};")
        conns.append(f".{p['name']}({p['name']})")
    clk_decl = f"  always #5 {clk} = ~{clk};" if clk else ""
    step = f"@(posedge {clk}); #1;" if clk else "#2;"

    lines = []
    if clk:
        lines.append(f"    {clk} = 0;")
    for vec in vectors:
        for p, val in zip(drive, vec):
            mask = (1 << p["width"]) - 1
            lines.append(f"    {p['name']} = {p['width']}'d{int(val) & mask};")
        lines.append(f"    {step}")
    body = "\n".join(lines)

    return f"""`timescale 1ns/1ps
module tb;
{chr(10).join(decls)}
  {module} dut({", ".join(conns)});
  initial begin $dumpfile("dump.vcd"); $dumpvars(0, tb); end
{clk_decl}
  initial begin
{body}
    #20;
    $display("RESULT: PASS");
    $finish;
  end
endmodule
"""


def _sweep_vectors(drive, cap=64):
    """Deterministic fallback: exhaustively sweep small input spaces."""
    total = 1
    for p in drive:
        total *= (1 << p["width"])
        if total > cap:
            break
    vecs = []
    if total <= cap:
        from itertools import product
        for combo in product(*[range(1 << p["width"]) for p in drive]):
            vecs.append(list(combo))
    else:  # too big — random-ish deterministic spread
        for i in range(cap):
            vecs.append([(i * 2654435761 >> (3 * j)) & ((1 << p["width"]) - 1)
                         for j, p in enumerate(drive)])
    return vecs


# ---------------------------------------------------------------------------
# Stimulus agent
# ---------------------------------------------------------------------------

STIMULUS_SCHEMA = {
    "type": "object",
    "properties": {
        "vectors": {
            "type": "array",
            "description": "Input vectors; each is a list of decimal values, one per "
                           "drivable input in the given order. One vector per clock cycle.",
            "items": {"type": "array", "items": {"type": "integer"}},
        }
    },
    "required": ["vectors"],
    "additionalProperties": False,
}

STIMULUS_SYSTEM = """You choose INPUT VECTORS to maximise toggle coverage of an RTL module.
Each vector is a list of decimal values, one per drivable input (in the stated
order). Each vector is applied for exactly one clock cycle, so to make a bit take
both 0 and 1 you must include vectors that set it high AND vectors that set it low.
Cover every listed hole. Return ONLY the JSON schema (a list of integer lists).
"""


def _agent_vectors(module, ports, holes, round_no):
    drive = drivable_inputs(ports)
    order = ", ".join(f"{p['name']}({p['width']}b)" for p in drive)
    hole_desc = ", ".join(
        h["signal"] if h["bit"] is None else f"{h['signal']}[{h['bit']}]" for h in holes
    ) or "none yet — exercise the full input range"
    user = (f"Module {module}. Drivable inputs in order: {order}.\n"
            f"Currently uncovered (never toggled): {hole_desc}.\n"
            f"Round {round_no}: give input vectors that toggle every uncovered bit "
            f"(include both extremes for each). Example for inputs (a(2b)): "
            f"[[0],[1],[2],[3]]. Respond ONLY with the JSON schema.")
    r = _client.chat.completions.create(
        model=_MODEL, reasoning_effort=_EFFORT,
        messages=[{"role": "system", "content": STIMULUS_SYSTEM},
                  {"role": "user", "content": user}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "out", "strict": True, "schema": STIMULUS_SCHEMA}},
        max_tokens=600,
    )
    return json.loads(r.choices[0].message.content or "{}").get("vectors", [])


def agent_generator(module: str, ports: list, fallback_sweep: bool = True):
    """Return a gen_stimulus(round, holes, rtl_lines) callback for hunt_coverage().

    Uses the model to pick input vectors; if it returns nothing usable, falls back
    to a deterministic sweep so the hunt always makes progress.
    """
    drive = drivable_inputs(ports)

    def gen_stimulus(round_no, holes, rtl_lines):
        vectors = []
        try:
            vectors = [v for v in _agent_vectors(module, ports, holes, round_no)
                       if isinstance(v, list) and len(v) == len(drive)]
        except Exception:
            vectors = []
        if not vectors and fallback_sweep:
            vectors = _sweep_vectors(drive)
        return build_tb(module, ports, vectors)

    return gen_stimulus
