"""
orchestrator.py
---------------
The closed-loop controller that ties everything together.

Flow per round:
  1. run_sim()          — simulate; if PASS we're done
  2. render_waveform()  — VCD → PNG
  3. Vision agent       — image → structured anomaly  (1 image call, image sent ONCE)
  4. Code agents ×K     — parallel hypotheses          (text only from here on)
  5. Deterministic cull — line_check()
  6. Majority vote      — pick the most common answer
  7. Verifier           — LLM sanity check on winner
  8. Patch agent        — produce the diff
  9. apply_patch()      — edit the file
  → loop back to step 1 (max 3 rounds)
"""

import asyncio
import os
import time
from typing import AsyncIterator

from cerebras import call, parse_json, timing_summary
from tools    import read_rtl, run_sim, apply_patch, apply_patches, restore_backup
from render   import render_waveform, describe_waveform
from checks   import line_check, patch_check, majority_vote
import agents

# "text"   — signal-transition table only (works on any model)
# "image"  — the waveform PNG only (requires multimodal)
# "hybrid" — PNG + the exact per-cycle table (multimodal AND precise) [recommended]
VISION_MODE = os.environ.get("VISION_MODE", "text")

# Pipeline shape, tuned to fit the free tier's 5 requests/min:
#   vision(1) + code(CODE_K) + patch(1) = 5 when CODE_K=3, verifier off.
# Bump CODE_K and enable the verifier when your 100-RPM tier lands.
CODE_K          = int(os.environ.get("CODE_K", "3"))
ENABLE_VERIFIER = os.environ.get("ENABLE_VERIFIER", "false").lower() in ("1", "true", "yes")
# Some non-zero temperature gives the K samples diversity for the majority vote,
# but too high makes gpt-oss-120b ramble and return empty content. 0.5 is a
# reliable middle ground for structured output.
CODE_TEMPERATURE = float(os.environ.get("CODE_TEMPERATURE", "0.5"))

# Assumed GPU throughput (tokens/sec) for the PROJECTED side-by-side baseline.
# We compare actual Cerebras inference time against what the same token workload
# would take on a GPU at this rate. ~50-80 tok/s is realistic for a ~100B model.
BASELINE_TPS = float(os.environ.get("BASELINE_TPS", "60"))


# ---------------------------------------------------------------------------
# Event yielded to the UI for the live agent stream
# ---------------------------------------------------------------------------

