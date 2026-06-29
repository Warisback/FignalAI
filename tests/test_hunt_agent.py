"""tests/test_hunt_agent.py — port parsing + testbench template (no API).

The agent only supplies stimulus; this proves the deterministic scaffolding
(parse_ports + build_tb) produces a valid, coverage-closing testbench.
"""
import pathlib, sys
sys.path.insert(0, "..")
from hunt_agent import parse_ports, build_tb
from tools import run_sim
from coverage import toggle_coverage

REG4 = """`timescale 1ns/1ps
module reg4(input clk, input [3:0] din, output reg [3:0] q);
    always @(posedge clk) q <= din;
endmodule
"""


def test_parse_ports():
    name, ports = parse_ports(REG4)
    assert name == "reg4"
    by = {p["name"]: p for p in ports}
    assert by["clk"]["width"] == 1 and by["clk"]["dir"] == "input"
    assert by["din"]["width"] == 4 and by["din"]["dir"] == "input"
    assert by["q"]["width"] == 4 and by["q"]["dir"] == "output"


def test_build_tb_compiles_and_covers(tmp_path):
    name, ports = parse_ports(REG4)
    # vectors in drivable-input order (just [din]); one vector per clock cycle
    (tmp_path / "design.v").write_text(REG4)
    (tmp_path / "tb.v").write_text(build_tb(name, ports, [[15], [0]]))
    r = run_sim(str(tmp_path / "design.v"), str(tmp_path / "tb.v"), work_dir=str(tmp_path))
    assert r["vcd"], r["log"][:300]
    cov = toggle_coverage(r["vcd"], ["q"])
    assert cov["per_signal"]["q"]["pct"] == 100.0   # template + stimulus close coverage


GATE = """`timescale 1ns/1ps
module gate(input clk, input [1:0] sel, output reg hit);
    always @(posedge clk) hit <= (sel == 2'd3);
endmodule
"""


def test_build_tb_one_bit_output_compiles(tmp_path):
    # regression: a 1-bit output must declare as 'wire hit;', not 'wirehit;'
    name, ports = parse_ports(GATE)
    (tmp_path / "design.v").write_text(GATE)
    (tmp_path / "tb.v").write_text(build_tb(name, ports, [[3], [0]]))
    r = run_sim(str(tmp_path / "design.v"), str(tmp_path / "tb.v"), work_dir=str(tmp_path))
    assert r["stage"] == "run", r["log"][:300]    # compiled
    assert r["vcd"]


def test_sweep_fallback_closes_gate(tmp_path):
    # the deterministic sweep alone must close the gate's coverage (hit toggles)
    from hunt import hunt_coverage
    from hunt_agent import agent_generator
    (tmp_path / "design.v").write_text(GATE)
    name, ports = parse_ports(GATE)
    # force the sweep path by making the agent return nothing (no network in tests):
    import hunt_agent
    gen = agent_generator(name, ports)
    hunt_agent._agent_vectors = lambda *a, **k: []   # stub out the model call
    res = hunt_coverage(str(tmp_path / "design.v"), str(tmp_path / "tb.v"),
                        ["sel", "hit"], gen, threshold=100.0, max_rounds=2, work_dir=str(tmp_path))
    assert res["closed"] is True and res["best_pct"] == 100.0
