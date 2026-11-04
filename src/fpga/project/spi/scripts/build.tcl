set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
if {[version -short] ne "2020.2"} {error "Use Vivado 2020.2"}
open_project [file join $root Navigator_7010.xpr]
if {[file isfile [file join $root spi reference asr_postroute.dcp]]} {set_property INCREMENTAL_CHECKPOINT [file join $root spi reference asr_postroute.dcp] [get_runs impl_1]}
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
open_bd_design [get_files */system.bd]
validate_bd_design
save_bd_design
generate_target all [get_files */system.bd]
make_wrapper -files [get_files */system.bd] -top
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {![string match {*write_bitstream Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Implementation failed"}
open_run impl_1
set reports [file join $root spi reports]
report_utilization -file [file join $reports utilization.rpt]
report_timing_summary -file [file join $reports timing.rpt]
report_drc -file [file join $reports drc.rpt]
report_io -file [file join $reports io.rpt]
set sf [open [file join $reports build_result.txt] w]
puts $sf "Vivado [version -short]. Hardware test NOT performed."
foreach kind {max min} {
 set paths [get_timing_paths -delay_type $kind -max_paths 1]
 if {![llength $paths]} {error "No $kind timing path"}
 set slack [get_property SLACK [lindex $paths 0]]
 puts $sf "$kind slack = $slack ns"
 if {$slack < 0} {close $sf; error "Timing failed"}
}
close $sf
set artifacts [file join $root spi artifacts]
file copy -force [file join [get_property DIRECTORY [get_runs impl_1]] system_wrapper.bit] [file join $artifacts asr_esp32_spi.bit]
write_hw_platform -fixed -include_bit -force [file join $artifacts asr_esp32_spi.xsa]
close_project
exit
