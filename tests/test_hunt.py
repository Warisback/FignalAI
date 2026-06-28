"""tests/test_hunt.py — the coverage-driven hunt loop (deterministic generator).

Proves the loop mechanics without an LLM:
  1. on a correct module, regenerated stimulus CLOSES coverage to threshold;
  2. on a buggy module, a hole NO stimulus can close persists -> a real bug.
"""
import pathlib, sys
sys.path.insert(0, "..")
from hunt import hunt_coverage

EX = pathlib.Path(__file__).resolve().parents[1] / "examples"

REG4 = """`timescale 1ns/1ps
module reg4(input clk, input [3:0] din, output reg [3:0] q);
    always @(posedge clk) q <= din;
endmodule
"""


def gen_reg4(rnd, holes, rtl_lines):
    # round 1 under-drives (din stuck at 0); round 2+ exercises all bits
    drive = "din = 4'd0;" if rnd < 2 else "din = 4'd15; @(posedge clk); #1; din = 4'd0;"
    return f"""`timescale 1ns/1ps
module tb;
  reg clk = 0; reg [3:0] din; wire [3:0] q;
  reg4 dut(.clk(clk), .din(din), .q(q));
  initial begin $dumpfile("dump.vcd"); $dumpvars(0, tb); end
  always #5 clk = ~clk;
  initial begin
    {drive}
    @(posedge clk); #1; @(posedge clk); #1;
    $display("RESULT: PASS"); $finish;
  end
endmodule
"""


def gen_fsm(rnd, holes, rtl_lines):
    cycles = 6 * rnd   # escalate stimulus each round — still can't reach DONE
    return f"""`timescale 1ns/1ps
module tb;
  reg clk = 0, rst_n = 0, go = 0; wire [1:0] state; integer i;
  fsm dut(.clk(clk), .rst_n(rst_n), .go(go), .state(state));
  initial begin $dumpfile("dump.vcd"); $dumpvars(0, tb); end
  always #5 clk = ~clk;
  initial begin
    #12 rst_n = 1;
    for (i = 0; i < {cycles}; i = i + 1) begin
      go = 1; @(posedge clk); #1; go = 0; @(posedge clk); #1;
    end
    $display("RESULT: PASS"); $finish;
  end
endmodule
"""


def test_hunt_closes_coverage(tmp_path):
    rtl = tmp_path / "design.v"; rtl.write_text(REG4)
    res = hunt_coverage(str(rtl), str(tmp_path / "tb.v"), ["q"],
                        gen_reg4, threshold=100.0, max_rounds=4, work_dir=str(tmp_path))
    assert res["closed"] is True
    assert res["best_pct"] == 100.0
    assert res["rounds"] <= 2


def test_hunt_persistent_hole_is_a_bug(tmp_path):
    rtl = tmp_path / "design.v"; rtl.write_text((EX / "fsm" / "design.v").read_text())
    res = hunt_coverage(str(rtl), str(tmp_path / "tb.v"), ["state"],
                        gen_fsm, threshold=100.0, max_rounds=3, work_dir=str(tmp_path))
    assert res["closed"] is False     # no stimulus can close it
    assert any(h["signal"] == "state" and h["bit"] == 1 for h in res["final_holes"])
