"""tests/test_coverage.py — toggle coverage + hole detection from a real VCD."""
import pytest, pathlib, tempfile, shutil, sys
sys.path.insert(0, "..")
from tools import run_sim
from coverage import toggle_coverage

EX = pathlib.Path(__file__).resolve().parents[1] / "examples"


def _vcd(case):
    d = pathlib.Path(tempfile.mkdtemp())
    shutil.copy2(EX / case / "design.v", d / "design.v")
    shutil.copy2(EX / case / "tb.v",     d / "tb.v")
    r = run_sim(str(d / "design.v"), str(d / "tb.v"), work_dir=str(d))
    assert r["vcd"], f"{case} produced no VCD"
    return r["vcd"]


def test_counter_count_fully_toggles():
    cov = toggle_coverage(_vcd("counter"), ["count"])
    c = cov["per_signal"]["count"]
    assert c["bits"] == 4                       # 4-bit bus
    assert c["pct"] == 100.0                    # 0..10 toggles every bit
    assert not [h for h in cov["holes"] if h["signal"] == "count"]


def test_fsm_unreached_state_is_a_hole():
    cov = toggle_coverage(_vcd("fsm"), ["state"])
    s = cov["per_signal"]["state"]
    assert s["bits"] == 2
    # wrong-transition bug: state oscillates IDLE<->RUN, never reaches DONE(2),
    # so the high bit (value-2 bit) never sets -> a coverage hole.
    holes = [h for h in cov["holes"] if h["signal"] == "state"]
    assert holes and any(h["bit"] == 1 for h in holes)
    assert s["pct"] < 100.0


def test_overall_pct_is_bounded():
    cov = toggle_coverage(_vcd("counter"))
    assert 0.0 <= cov["overall_pct"] <= 100.0
    assert cov["covered_bits"] <= cov["total_bits"]
