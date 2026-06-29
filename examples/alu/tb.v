// tb.v — self-checking testbench for the 8-bit ALU.
// Drives known operands through each opcode and checks the result.
`timescale 1ns/1ps
module tb;
    reg  [7:0] a, b;
    reg  [1:0] op;
    wire [7:0] y;
    integer    errors = 0;

    alu dut (.a(a), .b(b), .op(op), .y(y));

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb);
    end

    task check(input [7:0] expected);
        begin
            #2;
            if (y !== expected) begin
                $display("ERROR op=%0d a=%0d b=%0d -> y=%0d (expected %0d)",
                         op, a, b, y, expected);
                errors = errors + 1;
            end
            #1;
        end
    endtask

    initial begin
        a = 8'd20; b = 8'd5;
        op = 2'd0; check(8'd25);          // ADD: 20 + 5
        op = 2'd1; check(8'd15);          // SUB: 20 - 5   <-- bug yields 25
        op = 2'd2; check(8'd20 & 8'd5);   // AND
        op = 2'd3; check(8'd20 | 8'd5);   // OR
        #5;
        if (errors == 0) $display("RESULT: PASS");
        else             $display("RESULT: FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
