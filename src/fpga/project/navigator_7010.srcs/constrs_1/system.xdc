# pl led
set_property -dict {PACKAGE_PIN H15 IOSTANDARD LVCMOS33} [get_ports {pl_led_tri_o[0]}]
set_property -dict {PACKAGE_PIN L15 IOSTANDARD LVCMOS33} [get_ports {pl_led_tri_o[1]}]

# GPIO0
#核心板 pl led 54
set_property -dict {PACKAGE_PIN J16 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[0]}]
#pl key 55-56
set_property -dict {PACKAGE_PIN L14 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[1]}]
set_property -dict {PACKAGE_PIN K16 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[2]}]
#touch key 57
set_property -dict {PACKAGE_PIN F16 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[3]}]
#beeper 58
set_property -dict {PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[4]}]
#lcd touch rst 59
set_property -dict {PACKAGE_PIN M19 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[5]}]
#lcd touch int 60
set_property -dict {PACKAGE_PIN U19 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[6]}]
#cam pwdn 61
set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[7]}]
#cam rst 62
set_property -dict {PACKAGE_PIN P14 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[8]}]
#pl pyh rst 63
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[9]}]
#hdmi hpd 64
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33} [get_ports {gpio0_tri_io[10]}]

# CAN 0

# 音频
set_property -dict {PACKAGE_PIN M17 IOSTANDARD LVCMOS33} [get_ports aud_adcdat]
set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33} [get_ports aud_adclrc]
set_property -dict {PACKAGE_PIN M18 IOSTANDARD LVCMOS33} [get_ports aud_bclk]
set_property -dict {PACKAGE_PIN G17 IOSTANDARD LVCMOS33} [get_ports aud_dacdat]
set_property -dict {PACKAGE_PIN G18 IOSTANDARD LVCMOS33} [get_ports aud_daclrc]
set_property -dict {PACKAGE_PIN E19 IOSTANDARD LVCMOS33} [get_ports aud_mclk]

# LCD
set_property -dict {PACKAGE_PIN P19 IOSTANDARD LVCMOS33} [get_ports lcd_clk]
set_property -dict {PACKAGE_PIN U20 IOSTANDARD LVCMOS33} [get_ports lcd_de]
set_property -dict {PACKAGE_PIN N18 IOSTANDARD LVCMOS33} [get_ports lcd_hs]
set_property -dict {PACKAGE_PIN T20 IOSTANDARD LVCMOS33} [get_ports lcd_vs]
#PWM_0
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports {lcd_bl[0]}]
#lcd rst
set_property -dict {PACKAGE_PIN L17 IOSTANDARD LVCMOS33} [get_ports lcd_rst]

#LCD Red
set_property -dict {PACKAGE_PIN W18 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[0]}]
set_property -dict {PACKAGE_PIN W19 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[1]}]
set_property -dict {PACKAGE_PIN R16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[2]}]
set_property -dict {PACKAGE_PIN R17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[3]}]
set_property -dict {PACKAGE_PIN W20 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[4]}]
set_property -dict {PACKAGE_PIN V20 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[5]}]
set_property -dict {PACKAGE_PIN P18 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[6]}]
set_property -dict {PACKAGE_PIN N17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[7]}]
#LCD Green
set_property -dict {PACKAGE_PIN V17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[8]}]
set_property -dict {PACKAGE_PIN V18 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[9]}]
set_property -dict {PACKAGE_PIN T17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[10]}]
set_property -dict {PACKAGE_PIN R18 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[11]}]
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[12]}]
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[13]}]
set_property -dict {PACKAGE_PIN P15 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[14]}]
set_property -dict {PACKAGE_PIN P16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[15]}]
#LCD Blue
set_property -dict {PACKAGE_PIN V16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[16]}]
set_property -dict {PACKAGE_PIN W16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[17]}]
set_property -dict {PACKAGE_PIN T14 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[18]}]
set_property -dict {PACKAGE_PIN T15 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[19]}]
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[20]}]
set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[21]}]
set_property -dict {PACKAGE_PIN T16 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[22]}]
set_property -dict {PACKAGE_PIN U17 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb_tri_io[23]}]

# PL网口
set_property -dict {PACKAGE_PIN F20 IOSTANDARD LVCMOS33} [get_ports mdio_mdc]
set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS33} [get_ports mdio_mdio_io]

