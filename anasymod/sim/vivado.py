import re
from anasymod.sim.sim import Simulator
from anasymod.generators.vivado import VivadoTCLGenerator
from anasymod.util import back2fwd

class VivadoSimulator(Simulator):
    def simulate(self):
        # set up the simulation commands
        v = VivadoTCLGenerator(target=self.target)

        # create a new project
        v.create_project(project_name=self.cfg.vivado_config.project_name,
                         project_directory=self.target.project_root,
                         force=True)

        # add all source files to the project (including header files)
        v.add_project_sources(content=self.target.content)

        # define the top module
        v.set_property('top', f"{{{self.target.cfg.top_module}}}", '[get_filesets {sim_1 sources_1}]')

        # set define variables
        v.add_project_defines(content=self.target.content, fileset='[get_filesets {sim_1 sources_1}]')

        # add include directories
        v.add_include_dirs(content=self.target.content, objects='[get_filesets {sim_1 sources_1}]')

        # if desired, treat Verilog (*.v) files as SystemVerilog (*.sv)
        if self.target.prj_cfg.cfg.treat_v_as_sv:
            v.writeln('set_property file_type SystemVerilog [get_files -filter {FILE_TYPE == Verilog}]')

        # read user-provided TCL scripts
        v.writeln('# Custom user-provided TCL scripts')
        for tcl_file in v.target.content.tcl_files:
            for file in tcl_file.files:
                v.writeln(f'source "{back2fwd(file)}"')

        # upgrade IPs as necessary
        v.writeln('if {[get_ips] ne ""} {')
        v.writeln('    upgrade_ip [get_ips]')
        v.writeln('}')

        # generate all IPs
        v.writeln('generate_target all [get_ips]')

        # launch the simulation
        v.set_property('{xsim.simulate.runtime}', '{-all}', '[get_fileset sim_1]')
        v.writeln('launch_simulation')

        # add any additional user-supplied flags
        for flag in self.flags:
            v.writeln(str(flag))

        # run the simulation
        v.run(filename='vivado_sim.tcl', err_str=re.compile('^(Error|Fatal):'))
