// counter.v — buggy mod-10 counter
// BUG: wraps when count reaches 10 (should wrap at 9)
// Signal to watch: count[3:0] — expect 0-1-2-3-4-5-6-7-8-9-0, see 0-1-2-3-4-5-6-7-8-9-10-0

module counter(
    input        clk,
    input        rst_n,
    output reg [3:0] count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'd0;
        else if (count == 4'd10)   // BUG: should be 4'd9
            count <= 4'd0;
        else
            count <= count + 4'd1;
    end
endmodule
