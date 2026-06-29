"""tests/test_examples.py — every demo case must compile and FAIL as shipped.

Guards the demo data: each example's design.v must (a) compile, (b) FAIL its
self-checking testbench (the bug is present), and (c) produce a VCD. If someone
accidentally ships a fixed/passing design, this catches it.
"""
import pytest, pathlib, tempfile, shutil, sys
sys.path.insert(0, "..")
from tools import run_sim

EX = pathlib.Path(__file__).resolve().parents[1] / "examples"
CASES = sorted(
    p.name for p in EX.iterdir()
    if (p / "design.v").exists() and (p / "tb.v").exists()
)


@pytest.mark.parametrize("case", CASES)
def test_example_compiles_and_fails(case):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        shutil.copy2(EX / case / "design.v", d / "design.v")
        shutil.copy2(EX / case / "tb.v",     d / "tb.v")
        r = run_sim(str(d / "design.v"), str(d / "tb.v"), work_dir=str(d))
        assert r["stage"] == "run", f"{case} did not compile: {r['log'][:300]}"
        assert r["passed"] is False, f"{case} unexpectedly PASSES — is the bug still there?"
        assert r["vcd"], f"{case} produced no VCD"
