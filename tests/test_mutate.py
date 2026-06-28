"""tests/test_mutate.py — the bug-injector must turn GOOD RTL into a failing bug.

Proves generality: a correct module + an injected mutation = a module that fails
its testbench, i.e. a fresh bug for FignalAI to find.
"""
import pytest, pathlib, tempfile, shutil, sys
sys.path.insert(0, "..")
from tools import run_sim
from mutate import inject, OPERATORS

# A CORRECT mod-10 counter (wraps at 9). Its testbench flags count > 9.
GOLDEN_COUNTER = """`timescale 1ns/1ps
module counter(input clk, input rst_n, output reg [3:0] count);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)              count <= 4'd0;
        else if (count == 4'd9)  count <= 4'd0;
        else                     count <= count + 4'd1;
    end
endmodule
"""
TB = pathlib.Path(__file__).resolve().parents[1] / "examples" / "counter" / "tb.v"


@pytest.fixture
def work():
    with tempfile.TemporaryDirectory() as d:
        yield pathlib.Path(d)


def test_golden_passes_then_injection_breaks_it(work):
    shutil.copy2(TB, work / "tb.v")
    (work / "design.v").write_text(GOLDEN_COUNTER)
    # golden is correct -> PASS
    assert run_sim(str(work / "design.v"), str(work / "tb.v"), work_dir=str(work))["passed"] is True

    # inject an off-by-one -> should now FAIL
    mutated, m = inject(GOLDEN_COUNTER.splitlines(), prefer="off_by_one")
    assert m is not None and m["op"] == "off_by_one"
    (work / "design.v").write_text("\n".join(mutated) + "\n")
    assert run_sim(str(work / "design.v"), str(work / "tb.v"), work_dir=str(work))["passed"] is False


def test_inject_returns_reversible_record(work):
    mutated, m = inject(GOLDEN_COUNTER.splitlines(), prefer="off_by_one")
    # the recorded edit must actually describe the change that was made
    assert m["before"] in GOLDEN_COUNTER
    assert m["after"] in "\n".join(mutated)


def test_no_applicable_mutation_returns_none():
    plain = ["module x;", "  // nothing to mutate here", "endmodule"]
    mutated, m = inject(plain)
    assert mutated is None and m is None
