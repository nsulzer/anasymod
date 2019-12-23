from anasymod.generators.gen_api import SVAPI, ModuleInst
from anasymod.templates.templ import JinjaTempl
from anasymod.config import EmuConfig
from anasymod.sim_ctrl.datatypes import DigitalSignal

class ModuleTop(JinjaTempl):
    """
    This is the generator for top.sv.
    """
    def __init__(self, target):
        super().__init__(trim_blocks=True, lstrip_blocks=True)
        scfg = target.str_cfg
        """ :type: StructureConfig """

        #####################################################
        # Add plugin specific includes
        #####################################################

        self.plugin_includes = SVAPI()
        for plugin in target.plugins:
            for include_statement in plugin.include_statements:
                self.plugin_includes.writeln(f'{include_statement}')

        #####################################################
        # Create module interface
        #####################################################
        self.module_ifc = SVAPI()

        module = ModuleInst(api=self.module_ifc, name='top')
        module.add_inputs(scfg.clk_i)
        module.generate_header()

        #####################################################
        # Manage clks
        #####################################################

        # Add clk in signals for simulation case
        self.clk_in_sim_sigs = SVAPI()

        for clk_i in scfg.clk_i:
            self.clk_in_sim_sigs.gen_signal(io_obj=clk_i)

        # Add dbg clk signals
        self.dbg_clk_sigs = SVAPI()
        self.dbg_clk_sigs.gen_signal(io_obj=scfg.dbg_clk)

        # Instantiation of clk_gen wrapper
        self.clk_gen_ifc = SVAPI()
        clk_gen = ModuleInst(api=self.clk_gen_ifc, name='clk_gen')
        clk_gen.add_inputs(scfg.clk_i, connections=scfg.clk_i)
        clk_gen.add_output(scfg.emu_clk_2x, connection=scfg.emu_clk_2x)
        clk_gen.add_output(scfg.dbg_clk, connection=scfg.dbg_clk)
        clk_gen.add_outputs(scfg.clk_independent, connections=scfg.clk_independent)
        clk_gen.generate_instantiation()

        # Absolute path assignments for derived clks
        dt_req_cnt = 0
        gated_clks_cnt = 0
        # ToDo: HIER WEITER: abspath assigns anpassen, passend zu werten in ClkDerived klasse, auch für rst, clk, emu_dt
        self.derived_clk_assigns = SVAPI()
        for k, clk in enumerate(scfg.clk_derived):
            self.derived_clk_assigns.writeln(f'// derived clock: {clk.name}')
            if clk.abspath_emu_dt is not None:
                self.derived_clk_assigns.writeln(f'assign {clk.abspath_emu_dt} = emu_dt;')
            if clk.abspath_emu_clk is not None:
                self.derived_clk_assigns.writeln(f'assign {clk.abspath_emu_clk} = emu_clk;')
            if clk.abspath_emu_rst is not None:
                self.derived_clk_assigns.writeln(f'assign {clk.abspath_emu_rst} = emu_rst;')
            if clk.abspath_dt_req is not None:
                self.derived_clk_assigns.writeln(f'assign dt_req[{dt_req_cnt}] = {clk.abspath_dt_req};')
                dt_req_cnt += 1
            if clk.abspath_gated_clk is not None:
                self.derived_clk_assigns.writeln(f'assign clk_vals[{gated_clks_cnt}] = {clk.abspath_gated_clk_req};')
                self.derived_clk_assigns.writeln(f'assign {clk.abspath_gated_clk} = clks[{gated_clks_cnt}];')
                gated_clks_cnt += 1

        self.num_dt_reqs = dt_req_cnt
        self.num_gated_clks = gated_clks_cnt

        #####################################################
        # Manage Ctrl Module
        #####################################################

        custom_ctrl_ios = scfg.analog_ctrl_inputs + scfg.analog_ctrl_outputs + scfg.digital_ctrl_inputs + \
                          scfg.digital_ctrl_outputs

        ctrl_ios = custom_ctrl_ios + [scfg.dec_thr_ctrl] + [scfg.reset_ctrl]

        ## Instantiate all ctrl signals
        self.inst_itl_ctlsigs = SVAPI()
        for ctrl_io in ctrl_ios:
            self.inst_itl_ctlsigs.gen_signal(io_obj=ctrl_io)

        ## Instantiate ctrl module
        self.sim_ctrl_inst_ifc = SVAPI()
        sim_ctrl_inst = ModuleInst(api=self.sim_ctrl_inst_ifc, name='sim_ctrl_gen')
        sim_ctrl_inst.add_inputs(scfg.analog_ctrl_outputs + scfg.digital_ctrl_outputs,
                                 connections=scfg.analog_ctrl_outputs + scfg.digital_ctrl_outputs)
        sim_ctrl_inst.add_outputs(scfg.analog_ctrl_inputs + scfg.digital_ctrl_inputs + [scfg.dec_thr_ctrl] +
                                  [scfg.reset_ctrl], connections=scfg.analog_ctrl_inputs + scfg.digital_ctrl_inputs +
                                                                 [scfg.dec_thr_ctrl] + [scfg.reset_ctrl])
        # add master clk to ctrl module
        sim_ctrl_inst.add_input(DigitalSignal(name='emu_clk', width=1, abspath=None), connection=DigitalSignal(name='emu_clk', width=1, abspath=None))
        sim_ctrl_inst.generate_instantiation()

        ## Assign custom ctrl signals via abs paths into design
        self.assign_custom_ctlsigs = SVAPI()
        for ctrl_input in scfg.digital_ctrl_inputs + scfg.analog_ctrl_inputs:
            self.assign_custom_ctlsigs.assign_to(io_obj=ctrl_input.abs_path, exp=ctrl_input)

        for ctrl_output in scfg.digital_ctrl_outputs + scfg.analog_ctrl_outputs:
            self.assign_custom_ctlsigs.assign_to(io_obj=ctrl_output, exp=ctrl_output.abs_path)

        #####################################################
        # Manage trace port Module
        ######################################################

        probes = scfg.digital_probes + scfg.analog_probes + [scfg.time_probe]

        ## Instantiate all probe signals
        self.inst_probesigs = SVAPI()
        for probe in probes:
            self.inst_probesigs.gen_signal(probe)

        ## Instantiate traceport module
        self.num_probes = len(probes)
        self.trap_inst_ifc = SVAPI()
        trap_inst = ModuleInst(api=self.trap_inst_ifc, name='trace_port_gen')
        trap_inst.add_inputs(probes, connections=probes)
        trap_inst.add_input(scfg.emu_clk, connection=scfg.emu_clk)
        trap_inst.generate_instantiation()

        ## Assign probe signals via abs paths into design
        self.assign_probesigs = SVAPI()
        for probe in probes:
            self.assign_probesigs.assign_to(io_obj=probe, exp=probe.abs_path)

        #####################################################
        # Instantiate testbench
        #####################################################
        self.tb_inst_ifc = SVAPI()
        tb_inst = ModuleInst(api=self.tb_inst_ifc, name='tb')
        tb_inst.add_inputs(scfg.clk_independent, connections=scfg.clk_independent)
        tb_inst.generate_instantiation()

    TEMPLATE_TEXT = '''
`timescale 1ns/1ps

{{subst.plugin_includes.text}}

`default_nettype none

`ifndef SIMULATION_MODE_MSDSL
{{subst.module_ifc.text}}
`else
module top(
);
`endif // `ifndef SIMULATION_MODE_MSDSL

// Declaration of control signals
{{subst.inst_itl_ctlsigs.text}}

// Declaration of probe signals
{{subst.inst_probesigs.text}}

// create ext_clk signal when running in simulation mode
`ifdef SIMULATION_MODE_MSDSL
    logic ext_clk;
    {% for line in subst.clk_in_sim_sigs.text.splitlines() %}
        {{line}}
    {% endfor %}
`endif // `ifdef SIMULATION_MODE_MSDSL

// debug clk declaration
{{subst.dbg_clk_sigs.text}}

// emulation clock declarations
logic emu_clk, emu_clk_2x;

{% if subst.num_dt_reqs != 0 %}
// declarations for time manager
localparam integer n_dt = {{subst.num_dt_reqs}};
logic signed [((`DT_WIDTH)-1):0] dt_req [n_dt];
logic signed [((`DT_WIDTH)-1):0] emu_dt;
logic signed [((`TIME_WIDTH)-1):0] emu_time;
{% endif %}

{% if subst.num_gated_clks != 0 %}
// declarations for emu clock generator
localparam integer n_clks = {{subst.num_gated_clks}};
logic clk_vals [n_clks];
logic clks [n_clks];
{% endif %}

// instantiate testbench
{{subst.tb_inst_ifc.text}}

// Instantiation of control wrapper
{{subst.sim_ctrl_inst_ifc.text}}

{% if subst.num_probes !=0 %}
// Instantiation of traceport wrapper
{{subst.trap_inst_ifc.text}}
{% endif %}

// Clock generator
{{subst.clk_gen_ifc.text}}

{% if subst.num_gated_clks != 0 %}
// Emu Clk generator
gen_emu_clks  #(.n(n_clks)) gen_emu_clks_i (
    .emu_clk_2x(emu_clk_2x),
    .emu_clk(emu_clk),
    .clk_vals(clk_vals),
    .clks(clks)
);
{% else %}
// generate emu_clk
logic emu_clk_unbuf = 0;
always @(posedge emu_clk_2x) begin
    emu_clk_unbuf <= ~emu_clk_unbuf;
end
`ifndef SIMULATION_MODE_MSDSL
    BUFG buf_emu_clk (.I(emu_clk_unbuf), .O(emu_clk));
`else
    assign emu_clk = emu_clk_unbuf;
`endif
{% endif %}

{% if subst.num_dt_reqs != 0 %}
// Time manager
time_manager  #(
    .n(n_dt),
    .width(`DT_WIDTH),
    .time_width(`TIME_WIDTH)
) time_manager_i (
    .dt_req(dt_req),
    .emu_dt(emu_dt),
    .emu_clk(emu_clk),
    .emu_rst(emu_rst),
    .emu_time_probe(emu_time_probe)
);
{% else %}
// make emu time probe
//ToDo: Get rid of emu_time_probe, this is not necessary anymore
`COPY_FORMAT_REAL(emu_time, emu_time_next);
`COPY_FORMAT_REAL(emu_time, emu_time_dt);
`ASSIGN_CONST_REAL(`DT_MSDSL, emu_time_dt);
`ADD_INTO_REAL(emu_time, emu_time_dt, emu_time_next);
`MEM_INTO_ANALOG(emu_time_next, emu_time, 1'b1, `CLK_MSDSL, `RST_MSDSL, 0);
`PROBE_TIME(emu_time);
{% endif %}
// make reset and decimation probes
`MAKE_RESET_PROBE;
`MAKE_DEC_PROBE;

// Assignment for derived clks
{{subst.derived_clk_assigns.text}}

// Assignment of custom control signals via absolute paths to design signals
{{subst.assign_custom_ctlsigs.text}}

{% if subst.num_probes !=0 %}
// Assignment of probe signals via absolute paths to design signals
{{subst.assign_probesigs.text}}
{% endif %}

// simulation control
`ifdef SIMULATION_MODE_MSDSL
    // stop simulation after some time
    initial begin
        #((`TSTOP_MSDSL)*1s);
        $finish;
    end

    // dump waveforms to a specified VCD file
    `define ADD_QUOTES_TO_MACRO(macro) `"macro`"
    initial begin
        $dumpfile(`ADD_QUOTES_TO_MACRO(`VCD_FILE_MSDSL));
    end
`endif // `ifdef SIMULATION_MODE_MSDSL

endmodule

`default_nettype wire
'''

def main():
    print(ModuleTop(target=FPGATarget(prj_cfg=EmuConfig(root='test', cfg_file=''))).render())

if __name__ == "__main__":
    main()