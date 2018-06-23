#!/usr/bin/env python
"""
This script provides a simplified interface to the AbiPy factory functions.
For a more flexible interface please use the AbiPy objects to generate input files and workflows.
"""
from __future__ import unicode_literals, division, print_function, absolute_import

import sys
import os
import argparse

from monty.termcolor import cprint
from monty.functools import prof_main
from abipy import abilab
from abipy.abio import factories
from abipy.abio.inputs import AnaddbInput
from abipy.dfpt.ddb import DdbFile


def get_structure(options):
    """Return structure object either from file or from the material project database."""
    if os.path.exists(options.filepath):
        return abilab.Structure.from_file(options.filepath)

    elif options.filepath.startswith("mp-"):
        return abilab.Structure.from_mpid(options.filepath, final=True,
                                          api_key=options.mapi_key, endpoint=options.endpoint)

    raise TypeError("Don't know how to extract structure object from %s" % options.filepath)


def get_pseudotable(options):
    """Return PseudoTable object."""
    if options.pseudos is not None:
        from abipy.flowtk import PseudoTable
        return PseudoTable.as_table(options.pseudos)

    try:
        from pseudo_dojo import OfficialTables
    except ImportError as exc:
        print("PseudoDojo package not installed. Please install it with `pip install pseudo_dojo`")
        print("or use `--pseudos FILE_LIST` to specify the pseudopotentials to use.")
        raise exc

    dojo_tables = OfficialTables()
    if options.usepaw:
        raise NotImplementedError("PAW table is missing")
        #pseudos = dojo_tables["ONCVPSP-PBE-PDv0.2-accuracy"]
    else:
        pseudos = dojo_tables["ONCVPSP-PBE-PDv0.2-accuracy"]

    print("Using pseudos from PseudoDojo table", repr(pseudos))
    return pseudos


def finalize(obj, options):
    if options.mnemonics: obj.set_mnemonics(True)
    print(obj)
    print("\n")
    print("# This input file template has been automatically generated by the abinp.py script.")
    print("# Several input parameters have default values that might not be suitable for you particular calculation.")
    print("# Please check the input file, make sure you understand what's happening and modify the template according to your needs")
    return 0


def build_abinit_input_from_file(options, **abivars):
    """
    Build and return an AbinitInput instance from filepath.

    abivars are optional variables that will be added to the input.
    """
    from abipy.abio.abivars import AbinitInputFile
    abifile = AbinitInputFile(options.filepath)
    pseudos = get_pseudotable(options)
    jdtset = options.jdtset
    # Get vars from input
    abi_kwargs = abifile.datasets[jdtset - 1].get_vars()
    if abifile.ndtset != 1:
        cprint("# Input file contains %s datasets, will select jdtset index %s:" %
               (abifile.ndtset, jdtset), "yellow")
        abi_kwargs["jdtset"] = jdtset

    # Add input abivars (if any).
    abi_kwargs.update(abivars)

    return abilab.AbinitInput(abifile.structure, pseudos, pseudo_dir=None, comment=None, decorators=None, abi_args=None,
                              abi_kwargs=abi_kwargs, tags=None)


def abinp_validate(options):
    """Validate Abinit input file."""
    inp = build_abinit_input_from_file(options)
    r = inp.abivalidate()
    if r.retcode == 0:
        print("Validation completed succesfully.")
    else:
        print(r.log_file, r.stderr_file)

    return r.retcode


def abinp_autoparal(options):
    """Compute autoparal configurations."""
    inp = build_abinit_input_from_file(options)
    pconfs = inp.abiget_autoparal_pconfs(options.max_ncpus, autoparal=1, workdir=None, manager=None, verbose=options.verbose)
    print(pconfs)
    return 0


