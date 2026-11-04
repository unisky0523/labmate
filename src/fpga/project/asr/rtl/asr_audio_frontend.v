`timescale 1ns/1ps
// PG308 audio frames. Clock: 100 MHz, input: 44.1 kHz stereo, 24-bit.
// BYPASS=1 is bit-exact transport. BYPASS=0 enables DC blocker + 127-tap FIR.
module asr_audio_frontend #(parameter BYPASS=1)(
    input wire aclk, input wire aresetn,
    input wire [31:0] in_data, input wire [2:0] in_id,
    input wire in_valid, output wire in_ready,
    output reg [31:0] out_data, output reg [7:0] out_id,
    output reg out_valid, input wire out_ready
);
generate if (BYPASS) begin : bypass_path
    assign in_ready = !out_valid || out_ready;
    always @(posedge aclk) begin
        if (!aresetn) begin
            out_valid <= 0; out_data <= 0; out_id <= 0;
        end else if (in_ready) begin
            out_valid <= in_valid;
            if (in_valid) begin out_data <= in_data; out_id <= {5'b0,in_id}; end
        end
    end
end else begin : filter_path
    `include "fir_coeff.vh"
    localparam INIT=0, IDLE=1, DC=2, STORE=3, LOAD=4, MUL=5, ACC=6, EMIT=7;
    reg [3:0] state;
    reg signed [23:0] previous_x [0:7], previous_y [0:7];
    reg [6:0] wr_ptr [0:7];
    reg [9:0] clear_addr;
    reg [6:0] tap;
    reg [31:0] saved;
    reg [2:0] channel;
    reg signed [25:0] delta, feedback, dc_wide;
    wire signed [23:0] sample_q;
    reg signed [17:0] coeff_q;
    (* use_dsp="yes" *) reg signed [41:0] product;
    reg signed [47:0] accumulator;
    wire signed [23:0] x = in_data[27:4];
    wire signed [25:0] sx = {{2{x[23]}},x};
    wire signed [25:0] px = {{2{previous_x[in_id][23]}},previous_x[in_id]};
    wire signed [25:0] py = {{2{previous_y[in_id][23]}},previous_y[in_id]};
    wire signed [23:0] dc_sample = dc_wide > 26'sd8388607 ? 24'sh7fffff :
        dc_wide < -26'sd8388608 ? 24'sh800000 : dc_wide[23:0];
    wire [6:0] rd_ptr = wr_ptr[channel] - tap;
    wire signed [47:0] scaled = (accumulator + 48'sd65536) >>> 17;
    wire signed [23:0] y = scaled > 48'sd8388607 ? 24'sh7fffff :
        scaled < -48'sd8388608 ? 24'sh800000 : scaled[23:0];
    wire [30:0] payload = {saved[30:28],y,saved[3:0]};
    wire ram_we = aresetn && (state == INIT || state == STORE);
    wire [9:0] ram_wa = state == INIT ? clear_addr : {channel,wr_ptr[channel]};
    wire [23:0] ram_wd = state == INIT ? 24'd0 : dc_sample;
    assign in_ready = (state == IDLE) && (!out_valid || out_ready);
    // Keep the read register at the RAM boundary instead of absorbing it into DSP.
    (* keep_hierarchy="yes" *) asr_history_ram history_ram(
        .clk(aclk), .we(ram_we), .wa(ram_wa), .wd(ram_wd),
        .ra({channel,rd_ptr}), .rd(sample_q));
    integer i;
    always @(posedge aclk) begin
        if (!aresetn) begin
            state <= INIT; clear_addr <= 0;
            out_valid <= 0; out_data <= 0; out_id <= 0;
            saved <= 0; channel <= 0; tap <= 0;
            delta <= 0; feedback <= 0; dc_wide <= 0;
            coeff_q <= 0; product <= 0; accumulator <= 0;
            for (i=0;i<8;i=i+1) begin
                previous_x[i] <= 0; previous_y[i] <= 0; wr_ptr[i] <= 0;
            end
        end else begin
            if (out_valid && out_ready) out_valid <= 0;
            case(state)
            INIT: if (clear_addr == 1023) state <= IDLE;
                  else clear_addr <= clear_addr + 1'b1;
            IDLE: if (in_valid && in_ready) begin
                saved <= in_data; channel <= in_id;
                if (in_data[28]) begin
                    // Invalid audio stays invalid; do not feed it into filter state.
                    out_data <= in_data; out_id <= {5'b0,in_id}; out_valid <= 1;
                end else begin
                    delta <= sx - px;
                    feedback <= py - (py >>> 7);
                    state <= DC;
                end
            end
            DC: begin dc_wide <= delta + feedback; state <= STORE; end
            STORE: begin
                previous_x[channel] <= saved[27:4]; previous_y[channel] <= dc_sample;
                accumulator <= 0; tap <= 0; state <= LOAD;
            end
            LOAD: begin coeff_q <= coefficient(tap); state <= MUL; end
            MUL: begin product <= sample_q * coeff_q; state <= ACC; end
            ACC: begin
                accumulator <= accumulator + {{6{product[41]}},product};
                if (tap == 126) state <= EMIT;
                else begin tap <= tap + 1'b1; state <= LOAD; end
            end
            EMIT: begin
                out_data <= {^payload[30:4],payload}; // IEC60958 parity excludes preamble.
                out_id <= {5'b0,channel}; out_valid <= 1;
                wr_ptr[channel] <= wr_ptr[channel] + 1'b1;
                state <= IDLE;
            end
            endcase
        end
    end
end endgenerate
endmodule

module asr_history_ram(
    input wire clk, input wire we,
    input wire [9:0] wa, input wire [23:0] wd,
    input wire [9:0] ra, output reg [23:0] rd
);
    (* ram_style="block" *) reg [23:0] memory [0:1023];
    always @(posedge clk) begin
        if (we) memory[wa] <= wd;
        rd <= memory[ra];
    end
endmodule
