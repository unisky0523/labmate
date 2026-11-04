set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
open_project [file join $root Navigator_7010.xpr]
if {[file isfile [file join $root spi reference asr_postroute.dcp]]} {set_property INCREMENTAL_CHECKPOINT [file join $root spi reference asr_postroute.dcp] [get_runs impl_1]}
set runroot [file join $root Navigator_7010.runs impl_1]
open_checkpoint [file join $runroot system_wrapper_postroute_physopt.dcp]
set reports [file join $root spi reports]
report_utilization -file [file join $reports utilization.rpt]
report_timing_summary -file [file join $reports timing.rpt]
report_drc -file [file join $reports drc.rpt]
report_io -file [file join $reports io.rpt]
set sf [open [file join $reports build_result.txt] w]
puts $sf "Vivado [version -short]. Frozen, unchanged video-IP RTL reused. Full synthesis/place/route performed."
puts $sf "Hardware test NOT performed. External SPI timing/ESP32 operation must be measured on board."
foreach kind {max min} {
 set paths [get_timing_paths -delay_type $kind -max_paths 1]
 if {![llength $paths]} {error "No $kind timing path"}
 set slack [get_property SLACK [lindex $paths 0]]
 puts $sf "$kind constrained slack = $slack ns"
 if {$slack < 0} {close $sf; error "Timing failed; do not release bitstream"}
}
close $sf
set artifacts [file join $root spi artifacts]
file copy -force [file join $runroot system_wrapper.bit] [file join $artifacts asr_esp32_spi.bit]
write_hw_platform -fixed -include_bit -force [file join $artifacts asr_esp32_spi.xsa]
close_project
exit
