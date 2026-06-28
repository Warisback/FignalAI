"""
hunt.py
-------
Coverage-driven verification hunt — the flagship loop, deterministic core.

Instead of debugging one known failure, this CLOSES COVERAGE: simulate, measure
toggle coverage, find the holes, ask a stimulus generator for a new testbench
aimed at those holes, and repeat until coverage crosses a threshold (or stalls).

The generator is a plug-in callback:
    gen_stimulus(round, holes, rtl_lines) -> testbench_text

Today we test it with a plain Python generator (no LLM) so the LOOP is proven.
At kickoff the agent simply becomes `gen_stimulus`, generating directed stimulus
to hit the named holes. A hole that NO stimulus can close is a real bug — that's
the hand-off point to the diagnose/patch loop.
"""

import pathlib
from tools import run_sim
from coverage import toggle_coverage, name_bit


def hunt_coverage(
    rtl_path: str,
    tb_path: str,
    signals: list[str],
    gen_stimulus,
    threshold: float = 100.0,
    max_rounds: int = 5,
    work_dir: str = ".",
) -> dict:
    """
    Drive a coverage-closure loop.

    gen_stimulus : (round:int, holes:list, rtl_lines:list[str]) -> testbench text
    threshold    : stop once overall toggle coverage reaches this %
    max_rounds   : cap on stimulus-regeneration rounds

    Returns:
        best_pct     : float
        rounds       : int
        closed       : bool                — reached threshold
        history      : [{round, pct, holes, n_holes}]
        final_holes  : list   — holes still open at the best round (candidate bugs)
    """
    rtl_lines = pathlib.Path(rtl_path).read_text().splitlines()
    history, best_pct, best_holes = [], 0.0, []
    holes = []

    for rnd in range(1, max_rounds + 1):
        tb_text = gen_stimulus(rnd, holes, rtl_lines)
        pathlib.Path(tb_path).write_text(tb_text)

        sim = run_sim(rtl_path, tb_path, work_dir=work_dir)
        if not sim["vcd"]:
            history.append({"round": rnd, "pct": 0.0, "holes": [], "n_holes": 0,
                            "error": sim.get("log", "")[:200]})
            continue

        cov = toggle_coverage(sim["vcd"], signals)
        holes = cov["holes"]
        history.append({"round": rnd, "pct": cov["overall_pct"],
                        "holes": holes, "n_holes": len(holes)})

        if cov["overall_pct"] > best_pct:
            best_pct, best_holes = cov["overall_pct"], holes

        if cov["overall_pct"] >= threshold or not holes:
            break

    return {
        "best_pct":    best_pct,
        "rounds":      len(history),
        "closed":      best_pct >= threshold,
        "history":     history,
        "final_holes": best_holes,
    }


def holes_summary(holes: list) -> str:
    """Compact 'state[1], q[3]' style list of open holes for prompts/logs."""
    return ", ".join(name_bit(h) for h in holes) or "none"
