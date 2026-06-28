// counter.v — mod-10 counter with an off-by-one bug
// Bug: wraps at count==10 instead of count==9
`timescale 1ns/1ps
module counter(
    input       clk,
    input       rst_n,
    output reg [3:0] count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'd0;
        else if (count == 4'd10)  // BUG: should be 4'd9
            count <= 4'd0;
        else
            count <= count + 4'd1;
    end
endmodule
