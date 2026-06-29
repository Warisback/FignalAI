"""tests/test_checks.py — deterministic guard tests"""
import pytest
import sys; sys.path.insert(0, "..")
from checks import line_check, patch_check, majority_vote

RTL = [
    "module counter(",
    "    input clk,",
    "    output reg [3:0] count",
    ");",
    "    always @(posedge clk) begin",
    "        if (count == 4'd10) count <= 4'd0;",
    "        else count <= count + 1;",
    "    end",
    "endmodule",
]

def test_line_check_exact_match():
    assert line_check(RTL, 6, "4'd10") is True

def test_line_check_wrong_line():
    assert line_check(RTL, 2, "4'd10") is False

def test_line_check_out_of_range():
    assert line_check(RTL, 99, "anything") is False

def test_line_check_zero_index():
    assert line_check(RTL, 0, "module") is False

def test_line_check_partial_match():
    # partial quote should still pass
    assert line_check(RTL, 6, "count == 4'd10") is True

def test_majority_vote_clear_winner():
    hyps = [
        {"line_no": 6, "bug_class": "wrong_constant"},
        {"line_no": 6, "bug_class": "wrong_constant"},
        {"line_no": 6, "bug_class": "wrong_constant"},
        {"line_no": 2, "bug_class": "missing_reset"},
    ]
    w = majority_vote(hyps)
    assert w["line_no"] == 6

def test_majority_vote_no_agreement():
    hyps = [
        {"line_no": 1, "bug_class": "other"},
        {"line_no": 2, "bug_class": "other"},
        {"line_no": 3, "bug_class": "other"},
    ]
    # all unique — no majority
    assert majority_vote(hyps) is None

def test_majority_vote_empty():
    assert majority_vote([]) is None

def test_patch_check_valid():
    assert patch_check(RTL, 6, "4'd10") is True

def test_patch_check_wrong_text():
    assert patch_check(RTL, 6, "4'd99") is False
