// (c) Copyright 1995-2026 Xilinx, Inc. All rights reserved.
// 
// This file contains confidential and proprietary information
// of Xilinx, Inc. and is protected under U.S. and
// international copyright and other intellectual property
// laws.
// 
// DISCLAIMER
// This disclaimer is not a license and does not grant any
// rights to the materials distributed herewith. Except as
// otherwise provided in a valid license issued to you by
// Xilinx, and to the maximum extent permitted by applicable
// law: (1) THESE MATERIALS ARE MADE AVAILABLE "AS IS" AND
// WITH ALL FAULTS, AND XILINX HEREBY DISCLAIMS ALL WARRANTIES
// AND CONDITIONS, EXPRESS, IMPLIED, OR STATUTORY, INCLUDING
// BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, NON-
// INFRINGEMENT, OR FITNESS FOR ANY PARTICULAR PURPOSE; and
// (2) Xilinx shall not be liable (whether in contract or tort,
// including negligence, or under any other theory of
// liability) for any loss or damage of any kind or nature
// related to, arising under or in connection with these
// materials, including for any direct, or any indirect,
// special, incidental, or consequential loss or damage
// (including loss of data, profits, goodwill, or any type of
// loss or damage suffered as a result of any action brought
// by a third party) even if such damage or loss was
// reasonably foreseeable or Xilinx had been advised of the
// possibility of the same.
// 
// CRITICAL APPLICATIONS
// Xilinx products are not designed or intended to be fail-
// safe, or for use in any application requiring fail-safe
// performance, such as life-support or safety devices or
// systems, Class III medical devices, nuclear facilities,
// applications related to the deployment of airbags, or any
// other applications that could lead to death, personal
// injury, or severe property or environmental damage
// (individually and collectively, "Critical
// Applications"). Customer assumes the sole risk and
// liability of any use of Xilinx products in Critical
// Applications, subject only to applicable laws and
// regulations governing limitations on product liability.
// 
// THIS COPYRIGHT NOTICE AND DISCLAIMER MUST BE RETAINED AS
// PART OF THIS FILE AT ALL TIMES.
// 
// DO NOT MODIFY THIS FILE.


// IP VLNV: xilinx.com:module_ref:spi_emio_master_io:1.0
// IP Revision: 1

`timescale 1ns/1ps

(* IP_DEFINITION_SOURCE = "module_ref" *)
(* DowngradeIPIdentifiedWarnings = "yes" *)
module system_esp32_spi_io_0 (
  sclk_o,
  sclk_t,
  mosi_o,
  mosi_t,
  cs_o,
  cs_t,
  sclk_i,
  mosi_i,
  miso_i,
  ss_i,
  esp_spi_sclk,
  esp_spi_mosi,
  esp_spi_cs_n,
  esp_spi_miso
);

input wire sclk_o;
input wire sclk_t;
input wire mosi_o;
input wire mosi_t;
input wire cs_o;
input wire cs_t;
output wire sclk_i;
output wire mosi_i;
output wire miso_i;
output wire ss_i;
inout wire esp_spi_sclk;
inout wire esp_spi_mosi;
inout wire esp_spi_cs_n;
input wire esp_spi_miso;

  spi_emio_master_io inst (
    .sclk_o(sclk_o),
    .sclk_t(sclk_t),
    .mosi_o(mosi_o),
    .mosi_t(mosi_t),
    .cs_o(cs_o),
    .cs_t(cs_t),
    .sclk_i(sclk_i),
    .mosi_i(mosi_i),
    .miso_i(miso_i),
    .ss_i(ss_i),
    .esp_spi_sclk(esp_spi_sclk),
    .esp_spi_mosi(esp_spi_mosi),
    .esp_spi_cs_n(esp_spi_cs_n),
    .esp_spi_miso(esp_spi_miso)
  );
endmodule
