// alu.v — 8-bit ALU (0=ADD, 1=SUB, 2=AND, 3=OR)
// Bug: the SUB opcode computes a + b instead of a - b.
// Signal to watch: y for op=1 (SUB) is wrong (a+b instead of a-b).
`timescale 1ns/1ps
module alu(
    input      [7:0] a,
    input      [7:0] b,
    input      [1:0] op,
    output reg [7:0] y
);
    always @(*) begin
        case (op)
            2'd0: y = a + b;
            2'd1: y = a + b;   // BUG: SUB should be a - b
            2'd2: y = a & b;
            2'd3: y = a | b;
            default: y = 8'd0;
        endcase
    end
endmodule