def abinp_abispg(options):
    """Call Abinit with chkprim = 0 to find space group."""
    inp = build_abinit_input_from_file(options, chkprim=0, mem_test=0)
    r = inp.abivalidate()
    if r.retcode != 0:
        print(r.log_file, r.stderr_file)
        return r.retcode

    try:
        out = abilab.abiopen(r.output_file.path)
    except Exception as exc:
        print("Error while trying to parse output file:", r.output_file.path)
        print("Exception:\n", exc)
        return 1

    #print(out)
    structure = out.initial_structure

    # Call spglib to get spacegroup if Abinit spacegroup is not available.
    # Return string with full information about crystalline structure i.e.
    # space group, point group, wyckoff positions, equivalent sites.
    print(structure.spget_summary(verbose=options.verbose))
    if options.verbose:
        print(structure.abi_spacegroup.to_string(verbose=options.verbose))

    return 0


def abinp_ibz(options):
    """Get k-points in the irreducible weights."""
    inp = build_abinit_input_from_file(options)
    ibz = inp.abiget_ibz(ngkpt=None, shiftk=None, kptopt=None, workdir=None, manager=None)

    nkibz = len(ibz.points)
    print("kptopt 0 nkpt ", nkibz)
    print("kpts")
    for i, (k, w) in enumerate(zip(ibz.points, ibz.weights)):
        print("%12.8f  %12.8f  %12.8f  # index: %d, weigth: %10.8f" % (k[0], k[1], k[2], i + 1, w))

    print("\nwtk")
    for i, w in enumerate(ibz.weights):
        print("%10.8f  # index: %d" % (w, i + 1))

    return 0


def abinp_phperts(options):
    """Get list of phonon perturbations."""
    inp = build_abinit_input_from_file(options)
    qpt = None if "qpt" in inp else [0, 0, 0]
    perts = inp.abiget_irred_phperts(qpt=qpt)
    print(perts)

    return 0


def abinp_gs(options):
    """Build Abinit input for ground-state calculation."""
    structure = abilab.Structure.from_file(options.filepath)
    pseudos = get_pseudotable(options)
    gsinp = factories.gs_input(structure, pseudos,
                               kppa=None, ecut=None, pawecutdg=None, scf_nband=None,
                               accuracy="normal", spin_mode="unpolarized",
                               smearing="fermi_dirac:0.1 eV", charge=0.0, scf_algorithm=None)

    return finalize(gsinp, options)


def abinp_ebands(options):
    """Build Abinit input for band structure calculations."""
    structure = get_structure(options)
    pseudos = get_pseudotable(options)
    multi = factories.ebands_input(structure, pseudos,
                 kppa=None, nscf_nband=None, ndivsm=15,
                 ecut=None, pawecutdg=None, scf_nband=None, accuracy="normal", spin_mode="unpolarized",
                 smearing="fermi_dirac:0.1 eV", charge=0.0, scf_algorithm=None, dos_kppa=None)

    # Add getwfk variables.
    for inp in multi[1:]:
        inp["getwfk"] = 1

    return finalize(multi, options)


def abinp_phonons(options):
    """Build Abinit input for phonon calculations."""
    structure = get_structure(options)
    pseudos = get_pseudotable(options)

    gsinp = factories.gs_input(structure, pseudos,
                               kppa=None, ecut=None, pawecutdg=None, scf_nband=None,
                               accuracy="normal", spin_mode="unpolarized",
                               smearing="fermi_dirac:0.1 eV", charge=0.0, scf_algorithm=None)

    multi = factories.phonons_from_gsinput(gsinp, ph_ngqpt=None, qpoints=None, with_ddk=True, with_dde=True, with_bec=False,
                                           ph_tol=None, ddk_tol=None, dde_tol=None, wfq_tol=None, qpoints_to_skip=None)

    # Add getwfk variables.
    for inp in multi[1:]:
        inp["getwfk"] = 1

    return finalize(multi, options)


def abinp_g0w0(options):
    """Generate input files for G0W0 calculations."""
    structure = get_structure(options)
    pseudos = get_pseudotable(options)
    kppa, nscf_nband, ecuteps, ecutsigx = 1000, 100, 4, 12

    multi = factories.g0w0_with_ppmodel_inputs(structure, pseudos,
                             kppa, nscf_nband, ecuteps, ecutsigx,
                             ecut=None, pawecutdg=None,
                             accuracy="normal", spin_mode="unpolarized", smearing="fermi_dirac:0.1 eV",
                             ppmodel="godby", charge=0.0, scf_algorithm=None, inclvkb=2, scr_nband=None,
                             sigma_nband=None, gw_qprange=1)

    # Add getwfk and getscr variables.
    for inp in multi[1:]:
        inp["getwfk"] = -1
    multi[-1]["getscr"] = -1

    return finalize(multi, options)


