# Run on an independent copy of the verified ASR project, once.
set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
if {![llength [get_projects -quiet]]} {open_project [file join $root Navigator_7010.xpr]}
set_property source_mgmt_mode All [current_project]
add_files -norecurse [file join $root spi rtl spi_emio_master_io.v]
update_compile_order -fileset sources_1
open_bd_design [get_files */system.bd]
if {[llength [get_bd_cells -quiet esp32_spi_io]]} {error "SPI already added; use build.tcl"}
set ps [get_bd_cells processing_system7_0]
# UART1 (board UART2) and CAN0 give four J3 pins back; UART0 USB console stays.
foreach name {uart1 can0} {delete_bd_objs [get_bd_intf_ports $name]}
set_property -dict [list CONFIG.PCW_UART1_PERIPHERAL_ENABLE {0} CONFIG.PCW_CAN0_PERIPHERAL_ENABLE {0} CONFIG.PCW_SPI0_PERIPHERAL_ENABLE {1} CONFIG.PCW_SPI0_SPI0_IO {EMIO} CONFIG.PCW_SPI0_GRP_SS0_ENABLE {1} CONFIG.PCW_SPI_PERIPHERAL_FREQMHZ {166.666666} CONFIG.PCW_GPIO_EMIO_GPIO_IO {12}] $ps
set io [create_bd_cell -type module -reference spi_emio_master_io esp32_spi_io]
foreach signal {SCLK MOSI} name {sclk mosi} {
 foreach s {O T} t {o t} {connect_bd_net [get_bd_pins $ps/SPI0_${signal}_$s] [get_bd_pins $io/${name}_$t]}
 connect_bd_net [get_bd_pins $io/${name}_i] [get_bd_pins $ps/SPI0_${signal}_I]
}
foreach a {cs_o cs_t miso_i ss_i} b {SS_O SS_T MISO_I SS_I} {
 connect_bd_net [get_bd_pins $io/$a] [get_bd_pins $ps/SPI0_$b]
}
foreach name {esp_spi_sclk esp_spi_mosi esp_spi_cs_n} {
 create_bd_port -dir IO $name
 connect_bd_net [get_bd_pins $io/$name] [get_bd_ports $name]
}
create_bd_port -dir I esp_spi_miso
connect_bd_net [get_bd_pins $io/esp_spi_miso] [get_bd_ports esp_spi_miso]
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $root spi reports integrated_design.tcl]
generate_target all [get_files */system.bd]
make_wrapper -files [get_files */system.bd] -top
update_compile_order -fileset sources_1
report_ip_status -file [file join $root spi reports ip_status.rpt]
close_project
exit
