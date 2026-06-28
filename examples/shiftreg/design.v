// shiftreg.v — 3-stage shift register (din -> q1 -> q2 -> dout)
// Bug: the middle stage samples din instead of q1, collapsing the pipeline
//      to 2 stages, so dout lags din by 2 cycles instead of 3.
// Signal to watch: dout should equal din delayed by exactly 3 clock cycles.
`timescale 1ns/1ps
module shiftreg(
    input  clk,
    input  din,
    output reg dout
);
    reg q1, q2;

    always @(posedge clk) begin
        q1   <= din;
        q2   <= din;   // BUG: should be q1 (this skips a pipeline stage)
        dout <= q2;
    end
endmodule