def abinp_anaph(options):
    """Build Anaddb input file for the computation of phonon bands DOS."""
    ddb = DdbFile(options.filepath)
    nqsmall = 10
    inp = AnaddbInput.phbands_and_dos(ddb.structure, ddb.guessed_ngqpt, nqsmall, ndivsm=20, q1shft=(0, 0, 0),
        qptbounds=None, asr=2, chneut=0, dipdip=1, dos_method="tetra", lo_to_splitting=False,
        anaddb_args=None, anaddb_kwargs=None)

    return finalize(inp, options)


def abinp_wannier90(options):
    """Build wannier90 template input file from Abinit input/output file."""
    from abipy.wannier90.win import Wannier90Input
    inp = Wannier90Input.from_abinit_file(options.filepath)
    return finalize(inp, options)



def get_epilog():
    return r"""
Usage example:

######################
# Require Abinit Input
######################

    abinp.py validate run.abi       # Call abinit to validate run.abi input file
    abinp.py abispg run.abi         # Call abinit to get space group information.
    abinp.py autoparal run.abi      # Call abinit to get list of autoparal configurations.
    abinp.py ibz run.abi            # Call abinit to get list of k-points in the IBZ.
    abinp.py phperts run.abi        # Call abinit to get list of atomic perturbations for phonons.

########################
# Abinit Input Factories
########################

    abinp.py gs si.cif > run.abi    # Build input for GS run for silicon structure read from CIF file.
                                    # Redirect output to run.abi.
    abinp.py ebands out_GSR.nc      # Build input for SCF + NSCF run with structure read from GSR.nc file.
    abinp.py ebands mp-149          # Build input for SCF+NSCF run with (relaxed) structure taken from the
                                    # materials project database. Requires internet connect and MAPI_KEY.
    abinp.py phonons POSCAR         # Build input for GS + DFPT calculation of phonons with DFPT.
    abinp.py phonons out_HIST.nc    # Build input for G0W0 run with (relaxed) structure read from HIST.nc file.

########################
# Anaddb Input Factories
########################

    abinp.py anaph out_DDB          # Build anaddb input file for phonon bands + DOS from DDB file.


Note that one can use pass any file providing a pymatgen structure
e.g. Abinit netcdf files, CIF files, POSCAR, ...
Use `abinp.py --help` for help and `abinp.py COMMAND --help` to get the documentation for `COMMAND`.
Use `-v` to increase verbosity level (can be supplied multiple times e.g -vv).

CAVEAT: This script provides a simplified interface to the AbiPy factory functions.
For a more flexible interface please use the AbiPy objects to generate input files and workflows.
"""


