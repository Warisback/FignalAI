// tb_counter.v — self-checking testbench
// Prints RESULT: PASS or RESULT: FAIL (N errors)
`timescale 1ns/1ps
module tb;
    reg        clk   = 0;
    reg        rst_n = 0;
    wire [3:0] count;
    integer    errors = 0;

    counter dut (.clk(clk), .rst_n(rst_n), .count(count));

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb);
    end

    always #5 clk = ~clk;   // 10ns period

    integer i;
    initial begin
        #12 rst_n = 1;
        // Run for 25 clock cycles and check count never exceeds 9
        for (i = 0; i < 25; i = i + 1) begin
            @(posedge clk); #1;
            if (count > 4'd9) begin
                $display("ERROR at t=%0t: count=%0d (exceeds 9)", $time, count);
                errors = errors + 1;
            end
        end
        if (errors == 0)
            $display("RESULT: PASS");
        else
            $display("RESULT: FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
