"""tests/test_render.py — VCD parsing, text description, and PNG rendering.

Generates a REAL VCD with iverilog/vvp, then exercises the parser and renderer
against it (regression guard for the off-by-one $var parse bug and the scalar
step-plot length mismatch that previously broke both).
"""
import pytest, pathlib, tempfile, sys
sys.path.insert(0, "..")
from tools import run_sim
from render import parse_vcd, describe_waveform, render_waveform

# 4-bit counter: gives us a bus signal (count) + a clock + a scalar reset.
RTL = """`timescale 1ns/1ps
module counter(input clk, input rst_n, output reg [3:0] count);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 4'd0;
        else        count <= count + 4'd1;
    end
endmodule
"""

TB = """`timescale 1ns/1ps
module tb;
    reg clk = 0, rst_n = 0;
    wire [3:0] count;
    counter dut(.clk(clk), .rst_n(rst_n), .count(count));
    initial begin $dumpfile("dump.vcd"); $dumpvars(0, tb); end
    always #5 clk = ~clk;
    initial begin #12 rst_n = 1; #200 $display("RESULT: PASS"); $finish; end
endmodule
"""


@pytest.fixture
def vcd():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "design.v").write_text(RTL)
        (d / "tb.v").write_text(TB)
        r = run_sim(str(d / "design.v"), str(d / "tb.v"), work_dir=str(d))
        assert r["vcd"], "simulation produced no VCD"
        yield d, r["vcd"]


def test_parse_vcd_keyed_by_name_with_transitions(vcd):
    _, path = vcd
    tv = parse_vcd(path)
    # keyed by signal NAME (not VCD id), and signals actually have transitions
    assert "count" in tv and "clk" in tv and "rst_n" in tv
    assert len(tv["count"]) > 5
    assert len(tv["clk"]) > 5


def test_parse_vcd_decodes_bus_values(vcd):
    _, path = vcd
    tv = parse_vcd(path)
    # count is a 4-bit bus -> values are multi-char binary strings
    assert any(len(v) > 1 for _, v in tv["count"])


def test_describe_waveform_is_per_cycle(vcd):
    _, path = vcd
    desc = describe_waveform(path, ["clk", "rst_n", "count"])
    assert "per cycle" in desc
    # a free-running 4-bit counter must visit double-digit decimal values
    assert "10" in desc or "11" in desc


def test_render_waveform_writes_png(vcd):
    d, path = vcd
    out = render_waveform(path, ["clk", "rst_n", "count"], out_path=str(d / "w.png"))
    assert pathlib.Path(out).exists()
    assert pathlib.Path(out).stat().st_size > 0
