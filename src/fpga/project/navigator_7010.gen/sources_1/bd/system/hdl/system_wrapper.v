//Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2020.2 (win64) Build 3064766 Wed Nov 18 09:12:45 MST 2020
//Date        : Tue Nov  3 23:41:10 2026
//Host        : LAPTOP-DB6S7DJE running 64-bit major release  (build 9200)
//Command     : generate_target system_wrapper.bd
//Design      : system_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module system_wrapper
   (DDR_addr,
    DDR_ba,
    DDR_cas_n,
    DDR_ck_n,
    DDR_ck_p,
    DDR_cke,
    DDR_cs_n,
    DDR_dm,
    DDR_dq,
    DDR_dqs_n,
    DDR_dqs_p,
    DDR_odt,
    DDR_ras_n,
    DDR_reset_n,
    DDR_we_n,
    FIXED_IO_ddr_vrn,
    FIXED_IO_ddr_vrp,
    FIXED_IO_mio,
    FIXED_IO_ps_clk,
    FIXED_IO_ps_porb,
    FIXED_IO_ps_srstb,
    aud_adcdat,
    aud_adclrc,
    aud_bclk,
    aud_dacdat,
    aud_daclrc,
    aud_mclk,
    cmos_data,
    cmos_href,
    cmos_pclk,
    cmos_vsync,
    esp_spi_cs_n,
    esp_spi_miso,
    esp_spi_mosi,
    esp_spi_sclk,
    gpio0_tri_io,
    i2c0_scl_io,
    i2c0_sda_io,
    i2c1_scl_io,
    i2c1_sda_io,
    i2c2_scl_io,
    i2c2_sda_io,
    lcd_bl,
    lcd_clk,
    lcd_de,
    lcd_hs,
    lcd_rgb_tri_io,
    lcd_rst,
    lcd_vs,
    mdio_mdc,
    mdio_mdio_io,
    pl_led_tri_o,
    rgmii_rd,
    rgmii_rx_ctl,
    rgmii_rxc,
    rgmii_td,
    rgmii_tx_ctl,
    rgmii_txc);
  inout [14:0]DDR_addr;
  inout [2:0]DDR_ba;
  inout DDR_cas_n;
  inout DDR_ck_n;
  inout DDR_ck_p;
  inout DDR_cke;
  inout DDR_cs_n;
  inout [3:0]DDR_dm;
  inout [31:0]DDR_dq;
  inout [3:0]DDR_dqs_n;
  inout [3:0]DDR_dqs_p;
  inout DDR_odt;
  inout DDR_ras_n;
  inout DDR_reset_n;
  inout DDR_we_n;
  inout FIXED_IO_ddr_vrn;
  inout FIXED_IO_ddr_vrp;
  inout [53:0]FIXED_IO_mio;
  inout FIXED_IO_ps_clk;
  inout FIXED_IO_ps_porb;
  inout FIXED_IO_ps_srstb;
  input aud_adcdat;
  output aud_adclrc;
  output [0:0]aud_bclk;
  output aud_dacdat;
  output aud_daclrc;
  output aud_mclk;
  input [7:0]cmos_data;
  input cmos_href;
  input cmos_pclk;
  input cmos_vsync;
  inout esp_spi_cs_n;
  input esp_spi_miso;
  inout esp_spi_mosi;
  inout esp_spi_sclk;
  inout [11:0]gpio0_tri_io;
  inout i2c0_scl_io;
  inout i2c0_sda_io;
  inout i2c1_scl_io;
  inout i2c1_sda_io;
  inout i2c2_scl_io;
  inout i2c2_sda_io;
  output [0:0]lcd_bl;
  output lcd_clk;
  output lcd_de;
  output lcd_hs;
  inout [23:0]lcd_rgb_tri_io;
  output [0:0]lcd_rst;
  output lcd_vs;
  output mdio_mdc;
  inout mdio_mdio_io;
  output [1:0]pl_led_tri_o;
  input [3:0]rgmii_rd;
  input rgmii_rx_ctl;
  input rgmii_rxc;
  output [3:0]rgmii_td;
  output rgmii_tx_ctl;
  output rgmii_txc;

  wire [14:0]DDR_addr;
  wire [2:0]DDR_ba;
  wire DDR_cas_n;
  wire DDR_ck_n;
  wire DDR_ck_p;
  wire DDR_cke;
  wire DDR_cs_n;
  wire [3:0]DDR_dm;
  wire [31:0]DDR_dq;
  wire [3:0]DDR_dqs_n;
  wire [3:0]DDR_dqs_p;
  wire DDR_odt;
  wire DDR_ras_n;
  wire DDR_reset_n;
  wire DDR_we_n;
  wire FIXED_IO_ddr_vrn;
  wire FIXED_IO_ddr_vrp;
  wire [53:0]FIXED_IO_mio;
  wire FIXED_IO_ps_clk;
  wire FIXED_IO_ps_porb;
  wire FIXED_IO_ps_srstb;
  wire aud_adcdat;
  wire aud_adclrc;
  wire [0:0]aud_bclk;
  wire aud_dacdat;
  wire aud_daclrc;
  wire aud_mclk;
  wire [7:0]cmos_data;
  wire cmos_href;
  wire cmos_pclk;
  wire cmos_vsync;
  wire esp_spi_cs_n;
  wire esp_spi_miso;
  wire esp_spi_mosi;
  wire esp_spi_sclk;
  wire [0:0]gpio0_tri_i_0;
  wire [1:1]gpio0_tri_i_1;
  wire [10:10]gpio0_tri_i_10;
  wire [11:11]gpio0_tri_i_11;
  wire [2:2]gpio0_tri_i_2;
  wire [3:3]gpio0_tri_i_3;
  wire [4:4]gpio0_tri_i_4;
  wire [5:5]gpio0_tri_i_5;
  wire [6:6]gpio0_tri_i_6;
  wire [7:7]gpio0_tri_i_7;
  wire [8:8]gpio0_tri_i_8;
  wire [9:9]gpio0_tri_i_9;
  wire [0:0]gpio0_tri_io_0;
  wire [1:1]gpio0_tri_io_1;
  wire [10:10]gpio0_tri_io_10;
  wire [11:11]gpio0_tri_io_11;
  wire [2:2]gpio0_tri_io_2;
  wire [3:3]gpio0_tri_io_3;
  wire [4:4]gpio0_tri_io_4;
  wire [5:5]gpio0_tri_io_5;
  wire [6:6]gpio0_tri_io_6;
  wire [7:7]gpio0_tri_io_7;
  wire [8:8]gpio0_tri_io_8;
  wire [9:9]gpio0_tri_io_9;
  wire [0:0]gpio0_tri_o_0;
  wire [1:1]gpio0_tri_o_1;
  wire [10:10]gpio0_tri_o_10;
  wire [11:11]gpio0_tri_o_11;
  wire [2:2]gpio0_tri_o_2;
  wire [3:3]gpio0_tri_o_3;
  wire [4:4]gpio0_tri_o_4;
  wire [5:5]gpio0_tri_o_5;
  wire [6:6]gpio0_tri_o_6;
  wire [7:7]gpio0_tri_o_7;
  wire [8:8]gpio0_tri_o_8;
  wire [9:9]gpio0_tri_o_9;
  wire [0:0]gpio0_tri_t_0;
  wire [1:1]gpio0_tri_t_1;
  wire [10:10]gpio0_tri_t_10;
  wire [11:11]gpio0_tri_t_11;
  wire [2:2]gpio0_tri_t_2;
  wire [3:3]gpio0_tri_t_3;
  wire [4:4]gpio0_tri_t_4;
  wire [5:5]gpio0_tri_t_5;
  wire [6:6]gpio0_tri_t_6;
  wire [7:7]gpio0_tri_t_7;
  wire [8:8]gpio0_tri_t_8;
  wire [9:9]gpio0_tri_t_9;
  wire i2c0_scl_i;
  wire i2c0_scl_io;
  wire i2c0_scl_o;
  wire i2c0_scl_t;
  wire i2c0_sda_i;
  wire i2c0_sda_io;
  wire i2c0_sda_o;
  wire i2c0_sda_t;
  wire i2c1_scl_i;
  wire i2c1_scl_io;
  wire i2c1_scl_o;
  wire i2c1_scl_t;
  wire i2c1_sda_i;
  wire i2c1_sda_io;
  wire i2c1_sda_o;
  wire i2c1_sda_t;
  wire i2c2_scl_i;
  wire i2c2_scl_io;
  wire i2c2_scl_o;
  wire i2c2_scl_t;
  wire i2c2_sda_i;
  wire i2c2_sda_io;
  wire i2c2_sda_o;
  wire i2c2_sda_t;
  wire [0:0]lcd_bl;
  wire lcd_clk;
  wire lcd_de;
  wire lcd_hs;
  wire [0:0]lcd_rgb_tri_i_0;
  wire [1:1]lcd_rgb_tri_i_1;
  wire [10:10]lcd_rgb_tri_i_10;
  wire [11:11]lcd_rgb_tri_i_11;
  wire [12:12]lcd_rgb_tri_i_12;
  wire [13:13]lcd_rgb_tri_i_13;
  wire [14:14]lcd_rgb_tri_i_14;
  wire [15:15]lcd_rgb_tri_i_15;
  wire [16:16]lcd_rgb_tri_i_16;
  wire [17:17]lcd_rgb_tri_i_17;
  wire [18:18]lcd_rgb_tri_i_18;
  wire [19:19]lcd_rgb_tri_i_19;
  wire [2:2]lcd_rgb_tri_i_2;
  wire [20:20]lcd_rgb_tri_i_20;
  wire [21:21]lcd_rgb_tri_i_21;
  wire [22:22]lcd_rgb_tri_i_22;
  wire [23:23]lcd_rgb_tri_i_23;
  wire [3:3]lcd_rgb_tri_i_3;
  wire [4:4]lcd_rgb_tri_i_4;
  wire [5:5]lcd_rgb_tri_i_5;
  wire [6:6]lcd_rgb_tri_i_6;
  wire [7:7]lcd_rgb_tri_i_7;
  wire [8:8]lcd_rgb_tri_i_8;
  wire [9:9]lcd_rgb_tri_i_9;
  wire [0:0]lcd_rgb_tri_io_0;
  wire [1:1]lcd_rgb_tri_io_1;
  wire [10:10]lcd_rgb_tri_io_10;
  wire [11:11]lcd_rgb_tri_io_11;
  wire [12:12]lcd_rgb_tri_io_12;
  wire [13:13]lcd_rgb_tri_io_13;
  wire [14:14]lcd_rgb_tri_io_14;
  wire [15:15]lcd_rgb_tri_io_15;
  wire [16:16]lcd_rgb_tri_io_16;
  wire [17:17]lcd_rgb_tri_io_17;
  wire [18:18]lcd_rgb_tri_io_18;
  wire [19:19]lcd_rgb_tri_io_19;
  wire [2:2]lcd_rgb_tri_io_2;
  wire [20:20]lcd_rgb_tri_io_20;
  wire [21:21]lcd_rgb_tri_io_21;
  wire [22:22]lcd_rgb_tri_io_22;
  wire [23:23]lcd_rgb_tri_io_23;
  wire [3:3]lcd_rgb_tri_io_3;
  wire [4:4]lcd_rgb_tri_io_4;
  wire [5:5]lcd_rgb_tri_io_5;
  wire [6:6]lcd_rgb_tri_io_6;
  wire [7:7]lcd_rgb_tri_io_7;
  wire [8:8]lcd_rgb_tri_io_8;
  wire [9:9]lcd_rgb_tri_io_9;
  wire [0:0]lcd_rgb_tri_o_0;
  wire [1:1]lcd_rgb_tri_o_1;
  wire [10:10]lcd_rgb_tri_o_10;
  wire [11:11]lcd_rgb_tri_o_11;
  wire [12:12]lcd_rgb_tri_o_12;
  wire [13:13]lcd_rgb_tri_o_13;
  wire [14:14]lcd_rgb_tri_o_14;
  wire [15:15]lcd_rgb_tri_o_15;
  wire [16:16]lcd_rgb_tri_o_16;
  wire [17:17]lcd_rgb_tri_o_17;
  wire [18:18]lcd_rgb_tri_o_18;
  wire [19:19]lcd_rgb_tri_o_19;
  wire [2:2]lcd_rgb_tri_o_2;
  wire [20:20]lcd_rgb_tri_o_20;
  wire [21:21]lcd_rgb_tri_o_21;
  wire [22:22]lcd_rgb_tri_o_22;
  wire [23:23]lcd_rgb_tri_o_23;
  wire [3:3]lcd_rgb_tri_o_3;
  wire [4:4]lcd_rgb_tri_o_4;
  wire [5:5]lcd_rgb_tri_o_5;
  wire [6:6]lcd_rgb_tri_o_6;
  wire [7:7]lcd_rgb_tri_o_7;
  wire [8:8]lcd_rgb_tri_o_8;
  wire [9:9]lcd_rgb_tri_o_9;
  wire [0:0]lcd_rgb_tri_t_0;
  wire [1:1]lcd_rgb_tri_t_1;
  wire [10:10]lcd_rgb_tri_t_10;
  wire [11:11]lcd_rgb_tri_t_11;
  wire [12:12]lcd_rgb_tri_t_12;
  wire [13:13]lcd_rgb_tri_t_13;
  wire [14:14]lcd_rgb_tri_t_14;
  wire [15:15]lcd_rgb_tri_t_15;
  wire [16:16]lcd_rgb_tri_t_16;
  wire [17:17]lcd_rgb_tri_t_17;
  wire [18:18]lcd_rgb_tri_t_18;
  wire [19:19]lcd_rgb_tri_t_19;
  wire [2:2]lcd_rgb_tri_t_2;
  wire [20:20]lcd_rgb_tri_t_20;
  wire [21:21]lcd_rgb_tri_t_21;
  wire [22:22]lcd_rgb_tri_t_22;
  wire [23:23]lcd_rgb_tri_t_23;
  wire [3:3]lcd_rgb_tri_t_3;
  wire [4:4]lcd_rgb_tri_t_4;
  wire [5:5]lcd_rgb_tri_t_5;
  wire [6:6]lcd_rgb_tri_t_6;
  wire [7:7]lcd_rgb_tri_t_7;
  wire [8:8]lcd_rgb_tri_t_8;
  wire [9:9]lcd_rgb_tri_t_9;
  wire [0:0]lcd_rst;
  wire lcd_vs;
  wire mdio_mdc;
  wire mdio_mdio_i;
  wire mdio_mdio_io;
  wire mdio_mdio_o;
  wire mdio_mdio_t;
  wire [1:0]pl_led_tri_o;
  wire [3:0]rgmii_rd;
  wire rgmii_rx_ctl;
  wire rgmii_rxc;
  wire [3:0]rgmii_td;
  wire rgmii_tx_ctl;
  wire rgmii_txc;

  IOBUF gpio0_tri_iobuf_0
       (.I(gpio0_tri_o_0),
        .IO(gpio0_tri_io[0]),
        .O(gpio0_tri_i_0),
        .T(gpio0_tri_t_0));
  IOBUF gpio0_tri_iobuf_1
       (.I(gpio0_tri_o_1),
        .IO(gpio0_tri_io[1]),
        .O(gpio0_tri_i_1),
        .T(gpio0_tri_t_1));
  IOBUF gpio0_tri_iobuf_10
       (.I(gpio0_tri_o_10),
        .IO(gpio0_tri_io[10]),
        .O(gpio0_tri_i_10),
        .T(gpio0_tri_t_10));
  IOBUF gpio0_tri_iobuf_11
       (.I(gpio0_tri_o_11),
        .IO(gpio0_tri_io[11]),
        .O(gpio0_tri_i_11),
        .T(gpio0_tri_t_11));
  IOBUF gpio0_tri_iobuf_2
       (.I(gpio0_tri_o_2),
        .IO(gpio0_tri_io[2]),
        .O(gpio0_tri_i_2),
        .T(gpio0_tri_t_2));
  IOBUF gpio0_tri_iobuf_3
       (.I(gpio0_tri_o_3),
        .IO(gpio0_tri_io[3]),
        .O(gpio0_tri_i_3),
        .T(gpio0_tri_t_3));
  IOBUF gpio0_tri_iobuf_4
       (.I(gpio0_tri_o_4),
        .IO(gpio0_tri_io[4]),
        .O(gpio0_tri_i_4),
        .T(gpio0_tri_t_4));
  IOBUF gpio0_tri_iobuf_5
       (.I(gpio0_tri_o_5),
        .IO(gpio0_tri_io[5]),
        .O(gpio0_tri_i_5),
        .T(gpio0_tri_t_5));
  IOBUF gpio0_tri_iobuf_6
       (.I(gpio0_tri_o_6),
        .IO(gpio0_tri_io[6]),
        .O(gpio0_tri_i_6),
        .T(gpio0_tri_t_6));
  IOBUF gpio0_tri_iobuf_7
       (.I(gpio0_tri_o_7),
        .IO(gpio0_tri_io[7]),
        .O(gpio0_tri_i_7),
        .T(gpio0_tri_t_7));
  IOBUF gpio0_tri_iobuf_8
       (.I(gpio0_tri_o_8),
        .IO(gpio0_tri_io[8]),
        .O(gpio0_tri_i_8),
        .T(gpio0_tri_t_8));
  IOBUF gpio0_tri_iobuf_9
       (.I(gpio0_tri_o_9),
        .IO(gpio0_tri_io[9]),
        .O(gpio0_tri_i_9),
        .T(gpio0_tri_t_9));
  IOBUF i2c0_scl_iobuf
       (.I(i2c0_scl_o),
        .IO(i2c0_scl_io),
        .O(i2c0_scl_i),
        .T(i2c0_scl_t));
  IOBUF i2c0_sda_iobuf
       (.I(i2c0_sda_o),
        .IO(i2c0_sda_io),
        .O(i2c0_sda_i),
        .T(i2c0_sda_t));
  IOBUF i2c1_scl_iobuf
       (.I(i2c1_scl_o),
        .IO(i2c1_scl_io),
        .O(i2c1_scl_i),
        .T(i2c1_scl_t));
  IOBUF i2c1_sda_iobuf
       (.I(i2c1_sda_o),
        .IO(i2c1_sda_io),
        .O(i2c1_sda_i),
        .T(i2c1_sda_t));
  IOBUF i2c2_scl_iobuf
       (.I(i2c2_scl_o),
        .IO(i2c2_scl_io),
        .O(i2c2_scl_i),
        .T(i2c2_scl_t));
  IOBUF i2c2_sda_iobuf
       (.I(i2c2_sda_o),
        .IO(i2c2_sda_io),
        .O(i2c2_sda_i),
        .T(i2c2_sda_t));
  IOBUF lcd_rgb_tri_iobuf_0
       (.I(lcd_rgb_tri_o_0),
        .IO(lcd_rgb_tri_io[0]),
        .O(lcd_rgb_tri_i_0),
        .T(lcd_rgb_tri_t_0));
  IOBUF lcd_rgb_tri_iobuf_1
       (.I(lcd_rgb_tri_o_1),
        .IO(lcd_rgb_tri_io[1]),
        .O(lcd_rgb_tri_i_1),
        .T(lcd_rgb_tri_t_1));
  IOBUF lcd_rgb_tri_iobuf_10
       (.I(lcd_rgb_tri_o_10),
        .IO(lcd_rgb_tri_io[10]),
        .O(lcd_rgb_tri_i_10),
        .T(lcd_rgb_tri_t_10));
  IOBUF lcd_rgb_tri_iobuf_11
       (.I(lcd_rgb_tri_o_11),
        .IO(lcd_rgb_tri_io[11]),
        .O(lcd_rgb_tri_i_11),
        .T(lcd_rgb_tri_t_11));
  IOBUF lcd_rgb_tri_iobuf_12
       (.I(lcd_rgb_tri_o_12),
        .IO(lcd_rgb_tri_io[12]),
        .O(lcd_rgb_tri_i_12),
        .T(lcd_rgb_tri_t_12));
  IOBUF lcd_rgb_tri_iobuf_13
       (.I(lcd_rgb_tri_o_13),
        .IO(lcd_rgb_tri_io[13]),
        .O(lcd_rgb_tri_i_13),
        .T(lcd_rgb_tri_t_13));
  IOBUF lcd_rgb_tri_iobuf_14
       (.I(lcd_rgb_tri_o_14),
        .IO(lcd_rgb_tri_io[14]),
        .O(lcd_rgb_tri_i_14),
        .T(lcd_rgb_tri_t_14));
  IOBUF lcd_rgb_tri_iobuf_15
       (.I(lcd_rgb_tri_o_15),
        .IO(lcd_rgb_tri_io[15]),
        .O(lcd_rgb_tri_i_15),
        .T(lcd_rgb_tri_t_15));
  IOBUF lcd_rgb_tri_iobuf_16
       (.I(lcd_rgb_tri_o_16),
        .IO(lcd_rgb_tri_io[16]),
        .O(lcd_rgb_tri_i_16),
        .T(lcd_rgb_tri_t_16));
  IOBUF lcd_rgb_tri_iobuf_17
       (.I(lcd_rgb_tri_o_17),
        .IO(lcd_rgb_tri_io[17]),
        .O(lcd_rgb_tri_i_17),
        .T(lcd_rgb_tri_t_17));
  IOBUF lcd_rgb_tri_iobuf_18
       (.I(lcd_rgb_tri_o_18),
        .IO(lcd_rgb_tri_io[18]),
        .O(lcd_rgb_tri_i_18),
        .T(lcd_rgb_tri_t_18));
  IOBUF lcd_rgb_tri_iobuf_19
       (.I(lcd_rgb_tri_o_19),
        .IO(lcd_rgb_tri_io[19]),
        .O(lcd_rgb_tri_i_19),
        .T(lcd_rgb_tri_t_19));
  IOBUF lcd_rgb_tri_iobuf_2
       (.I(lcd_rgb_tri_o_2),
        .IO(lcd_rgb_tri_io[2]),
        .O(lcd_rgb_tri_i_2),
        .T(lcd_rgb_tri_t_2));
  IOBUF lcd_rgb_tri_iobuf_20
       (.I(lcd_rgb_tri_o_20),
        .IO(lcd_rgb_tri_io[20]),
        .O(lcd_rgb_tri_i_20),
        .T(lcd_rgb_tri_t_20));
  IOBUF lcd_rgb_tri_iobuf_21
       (.I(lcd_rgb_tri_o_21),
        .IO(lcd_rgb_tri_io[21]),
        .O(lcd_rgb_tri_i_21),
        .T(lcd_rgb_tri_t_21));
  IOBUF lcd_rgb_tri_iobuf_22
       (.I(lcd_rgb_tri_o_22),
        .IO(lcd_rgb_tri_io[22]),
        .O(lcd_rgb_tri_i_22),
        .T(lcd_rgb_tri_t_22));
  IOBUF lcd_rgb_tri_iobuf_23
       (.I(lcd_rgb_tri_o_23),
        .IO(lcd_rgb_tri_io[23]),
        .O(lcd_rgb_tri_i_23),
        .T(lcd_rgb_tri_t_23));
  IOBUF lcd_rgb_tri_iobuf_3
       (.I(lcd_rgb_tri_o_3),
        .IO(lcd_rgb_tri_io[3]),
        .O(lcd_rgb_tri_i_3),
        .T(lcd_rgb_tri_t_3));
  IOBUF lcd_rgb_tri_iobuf_4
       (.I(lcd_rgb_tri_o_4),
        .IO(lcd_rgb_tri_io[4]),
        .O(lcd_rgb_tri_i_4),
        .T(lcd_rgb_tri_t_4));
  IOBUF lcd_rgb_tri_iobuf_5
       (.I(lcd_rgb_tri_o_5),
        .IO(lcd_rgb_tri_io[5]),
        .O(lcd_rgb_tri_i_5),
        .T(lcd_rgb_tri_t_5));
  IOBUF lcd_rgb_tri_iobuf_6
       (.I(lcd_rgb_tri_o_6),
        .IO(lcd_rgb_tri_io[6]),
        .O(lcd_rgb_tri_i_6),
        .T(lcd_rgb_tri_t_6));
  IOBUF lcd_rgb_tri_iobuf_7
       (.I(lcd_rgb_tri_o_7),
        .IO(lcd_rgb_tri_io[7]),
        .O(lcd_rgb_tri_i_7),
        .T(lcd_rgb_tri_t_7));
  IOBUF lcd_rgb_tri_iobuf_8
       (.I(lcd_rgb_tri_o_8),
        .IO(lcd_rgb_tri_io[8]),
        .O(lcd_rgb_tri_i_8),
        .T(lcd_rgb_tri_t_8));
  IOBUF lcd_rgb_tri_iobuf_9
       (.I(lcd_rgb_tri_o_9),
        .IO(lcd_rgb_tri_io[9]),
        .O(lcd_rgb_tri_i_9),
        .T(lcd_rgb_tri_t_9));
  IOBUF mdio_mdio_iobuf
       (.I(mdio_mdio_o),
        .IO(mdio_mdio_io),
        .O(mdio_mdio_i),
        .T(mdio_mdio_t));
  system system_i
       (.DDR_addr(DDR_addr),
        .DDR_ba(DDR_ba),
        .DDR_cas_n(DDR_cas_n),
        .DDR_ck_n(DDR_ck_n),
        .DDR_ck_p(DDR_ck_p),
        .DDR_cke(DDR_cke),
        .DDR_cs_n(DDR_cs_n),
        .DDR_dm(DDR_dm),
        .DDR_dq(DDR_dq),
        .DDR_dqs_n(DDR_dqs_n),
        .DDR_dqs_p(DDR_dqs_p),
        .DDR_odt(DDR_odt),
        .DDR_ras_n(DDR_ras_n),
        .DDR_reset_n(DDR_reset_n),
        .DDR_we_n(DDR_we_n),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),
        .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio),
        .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb),
        .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
        .aud_adcdat(aud_adcdat),
        .aud_adclrc(aud_adclrc),
        .aud_bclk(aud_bclk),
        .aud_dacdat(aud_dacdat),
        .aud_daclrc(aud_daclrc),
        .aud_mclk(aud_mclk),
        .cmos_data(cmos_data),
        .cmos_href(cmos_href),
        .cmos_pclk(cmos_pclk),
        .cmos_vsync(cmos_vsync),
        .esp_spi_cs_n(esp_spi_cs_n),
        .esp_spi_miso(esp_spi_miso),
        .esp_spi_mosi(esp_spi_mosi),
        .esp_spi_sclk(esp_spi_sclk),
        .gpio0_tri_i({gpio0_tri_i_11,gpio0_tri_i_10,gpio0_tri_i_9,gpio0_tri_i_8,gpio0_tri_i_7,gpio0_tri_i_6,gpio0_tri_i_5,gpio0_tri_i_4,gpio0_tri_i_3,gpio0_tri_i_2,gpio0_tri_i_1,gpio0_tri_i_0}),
        .gpio0_tri_o({gpio0_tri_o_11,gpio0_tri_o_10,gpio0_tri_o_9,gpio0_tri_o_8,gpio0_tri_o_7,gpio0_tri_o_6,gpio0_tri_o_5,gpio0_tri_o_4,gpio0_tri_o_3,gpio0_tri_o_2,gpio0_tri_o_1,gpio0_tri_o_0}),
        .gpio0_tri_t({gpio0_tri_t_11,gpio0_tri_t_10,gpio0_tri_t_9,gpio0_tri_t_8,gpio0_tri_t_7,gpio0_tri_t_6,gpio0_tri_t_5,gpio0_tri_t_4,gpio0_tri_t_3,gpio0_tri_t_2,gpio0_tri_t_1,gpio0_tri_t_0}),
        .i2c0_scl_i(i2c0_scl_i),
        .i2c0_scl_o(i2c0_scl_o),
        .i2c0_scl_t(i2c0_scl_t),
        .i2c0_sda_i(i2c0_sda_i),
        .i2c0_sda_o(i2c0_sda_o),
        .i2c0_sda_t(i2c0_sda_t),
        .i2c1_scl_i(i2c1_scl_i),
        .i2c1_scl_o(i2c1_scl_o),
        .i2c1_scl_t(i2c1_scl_t),
        .i2c1_sda_i(i2c1_sda_i),
        .i2c1_sda_o(i2c1_sda_o),
        .i2c1_sda_t(i2c1_sda_t),
        .i2c2_scl_i(i2c2_scl_i),
        .i2c2_scl_o(i2c2_scl_o),
        .i2c2_scl_t(i2c2_scl_t),
        .i2c2_sda_i(i2c2_sda_i),
        .i2c2_sda_o(i2c2_sda_o),
        .i2c2_sda_t(i2c2_sda_t),
        .lcd_bl(lcd_bl),
        .lcd_clk(lcd_clk),
        .lcd_de(lcd_de),
        .lcd_hs(lcd_hs),
        .lcd_rgb_tri_i({lcd_rgb_tri_i_23,lcd_rgb_tri_i_22,lcd_rgb_tri_i_21,lcd_rgb_tri_i_20,lcd_rgb_tri_i_19,lcd_rgb_tri_i_18,lcd_rgb_tri_i_17,lcd_rgb_tri_i_16,lcd_rgb_tri_i_15,lcd_rgb_tri_i_14,lcd_rgb_tri_i_13,lcd_rgb_tri_i_12,lcd_rgb_tri_i_11,lcd_rgb_tri_i_10,lcd_rgb_tri_i_9,lcd_rgb_tri_i_8,lcd_rgb_tri_i_7,lcd_rgb_tri_i_6,lcd_rgb_tri_i_5,lcd_rgb_tri_i_4,lcd_rgb_tri_i_3,lcd_rgb_tri_i_2,lcd_rgb_tri_i_1,lcd_rgb_tri_i_0}),
        .lcd_rgb_tri_o({lcd_rgb_tri_o_23,lcd_rgb_tri_o_22,lcd_rgb_tri_o_21,lcd_rgb_tri_o_20,lcd_rgb_tri_o_19,lcd_rgb_tri_o_18,lcd_rgb_tri_o_17,lcd_rgb_tri_o_16,lcd_rgb_tri_o_15,lcd_rgb_tri_o_14,lcd_rgb_tri_o_13,lcd_rgb_tri_o_12,lcd_rgb_tri_o_11,lcd_rgb_tri_o_10,lcd_rgb_tri_o_9,lcd_rgb_tri_o_8,lcd_rgb_tri_o_7,lcd_rgb_tri_o_6,lcd_rgb_tri_o_5,lcd_rgb_tri_o_4,lcd_rgb_tri_o_3,lcd_rgb_tri_o_2,lcd_rgb_tri_o_1,lcd_rgb_tri_o_0}),
        .lcd_rgb_tri_t({lcd_rgb_tri_t_23,lcd_rgb_tri_t_22,lcd_rgb_tri_t_21,lcd_rgb_tri_t_20,lcd_rgb_tri_t_19,lcd_rgb_tri_t_18,lcd_rgb_tri_t_17,lcd_rgb_tri_t_16,lcd_rgb_tri_t_15,lcd_rgb_tri_t_14,lcd_rgb_tri_t_13,lcd_rgb_tri_t_12,lcd_rgb_tri_t_11,lcd_rgb_tri_t_10,lcd_rgb_tri_t_9,lcd_rgb_tri_t_8,lcd_rgb_tri_t_7,lcd_rgb_tri_t_6,lcd_rgb_tri_t_5,lcd_rgb_tri_t_4,lcd_rgb_tri_t_3,lcd_rgb_tri_t_2,lcd_rgb_tri_t_1,lcd_rgb_tri_t_0}),
        .lcd_rst(lcd_rst),
        .lcd_vs(lcd_vs),
        .mdio_mdc(mdio_mdc),
        .mdio_mdio_i(mdio_mdio_i),
        .mdio_mdio_o(mdio_mdio_o),
        .mdio_mdio_t(mdio_mdio_t),
        .pl_led_tri_o(pl_led_tri_o),
        .rgmii_rd(rgmii_rd),
        .rgmii_rx_ctl(rgmii_rx_ctl),
        .rgmii_rxc(rgmii_rxc),
        .rgmii_td(rgmii_td),
        .rgmii_tx_ctl(rgmii_tx_ctl),
        .rgmii_txc(rgmii_txc));
endmodule
