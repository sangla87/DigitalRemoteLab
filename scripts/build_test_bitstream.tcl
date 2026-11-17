# Genera el .bit del diseño de prueba con Vivado en modo batch (sin interfaz).
#
# Uso (desde la raíz del repositorio):
#   source /tools/Xilinx/Vivado/2022.2/settings64.sh
#   vivado -mode batch -nojournal -nolog -source scripts/build_test_bitstream.tcl \
#       -tclargs nexys4ddr            ;# o: nexys4
#
# El resultado queda en build/<placa>/test_board.bit (o en la ruta que se pase
# como segundo argumento). Después: drl program build/<placa>/test_board.bit

if {$argc < 1} {
    puts "ERROR: indica la placa: nexys4 o nexys4ddr"
    exit 1
}

set board [lindex $argv 0]
set root  [file normalize [file join [file dirname [info script]] ..]]
set xdc   [file join $root hdl test_board $board.xdc]

if {![file exists $xdc]} {
    puts "ERROR: no existe $xdc (placas disponibles: nexys4, nexys4ddr)"
    exit 1
}

if {$argc > 1} {
    set out [file normalize [lindex $argv 1]]
} else {
    set out [file join $root build $board test_board.bit]
}
file mkdir [file dirname $out]

# La Nexys 4, la Nexys 4 DDR y la Nexys A7-100T llevan la misma FPGA.
set part xc7a100tcsg324-1

read_vhdl [file join $root hdl test_board test_board.vhd]
read_xdc  $xdc

synth_design -top test_board -part $part
opt_design
place_design
route_design

# Muestra el uso de recursos y el timing en el terminal.
report_utilization -hierarchical -hierarchical_depth 1
report_timing_summary -max_paths 1

write_bitstream -force $out
puts "OK: bitstream generado en $out"
