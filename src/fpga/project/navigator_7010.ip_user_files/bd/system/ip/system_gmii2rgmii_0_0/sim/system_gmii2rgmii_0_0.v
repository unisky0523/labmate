// (c) Copyright 1995-2025 Xilinx, Inc. All rights reserved.
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


// IP VLNV: xilinx.com:user:gmii2rgmii:1.0
// IP Revision: 1

`timescale 1ns/1ps

(* IP_DEFINITION_SOURCE = "package_project" *)
(* DowngradeIPIdentifiedWarnings = "yes" *)
module system_gmii2rgmii_0_0 (
  idelay_clk,
  gmii_rx_clk,
  gmii_rx_dv,
  gmii_rxd,
  gmii_rx_er,
  gmii_tx_clk,
  gmii_tx_en,
  gmii_txd,
  rgmii_rxc,
  rgmii_rx_ctl,
  rgmii_rxd,
  rgmii_txc,
  rgmii_tx_ctl,
  rgmii_txd
);

input wire idelay_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII RX_CLK" *)
output wire gmii_rx_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII RX_DV" *)
output wire gmii_rx_dv;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII RXD" *)
output wire [7 : 0] gmii_rxd;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII RX_ER" *)
output wire gmii_rx_er;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII TX_CLK" *)
output wire gmii_tx_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII TX_EN" *)
input wire gmii_tx_en;
(* X_INTERFACE_INFO = "xilinx.com:interface:gmii:1.0 GMII TXD" *)
input wire [7 : 0] gmii_txd;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII RXC" *)
input wire rgmii_rxc;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII RX_CTL" *)
input wire rgmii_rx_ctl;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII RD" *)
input wire [3 : 0] rgmii_rxd;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII TXC" *)
output wire rgmii_txc;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII TX_CTL" *)
output wire rgmii_tx_ctl;
(* X_INTERFACE_INFO = "xilinx.com:interface:rgmii:1.0 RGMII TD" *)
output wire [3 : 0] rgmii_txd;

  gmii_to_rgmii #(
    .IDELAY_VALUE(0)
  ) inst (
    .idelay_clk(idelay_clk),
    .gmii_rx_clk(gmii_rx_clk),
    .gmii_rx_dv(gmii_rx_dv),
    .gmii_rxd(gmii_rxd),
    .gmii_rx_er(gmii_rx_er),
    .gmii_tx_clk(gmii_tx_clk),
    .gmii_tx_en(gmii_tx_en),
    .gmii_txd(gmii_txd),
    .rgmii_rxc(rgmii_rxc),
    .rgmii_rx_ctl(rgmii_rx_ctl),
    .rgmii_rxd(rgmii_rxd),
    .rgmii_txc(rgmii_txc),
    .rgmii_tx_ctl(rgmii_tx_ctl),
    .rgmii_txd(rgmii_txd)
  );
endmodule
