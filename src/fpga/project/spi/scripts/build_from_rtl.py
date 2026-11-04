#!/usr/bin/env python3
"""Vivado2020.2 full build reusing the delivered, unchanged generated video IP RTL."""
import argparse
from pathlib import Path
import re
import subprocess
import zipfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--vivado",default="vivado")
a=p.parse_args()
root=Path(__file__).resolve().parents[2]
scripts=root/"spi/scripts"
def run(script,cwd,tag):
    subprocess.run([a.vivado,"-mode","batch","-source",str(script),"-log",str(root/("spi/reports/"+tag+".log")),
                    "-journal",str(root/("spi/reports/"+tag+".jou"))],cwd=cwd,check=True)
run(scripts/"prepare_rtl.tcl",root,"prepare_rtl")
synth=root/"Navigator_7010.runs/synth_1"
s=(synth/"system_wrapper.tcl").read_text()
s=s[s.index("create_project -in_memory"):s.index('OPTRACE "synth_design" END')]
s=re.sub(r'^OPTRACE[^\n]*\n','',s,flags=re.M)
s,n=re.subn(r'compile_c \[get_files .*?\]\s*', '',s,count=1,flags=re.S)
if n!=1: raise RuntimeError("Vivado2020.2 compile_c script format changed; inspect before continuing")
s=s.replace('close [open __synthesis_is_running__ w]','')
s=s.replace('read_xdc dont_touch.xdc','read_xdc {'+(synth/'dont_touch.xdc').as_posix()+'}')
s += '\nreport_utilization -file {spi_synth_utilization.rpt}\nwrite_checkpoint -force -noxdef {system_wrapper.dcp}\nclose_project\nexit\n'
standalone=synth/"synth_generated_rtl.tcl";standalone.write_text(s)
run(standalone,synth,"synth_rtl")
impl=root/"Navigator_7010.runs/impl_1"
run(impl/"system_wrapper.tcl",impl,"impl_rtl")
run(scripts/"finalize.tcl",root,"finalize")
with zipfile.ZipFile(root/"spi/artifacts/asr_esp32_spi.xsa") as archive:
    (root/"spi/artifacts/asr_esp32_spi.bit").write_bytes(archive.read("asr_esp32_spi.bit"))
print("BUILT: "+str(root/"spi/artifacts/asr_esp32_spi.bit"))