set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports rgmii_rxc]
set_property -dict {PACKAGE_PIN E17 IOSTANDARD LVCMOS33} [get_ports rgmii_rx_ctl]
set_property -dict {PACKAGE_PIN B19 IOSTANDARD LVCMOS33} [get_ports {rgmii_rd[0]}]
set_property -dict {PACKAGE_PIN A20 IOSTANDARD LVCMOS33} [get_ports {rgmii_rd[1]}]
set_property -dict {PACKAGE_PIN H17 IOSTANDARD LVCMOS33} [get_ports {rgmii_rd[2]}]
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports {rgmii_rd[3]}]

set_property -dict {PACKAGE_PIN B20 IOSTANDARD LVCMOS33} [get_ports rgmii_txc]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD LVCMOS33} [get_ports rgmii_tx_ctl]
set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVCMOS33} [get_ports {rgmii_td[0]}]
set_property -dict {PACKAGE_PIN C20 IOSTANDARD LVCMOS33} [get_ports {rgmii_td[1]}]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports {rgmii_td[2]}]
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {rgmii_td[3]}]

create_clock -period 8.000 -name rgmii_rxc [get_ports rgmii_rxc]

# I2C
# eeprom & rtc & audio iic
set_property -dict {PACKAGE_PIN E18 IOSTANDARD LVCMOS33} [get_ports i2c0_scl_io]
set_property -dict {PACKAGE_PIN F17 IOSTANDARD LVCMOS33} [get_ports i2c0_sda_io]
#lcd touch & hdmi iic
set_property -dict {PACKAGE_PIN R19 IOSTANDARD LVCMOS33} [get_ports i2c1_scl_io]
set_property -dict {PACKAGE_PIN P20 IOSTANDARD LVCMOS33} [get_ports i2c1_sda_io]
#cmos iic
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports i2c2_scl_io]
set_property -dict {PACKAGE_PIN T11 IOSTANDARD LVCMOS33} [get_ports i2c2_sda_io]

# HDMI
set_property -dict {PACKAGE_PIN J20 IOSTANDARD TMDS_33} [get_ports {tmds_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {tmds_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G19 IOSTANDARD TMDS_33} [get_ports {tmds_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports tmds_tmds_clk_p]
#set_property IOSTANDARD LVCMOS33 [get_ports tmds_oen]
#set_property PACKAGE_PIN G17 [get_ports tmds_oen]
#set_property PULLUP true [get_ports tmds_oen]

# 串口

# 单目摄像头
#create_clock -period 7.8125 -name cmos_pclk [get_ports cmos_pclk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cmos_pclk_IBUF]

set_property -dict {PACKAGE_PIN T12 IOSTANDARD LVCMOS33} [get_ports cmos_href]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports cmos_pclk]
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33} [get_ports cmos_vsync]

set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} [get_ports {cmos_data[0]}]
set_property -dict {PACKAGE_PIN U13 IOSTANDARD LVCMOS33} [get_ports {cmos_data[1]}]
set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} [get_ports {cmos_data[2]}]
set_property -dict {PACKAGE_PIN U15 IOSTANDARD LVCMOS33} [get_ports {cmos_data[3]}]
set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33} [get_ports {cmos_data[4]}]
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {cmos_data[5]}]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {cmos_data[6]}]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {cmos_data[7]}]

set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks -of_objects [get_pins system_i/hdmi_out/clk_wiz_dyn/inst/CLK_CORE_DRP_I/clk_inst/mmcm_adv_inst/CLKOUT1]]

set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks clk_fpga_1]
set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks -of_objects [get_pins system_i/hdmi_out/clk_wiz_dyn/inst/CLK_CORE_DRP_I/clk_inst/mmcm_adv_inst/CLKOUT0]]

set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks -of_objects [get_pins system_i/clk_wiz_0/inst/CLK_CORE_DRP_I/clk_inst/mmcm_adv_inst/CLKOUT0]]
# SPI0 master, 3.3V, J3 pins 1..4. Remove P1/P3 peripheral jumpers.
set_property -dict {PACKAGE_PIN K14 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports esp_spi_sclk]
set_property -dict {PACKAGE_PIN M15 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports esp_spi_mosi]
set_property -dict {PACKAGE_PIN J14 IOSTANDARD LVCMOS33 PULLUP true SLEW SLOW DRIVE 8} [get_ports esp_spi_cs_n]
set_property -dict {PACKAGE_PIN L16 IOSTANDARD LVCMOS33 PULLDOWN true} [get_ports esp_spi_miso]
# EMIO GPIO11 = PS GPIO line65. ATK MODULE U4 pin2, KEY; not its 5V VCC pin.
set_property -dict {PACKAGE_PIN G14 IOSTANDARD LVCMOS33 PULLDOWN true} [get_ports {gpio0_tri_io[11]}]