class Event:
    def __init__(self, kind: str, **kwargs):
        self.kind = kind      # "sim" | "render" | "vision" | "code" | "verifier" | "patch" | "done" | "error"
        self.data = kwargs

    def __repr__(self):
        return f"Event({self.kind}, {self.data})"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def debug(
    rtl_path:   str,
    tb_path:    str,
    signals:    list[str],
    max_rounds: int = 3,
    K:          int = CODE_K,
    work_dir:   str = ".",
) -> AsyncIterator[Event]:
    """
    Run the full debug loop, yielding Event objects as each step completes.
    The UI consumes these to update the dashboard in real time.

    Parameters
    ----------
    rtl_path   : path to the buggy Verilog module
    tb_path    : path to the self-checking testbench
    signals    : list of signal names to plot in the waveform
    max_rounds : maximum patch-and-retry iterations
    K          : number of parallel Code agent samples
    """
    total_start  = time.monotonic()
    timing_log   = []     # collect per-step timing for the side-by-side panel
    gen_ms       = 0.0    # summed GENERATION time only (completion_time), across
                          # all agent calls — the basis for the gen-vs-gen compare
    out_tokens   = 0      # summed completion (output) tokens generated

    def _agg(resp):
        """Accumulate this call's generation time + output tokens; return its timing."""
        nonlocal gen_ms, out_tokens
        ts = timing_summary(resp)
        gen_ms     += ts["completion_ms"] or 0
        out_tokens += ts["completion_tokens"] or 0
        return ts

    def _speed():
        """Generation-vs-generation speed (identical scope on both sides).

        cerebras_gen_ms : measured time Cerebras spent GENERATING the run's output
                          tokens (sum of per-call completion_time).
        baseline_gen_ms : ESTIMATE — time to generate the SAME output tokens on a
                          GPU at BASELINE_TPS tok/s. Derived, not measured.
        Neither includes queue/prompt/sim/render — that's the Total-cycle metric.
        """
        tps = round(out_tokens / (gen_ms / 1000)) if gen_ms else None
        return dict(
            cerebras_gen_ms=round(gen_ms),
            out_tokens=out_tokens,
            tps=tps,
            baseline_gen_ms=round(out_tokens / BASELINE_TPS * 1000) if out_tokens else None,
        )

    for rnd in range(max_rounds):

        # ------------------------------------------------------------------
        # STEP 1 — simulate
        # ------------------------------------------------------------------
        yield Event("sim", round=rnd+1, status="running")
        t0  = time.monotonic()
        sim = run_sim(rtl_path, tb_path, work_dir=work_dir)
        yield Event("sim", round=rnd+1, status="done",
                    passed=sim["passed"], log=sim["log"],
                    elapsed_ms=round((time.monotonic()-t0)*1000))

        if sim["passed"]:
            yield Event("done",
                        fixed=True,
                        round=rnd+1,
                        total_ms=round((time.monotonic()-total_start)*1000),
                        **_speed())
            return

        if not sim["vcd"]:
            yield Event("error", message="Simulation produced no VCD — check compile errors",
                        log=sim["log"])
            return

        # ------------------------------------------------------------------
        # STEP 2 — render
        # ------------------------------------------------------------------
        yield Event("render", status="running")
        t0  = time.monotonic()
        png = render_waveform(
            sim["vcd"], signals,
            out_path=os.path.join(work_dir, f"waveform_round{rnd+1}.png"),
            title=f"Round {rnd+1} — before patch",
        )
        yield Event("render", status="done",
                    png=png,
                    elapsed_ms=round((time.monotonic()-t0)*1000))

        # ------------------------------------------------------------------
        # STEP 3 — Vision agent (THE ONLY IMAGE CALL, when in image mode)
        # ------------------------------------------------------------------
        yield Event("vision", status="running", mode=VISION_MODE)
        t0 = time.monotonic()
        if VISION_MODE == "image":
            vision_msgs = agents.vision_messages(png)
        elif VISION_MODE == "hybrid":
            vision_msgs = agents.vision_hybrid_messages(
                png, describe_waveform(sim["vcd"], signals)
            )
        else:
            vision_msgs = agents.vision_text_messages(
                describe_waveform(sim["vcd"], signals)
            )
        v_resp  = await call(
            vision_msgs,
            schema=agents.VISION_SCHEMA,
            temperature=0.0,   # vision should be deterministic
        )
        anomaly = parse_json(v_resp)
        v_time  = _agg(v_resp)
        timing_log.append(("vision", v_time))
        yield Event("vision", status="done",
                    anomaly=anomaly,
                    timing=v_time,
                    elapsed_ms=round((time.monotonic()-t0)*1000),
                    **_speed())   # live running speed snapshot for the stat cards

        # ------------------------------------------------------------------
        # STEP 4 — K parallel Code agents (text only from here)
        # ------------------------------------------------------------------
        rtl_lines = read_rtl(rtl_path)

        yield Event("code", status="running", k=K)
        t0    = time.monotonic()
        tasks = [
            call(
                agents.code_messages(rtl_lines, anomaly),
                schema=agents.CODE_SCHEMA,
                temperature=CODE_TEMPERATURE,   # diversity for the majority vote
            )
            for _ in range(K)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        hypotheses = []
        code_events = []
        for idx, r in enumerate(responses):
            if isinstance(r, Exception):
                code_events.append({"idx": idx+1, "status": "error", "msg": str(r)})
                continue
            _agg(r)   # count this sample's real inference time + tokens
            try:
                h = parse_json(r)
            except Exception as e:
                code_events.append({"idx": idx+1, "status": "parse_error", "msg": str(e)})
                continue

            # ------ Guard 1: deterministic line-check ------
            passed_check = line_check(rtl_lines, h["line_no"], h["quoted_code"])
            code_events.append({
                "idx":         idx+1,
                "line_no":     h["line_no"],
                "quoted_code": h["quoted_code"],
                "bug_class":   h.get("bug_class"),
                "kept":        passed_check,
            })
            if passed_check:
                hypotheses.append(h)

        yield Event("code", status="done",
                    details=code_events,
                    kept=len(hypotheses),
                    elapsed_ms=round((time.monotonic()-t0)*1000),
                    **_speed())

        if not hypotheses:
            yield Event("error",
                        message="All hypotheses failed the deterministic line-check. "
                                "The model may have hallucinated all line numbers.")
            return

        # ------------------------------------------------------------------
        # STEP 5 — Majority vote
        # ------------------------------------------------------------------
        winner = majority_vote(hypotheses)
        if winner is None:
            # No majority — fall back to the first kept hypothesis
            winner = hypotheses[0]
            yield Event("vote", result="no_majority", fallback=winner)
        else:
            yield Event("vote", result="majority", winner=winner,
                        count=sum(
                            1 for h in hypotheses
                            if h["line_no"] == winner["line_no"]
                        ))

        # ------------------------------------------------------------------
        # STEP 6 — Verifier (optional; the simulator re-run is the real oracle)
        # ------------------------------------------------------------------
        if ENABLE_VERIFIER:
            yield Event("verifier", status="running")
            t0 = time.monotonic()
            v2_resp  = await call(
                agents.verifier_messages(winner, anomaly, rtl_lines),
                schema=agents.VERIFIER_SCHEMA,
                temperature=0.0,
            )
            verdict = parse_json(v2_resp)
            v2_time = _agg(v2_resp)
            timing_log.append(("verifier", v2_time))
            yield Event("verifier", status="done",
                        verdict=verdict,
                        timing=v2_time,
                        elapsed_ms=round((time.monotonic()-t0)*1000),
                        **_speed())

            # The verifier is ADVISORY — it surfaces doubt but never hard-aborts.
            # The simulator re-run (step 8) is the ground-truth oracle: if the
            # patch makes the testbench PASS, the hypothesis was right regardless
            # of what the verifier (anchored to the vision agent's prose) thought.
            # We still try the patch; if it doesn't pass, the loop re-diagnoses.

        # ------------------------------------------------------------------
        # STEP 7 — Patch agent
        # ------------------------------------------------------------------
        yield Event("patch", status="running")
        t0 = time.monotonic()
        p_resp = await call(
            agents.patch_messages(winner, rtl_lines),
            schema=agents.PATCH_SCHEMA,
            temperature=0.0,
        )
        patch  = parse_json(p_resp)
        p_time = _agg(p_resp)
        timing_log.append(("patch", p_time))

        edits = patch.get("edits", [])

        # Guard before writing: every edit's 'before' must be on its line
        bad = next(
            (e for e in edits if not patch_check(rtl_lines, e["line_no"], e["before"])),
            None,
        )
        if not edits or bad is not None:
            msg = ("Patch produced no edits."
                   if not edits else
                   f"Patch safety check failed: '{bad['before']}' not found on line {bad['line_no']}.")
            yield Event("error", message=msg, patch=patch)
            return

        result = apply_patches(rtl_path, edits)
        yield Event("patch", status="done",
                    patch=patch,
                    edits=edits,
                    result=result,
                    timing=p_time,
                    elapsed_ms=round((time.monotonic()-t0)*1000),
                    **_speed())

        if not result["success"]:
            yield Event("error", message=result["message"])
            return

        # loop back to step 1 — the simulator is the oracle

    # max_rounds exhausted without PASS
    yield Event("done",
                fixed=False,
                round=max_rounds,
                total_ms=round((time.monotonic()-total_start)*1000),
                message="Max rounds reached without a passing simulation.",
                **_speed())