def get_parser(with_epilog=False):
    """Build parser."""
    # Parent parser for common options.
    copts_parser = argparse.ArgumentParser(add_help=False)
    copts_parser.add_argument('-v', '--verbose', default=0, action='count', # -vv --> verbose=2
        help='verbose, can be supplied multiple times to increase verbosity')
    copts_parser.add_argument('--loglevel', default="ERROR", type=str,
        help="Set the loglevel. Possible values: CRITICAL, ERROR (default), WARNING, INFO, DEBUG")
    copts_parser.add_argument("--mapi-key", default=None,
        help="Pymatgen MAPI_KEY used if mp identifier is used to select structure.\n"
             "Use value in .pmgrc.yaml if not specified.")
    copts_parser.add_argument("--endpoint", help="Pymatgen database.", default="https://www.materialsproject.org/rest/v2")

    copts_parser.add_argument("-m", '--mnemonics', default=False, action="store_true",
        help="Print brief description of input variables in the input file.")
    copts_parser.add_argument('--usepaw', default=False, action="store_true",
        help="Use PAW pseudos instead of norm-conserving.")

    # Parent parser for command options operating on Abinit input files.
    abiinput_parser = argparse.ArgumentParser(add_help=False)
    abiinput_parser.add_argument('--jdtset', default=1, type=int,
        help="jdtset index. Used to select the dataset index when the input file " +
             "contains more than one dataset.")
    abiinput_parser.add_argument("-p", '--pseudos', nargs="+", default=None, help="List of pseudopotentials")

    # Parent parser for commands that need to know the filepath for the structure.
    path_selector = argparse.ArgumentParser(add_help=False)
    path_selector.add_argument('filepath', type=str,
        help="File with the crystalline structure (netcdf, cif, POSCAR, input files ...)")

    parser = argparse.ArgumentParser(epilog=get_epilog() if with_epilog else "",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--loglevel', default="ERROR", type=str,
        help="Set the loglevel. Possible values: CRITICAL, ERROR (default), WARNING, INFO, DEBUG")
    parser.add_argument('-V', '--version', action='version', version=abilab.__version__)
    parser.add_argument('-v', '--verbose', default=0, action='count', # -vv --> verbose=2
        help='verbose, can be supplied multiple times to increase verbosity')

    # Create the parsers for the sub-commands
    subparsers = parser.add_subparsers(dest='command', help='sub-command help',
                                       description="Valid subcommands, use command --help for help")

    abifile_parsers = [copts_parser, path_selector, abiinput_parser]

    # Subparser for validate command.
    p_validate = subparsers.add_parser('validate', parents=abifile_parsers, help=abinp_validate.__doc__)

    # Subparser for autoparal command.
    p_autoparal = subparsers.add_parser('autoparal', parents=abifile_parsers, help=abinp_autoparal.__doc__)
    p_autoparal.add_argument("-n", '--max-ncpus', default=50, type=int, help="Maximum number of CPUs")

    # Subparser for abispg command.
    p_abispg = subparsers.add_parser('abispg', parents=abifile_parsers, help=abinp_abispg.__doc__)

    # Subparser for ibz command.
    p_ibz = subparsers.add_parser('ibz', parents=abifile_parsers, help=abinp_ibz.__doc__)

    # Subparser for phperts command.
    p_phperts = subparsers.add_parser('phperts', parents=abifile_parsers, help=abinp_phperts.__doc__)

    inpgen_parsers = [copts_parser, path_selector, abiinput_parser]

    # Subparser for gs command.
    p_gs = subparsers.add_parser('gs', parents=inpgen_parsers, help=abinp_gs.__doc__)

    # Subparser for ebands command.
    p_ebands = subparsers.add_parser('ebands', parents=inpgen_parsers, help=abinp_ebands.__doc__)

    # Subparser for phonons command.
    p_phonons = subparsers.add_parser('phonons', parents=inpgen_parsers, help=abinp_phonons.__doc__)

    # Subparser for g0w0 command.
    p_g0w0 = subparsers.add_parser('g0w0', parents=inpgen_parsers, help=abinp_g0w0.__doc__)

    # Subparser for anaph command.
    p_anaph = subparsers.add_parser('anaph', parents=inpgen_parsers, help=abinp_anaph.__doc__)

    # Subparser for wannier90 command.
    p_wannier90 = subparsers.add_parser('wannier90', parents=inpgen_parsers, help=abinp_wannier90.__doc__)

    return parser

@prof_main
def main():

    def show_examples_and_exit(err_msg=None, error_code=1):
        """Display the usage of the script."""
        sys.stderr.write(get_epilog())
        if err_msg:
            sys.stderr.write("Fatal Error\n" + err_msg + "\n")
        sys.exit(error_code)

    parser = get_parser(with_epilog=True)

    # Parse the command line.
    try:
        options = parser.parse_args()
    except Exception:
        show_examples_and_exit(error_code=1)

    if not options.command:
        show_examples_and_exit(error_code=1)

    # loglevel is bound to the string value obtained from the command line argument.
    # Convert to upper case to allow the user to specify --loglevel=DEBUG or --loglevel=debug
    import logging
    numeric_level = getattr(logging, options.loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % options.loglevel)
    logging.basicConfig(level=numeric_level)

    # Dispatch
    return globals()["abinp_" + options.command](options)


if __name__ == "__main__":
    sys.exit(main())
