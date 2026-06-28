"""tests/test_tools.py — simulation + patching tools"""
import pytest, pathlib, tempfile, sys
sys.path.insert(0, "..")
from tools import read_rtl, run_sim, apply_patch, apply_patches, restore_backup

RTL_SRC = """`timescale 1ns/1ps
module simple(input clk, output reg q);
    always @(posedge clk) q <= ~q;
endmodule
"""

TB_PASS = """`timescale 1ns/1ps
module tb;
    reg clk = 0;
    wire q;
    simple dut(.clk(clk), .q(q));
    initial begin $dumpfile("dump.vcd"); $dumpvars(0,tb); end
    always #5 clk = ~clk;
    initial begin #100; $display("RESULT: PASS"); $finish; end
endmodule
"""

TB_FAIL = """`timescale 1ns/1ps
module tb;
    reg clk = 0;
    wire q;
    simple dut(.clk(clk), .q(q));
    initial begin $dumpfile("dump.vcd"); $dumpvars(0,tb); end
    always #5 clk = ~clk;
    initial begin #100; $display("RESULT: FAIL (1 errors)"); $finish; end
endmodule
"""

@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield pathlib.Path(d)

def test_run_sim_pass(tmpdir):
    rtl = tmpdir / "design.v"; rtl.write_text(RTL_SRC)
    tb  = tmpdir / "tb.v";     tb.write_text(TB_PASS)
    r   = run_sim(str(rtl), str(tb), work_dir=str(tmpdir))
    assert r["passed"] is True

def test_run_sim_fail(tmpdir):
    rtl = tmpdir / "design.v"; rtl.write_text(RTL_SRC)
    tb  = tmpdir / "tb.v";     tb.write_text(TB_FAIL)
    r   = run_sim(str(rtl), str(tb), work_dir=str(tmpdir))
    assert r["passed"] is False

def test_apply_patch_success(tmpdir):
    f = tmpdir / "design.v"
    f.write_text("line1\nif (x == 10) y <= 0;\nline3\n")
    r = apply_patch(str(f), 2, "== 10", "== 9")
    assert r["success"] is True
    assert "== 9" in f.read_text()

def test_apply_patch_safety_block(tmpdir):
    f = tmpdir / "design.v"
    f.write_text("line1\nif (x == 10) y <= 0;\nline3\n")
    r = apply_patch(str(f), 2, "== 99", "== 9")   # wrong 'before'
    assert r["success"] is False

def test_restore_backup(tmpdir):
    f   = tmpdir / "design.v"
    bak = tmpdir / "design.v.bak"
    f.write_text("original\n")
    bak.write_text("original\n")
    f.write_text("mutated\n")
    result = restore_backup(str(f))
    assert result is True
    assert f.read_text() == "original\n"

def test_read_rtl(tmpdir):
    f = tmpdir / "d.v"
    f.write_text("a\nb\nc\n")
    lines = read_rtl(str(f))
    assert lines == ["a", "b", "c"]

def test_apply_patches_multi(tmpdir):
    f = tmpdir / "d.v"
    f.write_text("q1 = din;\nq2 = q1;\ndout = q2;\n")
    r = apply_patches(str(f), [
        {"line_no": 1, "before": "q1 = din",  "after": "q1 <= din"},
        {"line_no": 2, "before": "q2 = q1",   "after": "q2 <= q1"},
        {"line_no": 3, "before": "dout = q2", "after": "dout <= q2"},
    ])
    assert r["success"] is True
    txt = f.read_text()
    assert "q1 <= din" in txt and "q2 <= q1" in txt and "dout <= q2" in txt
    assert len(r["applied"]) == 3

def test_apply_patches_atomic_abort(tmpdir):
    f = tmpdir / "d.v"
    original = "a = 1;\nb = 2;\n"
    f.write_text(original)
    r = apply_patches(str(f), [
        {"line_no": 1, "before": "a = 1", "after": "a = 9"},   # valid
        {"line_no": 2, "before": "NOPE",  "after": "x"},        # not on line 2
    ])
    assert r["success"] is False
    assert f.read_text() == original   # all-or-nothing: nothing written
