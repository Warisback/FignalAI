`timescale 1ns/1ps
module tb;
    reg        clk   = 0;
    reg        rst_n = 0;
    reg        go    = 0;
    wire [1:0] state;
    integer    errors = 0;

    fsm dut (.clk(clk), .rst_n(rst_n), .go(go), .state(state));

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb);
    end

    always #5 clk = ~clk;

    initial begin
        #12 rst_n = 1;
        @(posedge clk); #1;
        // After reset, state must be IDLE (0)
        if (state !== 2'd0) begin
            $display("ERROR: state is %0b after reset (expected 0/IDLE)", state);
            errors = errors + 1;
        end
        // Pulse go and check transition
        go = 1; @(posedge clk); #1; go = 0;
        if (state !== 2'd1) begin
            $display("ERROR: state is %0b after go (expected 1/RUN)", state);
            errors = errors + 1;
        end
        @(posedge clk); #1;
        if (state !== 2'd2) begin
            $display("ERROR: state is %0b (expected 2/DONE)", state);
            errors = errors + 1;
        end
        #20;
        if (errors == 0)
            $display("RESULT: PASS");
        else
            $display("RESULT: FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
