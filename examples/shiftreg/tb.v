// tb.v — self-checking testbench for the 3-stage shift register.
// Compares the DUT output against a golden 3-stage reference pipeline.
// A correct shiftreg makes dout == din delayed by exactly 3 clock cycles.
`timescale 1ns/1ps
module tb;
    reg     clk = 0;
    reg     din = 0;
    wire    dout;
    integer errors = 0;
    integer n;

    // golden reference: a true 3-stage pipeline
    reg r1, r2, r3;

    shiftreg dut (.clk(clk), .din(din), .dout(dout));

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb);
    end

    always #5 clk = ~clk;

    // golden model advances on the same clock edges as the DUT
    always @(posedge clk) begin
        r1 <= din;
        r2 <= r1;
        r3 <= r2;
    end

    // arbitrary stimulus pattern (drives one bit per clock cycle)
    reg [0:19] seq;
    initial begin
        seq = 20'b0001_0110_0101_1100_1010;
        din = 0;
        // let both pipelines flush the initial x out
        repeat (4) @(negedge clk);
        for (n = 0; n < 20; n = n + 1) begin
            din = seq[n];
            @(posedge clk); #1;
            if (n >= 4) begin   // both pipelines primed by now
                if (dout !== r3) begin
                    $display("ERROR step %0d: dout=%b expected %b (din delayed 3 cycles)",
                             n, dout, r3);
                    errors = errors + 1;
                end
            end
        end
        if (errors == 0) $display("RESULT: PASS");
        else             $display("RESULT: FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
