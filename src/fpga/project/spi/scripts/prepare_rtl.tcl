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
launch_runs impl_1 -to_step write_bitstream -scripts_only
close_project
exit
