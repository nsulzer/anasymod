from anasymod.templ import JinjaTempl
from anasymod.config import EmuConfig
from anasymod.util import back2fwd
from anasymod.probe_config import ProbeConfig
from anasymod.targets import FPGATarget

from math import ceil

class TemplEXECUTE_FPGA_SIM(JinjaTempl):
    def __init__(self, cfg: EmuConfig, target: FPGATarget, start_time: float, stop_time: float, dt: float):
        self.probe_signals = ProbeConfig(probe_cfg_path=target.probe_cfg_path)

        # Necessary variables
        self.bit_file = back2fwd(target.bitfile_path)
        self.ltx_file = back2fwd(target.ltxfile_path)
        self.jtag_freq = str(int(cfg.cfg['jtag_freq']))
        self.device_name = cfg.fpga_board_config.board.cfg['short_part_name']

        self.vio_name = cfg.vivado_config.vio_inst_name
        self.ila_name = cfg.vivado_config.ila_inst_name
        self.output = back2fwd(target.cfg['csv_path'])
        self.ila_reset = cfg.vivado_config.ila_reset
        #tbd remove vio_reset
        self.vio_reset = cfg.vivado_config.vio_reset
        self.window_count = str(cfg.ila_depth//2)

        # calculate decimation ratio
        # note that we have to subtract 1 from decimation ratio due to the FPGA implementation of this feature
        # also note that a minimum decimation ratio of 2 is used since that is unfortunately the minimum window_count
        # allowed
        self.decimation_ratio = ((stop_time-start_time)/dt)/(cfg.ila_depth/2)
        self.decimation_ratio = int(round(self.decimation_ratio)) - 1
        self.decimation_ratio = max(self.decimation_ratio, 2)
        self.decimation_ratio = str(self.decimation_ratio)

        # extract details of time signal
        # note that these are all strings...
        self.time_name, time_width, time_exponent = self.probe_signals.time_signal[0]
        time_exponent = int(time_exponent)

        # determine starting time as an integer value
        self.start_time_int = int(round(start_time*(2**(-time_exponent))))
        self.start_time_int = f"{time_width}'u{self.start_time_int}"

    TEMPLATE_TEXT = '''
# Connect to hardware
open_hw
catch {disconnect_hw_server}
connect_hw_server
set_property PARAM.FREQUENCY {{subst.jtag_freq}} [get_hw_targets]
open_hw_target

# Configure files to be programmed
set my_hw_device [get_hw_devices {{subst.device_name}}*]
set_property PROGRAM.FILE "{{subst.bit_file}}" $my_hw_device
set_property PROBES.FILE "{{subst.ltx_file}}" $my_hw_device
set_property FULL_PROBES.FILE "{{subst.ltx_file}}" $my_hw_device

# Program the device
current_hw_device $my_hw_device
program_hw_devices $my_hw_device
refresh_hw_device $my_hw_device

# ILA setup
set my_hw_ila [get_hw_ilas]
display_hw_ila_data [get_hw_ila_data hw_ila_data_1 -of_objects $my_hw_ila]

# VIO setup
set my_hw_vio [get_hw_vios]
set rst_hw_probe [get_hw_probes *rst* -of_objects $my_hw_vio]

# Trigger setup
# TODO: use starting time as trigger condition
startgroup
set_property CONTROL.CAPTURE_MODE BASIC $my_hw_ila
set_property CONTROL.TRIGGER_POSITION 0 $my_hw_ila
endgroup
set_property TRIGGER_COMPARE_VALUE gt{{subst.start_time_int}} [get_hw_probes {{subst.time_name}} -of_objects $my_hw_ila]

# Capture setup
# TODO: use variable for emu_dec_cmp_probe
# probably always be "2" because unfortunately "1" is not a valid option.
set_property CONTROL.DATA_DEPTH 2 $my_hw_ila
set_property CONTROL.WINDOW_COUNT {{subst.window_count}} $my_hw_ila
set_property CAPTURE_COMPARE_VALUE eq1'b1 [get_hw_probes emu_dec_cmp_probe -of_objects $my_hw_ila]

# VIO: decimation ratio
# TODO: use variable for emu_dec_thr
set_property OUTPUT_VALUE_RADIX UNSIGNED [get_hw_probes vio_gen_i/emu_dec_thr -of_objects $my_hw_vio]
set_property OUTPUT_VALUE {{subst.decimation_ratio}} [get_hw_probes vio_gen_i/emu_dec_thr -of_objects $my_hw_vio]
commit_hw_vio [get_hw_probes vio_gen_i/emu_dec_thr -of_objects $my_hw_vio]

# Radix setup: real numbers
{% for probename, _, _ in subst.probe_signals.analog_signals + subst.probe_signals.time_signal %}
catch {{'{'}}set_property DISPLAY_RADIX SIGNED [get_hw_probes {{probename}}]{{'}'}}
{% endfor %}

# Radix setup: unsigned digital values
# TODO: handle both signed and unsigned digital values
{% for probename, _, _ in subst.probe_signals.digital_signals + subst.probe_signals.reset_signal %}
catch {{'{'}}set_property DISPLAY_RADIX UNSIGNED [get_hw_probes {{probename}}]{{'}'}}
{% endfor %}

# Put design in reset
startgroup
set_property OUTPUT_VALUE 1 $rst_hw_probe
commit_hw_vio $rst_hw_probe
endgroup

# Arm the ILA trigger
run_hw_ila $my_hw_ila

# Take design out of reset
startgroup
set_property OUTPUT_VALUE 0 $rst_hw_probe
commit_hw_vio $rst_hw_probe
endgroup

# Get data from the ILA
wait_on_hw_ila $my_hw_ila
display_hw_ila_data [upload_hw_ila_data $my_hw_ila]

# Write ILA data to a file
write_hw_ila_data -csv_file -force "{{subst.output}}" hw_ila_data_1
'''

def main():
    print(TemplEXECUTE_FPGA_SIM(cfg=EmuConfig()).render())

if __name__ == "__main__":
    main()