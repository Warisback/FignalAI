// shiftreg.v — 3-stage shift register (din -> q1 -> q2 -> dout)
// Bug: blocking assignments (=) instead of non-blocking (<=). All three update
//      in the same delta step, collapsing the 3-cycle delay to ~1 cycle.
//      A correct fix changes ALL THREE lines (= -> <=) in one patch.
// Signal to watch: dout should equal din delayed by exactly 3 clock cycles.
`timescale 1ns/1ps
module shiftreg(
    input  clk,
    input  din,
    output reg dout
);
    reg q1, q2;

    always @(posedge clk) begin
        q1   = din;    // BUG: should be <=
        q2   = q1;     // BUG: should be <=
        dout = q2;     // BUG: should be <=
    end
endmodule
