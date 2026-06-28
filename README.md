# ScopePilot 🔭

**Multi-agent RTL debug assistant powered by Gemma 4 on Cerebras.**

Feed it a Verilog module and its testbench. ScopePilot runs the simulation,
reads the waveform with a vision agent, debates the root cause across five
parallel code agents, verifies the winner, patches the source, and
**re-runs the simulator to prove the fix** — the oracle is always the
simulator, never another LLM.

Built for the [Cerebras × Google DeepMind Gemma 4 Hackathon](https://cerebras.ai).

---

## How it works

```
run_sim() → FAIL
    └── render_waveform()          VCD → PNG  (+ per-cycle text description)
        └── Vision agent           waveform → structured anomaly
            └── Code agents ×K     parallel hypotheses          (text only)
                └── line_check()   deterministic hallucination guard
                    └── majority   self-consistency vote
                        └── Verifier   LLM sanity check (optional)
                            └── Patch  minimal one-line diff
                                └── run_sim() → PASS ✓
```

The loop retries up to 3 times. If the patched module passes its
self-checking testbench, the bug is proven fixed — **the oracle is the
simulator, never another LLM**.

### Vision input modes

The Vision agent reads the waveform either as an **image** (`VISION_MODE=image`,
needs multimodal enabled for your Cerebras org/model) or as a **per-clock-cycle
text table** (`VISION_MODE=text`, the default — works on any model). Both come
from the same VCD we parse ourselves, so the agent sees identical information.
Flip to `image` once your multimodal access lands.

---

## Quick start

### 1. Prerequisites

```bash
# Icarus Verilog simulator
sudo apt install iverilog       # Linux
brew install icarus-verilog     # macOS
winget install IcarusVerilog    # Windows (or: choco install iverilog)

# Python dependencies
pip install -r requirements.txt
```

Verify the simulator is on PATH: `iverilog -V`.

### 2. API keys

```bash
cp .env.example .env
# edit .env and add your CEREBRAS_API_KEY
```

Get a Cerebras key at [cloud.cerebras.ai](https://cloud.cerebras.ai).

### 3. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501), pick an example project,
and click **Run debug**.

---

## Run the tests

```bash
pytest tests/ -v
```

Requires `iverilog` to be on PATH for the simulation tests.

---

## Project structure

```
fignalai/
├── app.py             Streamlit dashboard (live timeline + honest speed cards)
├── orchestrator.py    Closed-loop controller
├── agents.py          Prompts + JSON schemas (Vision, Code, Verifier, Patch)
├── cerebras.py        Cerebras API wrapper (rate limiter + timing)
├── tools.py           read_rtl · run_sim · apply_patch · apply_patches
├── render.py          VCD → PNG renderer + text description (no GTKWave)
├── checks.py          Deterministic hallucination guards
├── coverage.py        Toggle coverage + hole detection from a VCD
├── hunt.py            Coverage-driven hunt loop (flagship)
├── mutate.py          Deterministic bug-injector (proves generality)
├── requirements.txt
├── .env.example
└── examples/
    ├── counter/       Off-by-one mod-10 counter (1-line fix)
    ├── fsm/           Wrong state transition — never reaches DONE (1-line fix)
    ├── shiftreg/      Blocking '=' instead of '<=' (3-line, multi-edit fix)
    └── alu/           SUB opcode computes a+b (combinational, 1-line fix)
```

---

## Advanced capabilities (v2)

Built on top of the core loop — see `git tag v1.0-stable` for the minimal baseline.

- **Multi-edit patches** (`tools.apply_patches`): one patch can change several
  lines atomically (validate-all-then-apply), so a multi-line bug like
  blocking→non-blocking fixes in a single round.
- **Coverage-driven bug hunting** (`hunt.py` + `coverage.py`): simulate → measure
  toggle coverage → find holes (stuck bits / unreached states) → regenerate
  stimulus aimed at the holes → repeat to a threshold. A hole that *no* stimulus
  can close is a real bug → handed to the diagnose/patch loop. The stimulus
  generator is a plug-in callback; a deterministic one ships for tests, and the
  agent becomes it once on the full tier.
- **Bug injector** (`mutate.py`): deterministic mutation operators turn known-good
  RTL into a fresh bug — feed it a mutated module and watch the loop fix a bug it
  has never seen, proving it generalises rather than memorises.

**Status:** the deterministic core of all of the above is implemented and tested
(`pytest` — 34 tests, iverilog-backed). The agent-facing layers (wiring the model
into the coverage hunt, the adversarial-verifier debate, and prompt tuning) are
finalised on the full Cerebras tier + gemma-4-31b, where the 5-way fan-out and
many-call loops actually run in parallel.

---

## Why Cerebras makes this work

A full diagnose-and-patch round is K parallel hypotheses plus vision and patch
calls. The honest metric is **summed inference time** across those calls
(reported in the dashboard as *Cerebras (infer)*), versus what the same token
workload would take on a GPU at ~60 tok/s (*GPU baseline*, projected). At
~1,500 tok/s, Cerebras turns a multi-pass debate into something interactive
rather than a batch job.

The simulator (compile + run + render) is local and Cerebras can't speed it up —
that's the honest bottleneck, and it's still sub-second on these small modules.

## Configuration & rate tiers

All tunable via `.env` (see `.env.example`). The defaults are sized for the
**free Cerebras tier (~5 requests/min, 30K tokens/min)**, so the loop paces
itself to never hit a 429:

| Var | Default | Notes |
|-----|---------|-------|
| `CEREBRAS_MODEL` | `gpt-oss-120b` | swap to `gemma-4-31b` when access lands |
| `CEREBRAS_RPM` | `5` | raise to 100 on the hackathon tier for true parallelism |
| `CODE_K` | `3` | parallel code samples; `vision + K + patch = 5` fits one window |
| `ENABLE_VERIFIER` | `false` | turn on when you have RPM headroom |
| `VISION_MODE` | `text` | `image` once multimodal is enabled |
| `BASELINE_TPS` | `60` | assumed GPU tok/s for the projected baseline |

On the free tier a single round is correctness-complete but **paced** (wall-clock
includes rate-limit waiting). Raise `CEREBRAS_RPM`/`CODE_K` and the 5-way
fan-out runs truly in parallel — the *inference-time* metric already reflects
that real speed today.

---

## Example bugs included

Each bug is a single-line fix (matching the patch agent's one-line edit) and is
visually obvious in the waveform, with a self-checking testbench as the oracle.

| Module | Bug | One-line fix | Waveform anomaly |
|--------|-----|--------------|-----------------|
| `counter` | `count == 4'd10` should be `4'd9` | `4'd10 → 4'd9` | count hits 10 before wrap |
| `fsm` | `RUN` returns to `IDLE` instead of `DONE` | `state <= IDLE → DONE` | state never reaches 2 (DONE) |
| `shiftreg` | middle stage samples `din` not `q1` | `q2 <= din → q2 <= q1` | dout lags din by 2 cycles, not 3 |

---

## Tracks

- **Track 1 — Multiverse Agents**: multi-agent + multimodal (waveform vision)
- **Track 3 — Enterprise Impact**: EDA debug workflow automation

---

## License

MIT
