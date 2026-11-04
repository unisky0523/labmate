`timescale 1ns/1ps
module tb_frontend;
    parameter BYPASS=0;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0, valid=0, ready=0;
    reg [31:0] din=0; reg [2:0] id=0;
    wire rin, vo; wire [31:0] dout; wire [7:0] oid;
    asr_audio_frontend #(.BYPASS(BYPASS)) dut(clk,resetn,din,id,valid,rin,dout,oid,vo,ready);
    reg [34:0] vectors[0:5999], golden[0:5999];
    integer sent=0, received=0, n, epoch, cycles=0;
    reg checking=0, stalled=0;
    reg [39:0] held;
    reg [31:0] random_state=32'h19847abc;
    always @(negedge clk) begin
        random_state = {random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        ready = random_state[2:0] != 0;
    end
    always @(posedge clk) begin
        cycles = cycles+1;
        if (!resetn) begin sent=0; received=0; stalled=0; end
        else if (checking) begin
            if (stalled && (!vo || {oid,dout} !== held)) $fatal(1,"unstable during stall");
            if (valid && rin) sent=sent+1;
            if (vo && ready) begin
                if (received >= sent) $fatal(1,"extra output");
                if ({oid,dout} !== {5'b0,(BYPASS ? vectors[received] : golden[received])})
                    $fatal(1,"mismatch %d: got %h/%h expected %h",received,oid,dout,golden[received]);
                received=received+1;
            end
            stalled=vo && !ready; held={oid,dout};
        end
    end
    task send_word(input [34:0] word);
        begin
            @(negedge clk); valid=1; id=word[34:32]; din=word[31:0];
            @(posedge clk); while (!rin) @(posedge clk);
            @(negedge clk); valid=0;
        end
    endtask
    initial begin
        $readmemh("input.hex",vectors); $readmemh("expected.hex",golden);
        repeat(5) @(negedge clk); resetn=1;
        send_word(vectors[0]);
        repeat(10) @(negedge clk); // Reset with a FIR calculation in flight.
        resetn=0;
        repeat(5) @(negedge clk); resetn=1; checking=1;
        for (epoch=0;epoch<2;epoch=epoch+1) begin
            for(n=0;n<6000;n=n+1) begin
                if (n%23==0) repeat(3) @(negedge clk);
                send_word(vectors[n]);
            end
            wait(received==6000);
            repeat(10) @(negedge clk);
            if(sent != received) $fatal(1,"lost samples");
            $display("PASS BYPASS=%d epoch=%d samples=%d",BYPASS,epoch,received);
            resetn=0; repeat(5) @(negedge clk); resetn=1;
        end
        $finish;
    end
    initial begin #100000000; $fatal(1,"timeout"); end
endmodule
module tb_mode0; tb_frontend #(.BYPASS(0)) test(); endmodule
module tb_mode1; tb_frontend #(.BYPASS(1)) test(); endmodule
