// fsm.v — 3-state FSM: IDLE -> RUN -> DONE -> IDLE
// Bug: the RUN state goes back to IDLE instead of advancing to DONE,
//      so the machine never reaches DONE (state oscillates 0<->1).
// Signal to watch: state[1:0] — should step 0 -> 1 -> 2 after `go`.
`timescale 1ns/1ps
module fsm(
    input      clk,
    input      rst_n,
    input      go,
    output reg [1:0] state
);
    localparam IDLE = 2'd0, RUN = 2'd1, DONE = 2'd2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= IDLE;
        else case (state)
            IDLE: if (go) state <= RUN;
            RUN:  state <= IDLE;   // BUG: should be DONE
            DONE: state <= IDLE;
            default: state <= IDLE;
        endcase
    end
endmodule
