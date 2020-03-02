from __future__ import division, with_statement

import logging
import warnings
from copy import deepcopy

import numpy

from .._common import default
from ._helpers import block, check_parameters, dtypes

__all__ = [
    "read",
    "write",
]


def read(filename):
    """
    Read TOUGH input file.

    Parameters
    ----------
    filename : str
        Input file name.

    Returns
    -------
    dict
        TOUGH input parameters.

    """
    with open(filename, "r") as f:
        parameters = {}

        # Title
        parameters["title"] = f.readline().strip()
        
        # Loop over blocks
        while True:
            line = f.readline().strip()

            if line.startswith("ROCKS"):
                parameters.update(_read_rocks(f))
            elif line.startswith("RPCAP"):
                parameters.update(_read_rpcap(f))
            elif line.startswith("FLAC"):
                parameters.update(_read_flac(f))
            elif line.startswith("MULTI"):
                parameters.update(_read_multi(f))
            elif line.startswith("START"):
                parameters["start"] = True
            elif line.startswith("PARAM"):
                parameters.update(_read_param(f))
            elif line.startswith("MOMOP"):
                parameters.update(_read_momop(f))
            elif line.startswith("INDOM"):
                parameters.update(_read_indom(f))
            elif line.startswith("TIMES"):
                parameters.update(_read_times(f))
            elif line.startswith("SOLVR"):
                parameters.update(_read_solvr(f))
            elif line.startswith("FOFT"):
                parameters.update(_read_oft(f, "element_history"))
            elif line.startswith("COFT"):
                parameters.update(_read_oft(f, "connection_history"))
            elif line.startswith("GOFT"):
                parameters.update(_read_oft(f, "generator_history"))
            elif line.startswith("DIFFU"):
                parameters.update(_read_diffu(f))
            elif line.startswith("OUTPU"):
                parameters.update(_read_outpu(f))
            elif line.startswith("ELEME"):
                logging.warning("Reading block ELEME is not supported. Skipping.")
            elif line.startswith("CONNE"):
                logging.warning("Reading block CONNE is not supported. Skipping.")
            elif line.startswith("INCON"):
                logging.warning("Reading block INCON is not supported. Skipping.")
            elif line.startswith("NOVER"):
                parameters["nover"] = True
            elif line.startswith("ENDFI"):
                parameters["endfi"] = True
            elif line.startswith("ENDCY"):
                break

    return parameters


def _read_record(data, fmt):
    """Parse string to data given format."""
    token_to_type = {
        "s": str,
        "S": str,
        "d": int,
        "f": float,
        "e": float,
    }
    
    i = 0
    out = []
    for token in fmt.split(","):
        n = int(token[:-1])
        tmp = data[i:i+n]
        tmp = tmp if token[-1] == "S" else tmp.strip()
        out.append(token_to_type[token[-1]](tmp) if tmp else None)
        i += n

    return out


def _prune_nones_dict(data):
    """Remove None key/value pairs from dict."""
    return {k: v for k, v in data.items() if v is not None}


def _prune_nones_list(data):
    """Remove trailing None values from list."""
    return [x for i, x in enumerate(data) if any(xx is not None for xx in data[i:])]


def _read_rocks(f):
    """Read ROCKS block data."""
    rocks = {"rocks": {}}

    while True:
        line = f.readline()

        if line.strip():
            # Record 1
            data = _read_record(line, "5s,5d,10e,10e,10e,10e,10e,10e,10e")
            rock = data[0]
            rocks["rocks"][rock] = {
                "density": data[2],
                "porosity": data[3],
                "permeability": data[4] if len(set(data[4:7])) == 1 else data[4:7],
                "conductivity": data[7],
                "specific_heat": data[8],
            }

            nad = data[1]
            if nad is not None:
                # Record 2
                line = f.readline()
                data = _read_record(line, "10e,10e,10e,10e,10e,10e,10e")
                rocks["rocks"][rock].update({
                    "compressibility": data[0],
                    "expansivity": data[1],
                    "conductivity_dry": data[2],
                    "tortuosity": data[3],
                    "b_coeff": data[4],
                    "xkd3": data[5],
                    "xkd4": data[6],
                })

            if nad > 1:
                rocks["rocks"][rock].update(_read_rpcap(f))

        else:
            break
    
    return {k: {kk: _prune_nones_dict(vv) for kk, vv in v.items()} for k, v in rocks.items()}


def _read_rpcap(f):
    """Read RPCAP block data."""
    rpcap = {}

    for key in ["relative_permeability", "capillarity"]:
        line = f.readline()
        data = _read_record(line, "5d,5s,10e,10e,10e,10e,10e,10e,10e")
        rpcap[key] = {
            "id": data[0],
            "parameters": _prune_nones_list(data[2:]),
        }

    return rpcap


def _read_flac(f):
    """Read FLAC block data."""
    logging.warning("Reading block FLAC is not supported yet. Skipping.")
    return {}


def _read_multi(f):
    """Read MULTI block data."""
    multi = {}

    line = f.readline().split()
    multi["n_component"] = int(line[0])
    multi["isothermal"] = int(line[1]) == int(line[0])
    multi["n_phase"] = int(line[2])
    
    return multi


def _read_param(f):
    """Read PARAM block data."""
    param = {}

    # Record 1
    line = f.readline()
    data = _read_record(line, "2d,2d,4d,4d,4d,24S,10s,10e,10e")
    param["options"] = {
        "n_iteration": data[0],
        "verbosity": data[1],
        "n_cycle": data[2],
        "n_second": data[3],
        "n_cycle_print": data[4],
        "temperature_dependence_gas": data[7],
        "effective_strength_vapor": data[8],
    }
    param["extra_options"] = {i+1: int(x) for i, x in enumerate(data[5]) if x.isdigit()}

    # Record 2
    line = f.readline()
    data = _read_record(line, "10e,10e,10f,10e,10s,10e,10e,10e")
    param["options"].update({
        "t_ini": data[0],
        "t_max": data[1],
        "t_steps": data[2],
        "t_step_max": data[3],
        "gravity": data[5],
        "t_reduce_factor": data[6],
        "mesh_scale_factor": data[7],
    })

    t_steps = int(data[2])
    if t_steps >= 0.0:
        param["options"]["t_steps"] = t_steps
    else:
        param["options"]["t_steps"] = []
        for _ in range(-t_steps):
            line = f.readline()
            data = _read_record(line, "10e,10e,10e,10e,10e,10e,10e,10e")
            param["options"]["t_steps"] += _prune_nones_list(data)
        if len(param["options"]["t_steps"]) == 1:
            param["options"]["t_steps"] = param["options"]["t_steps"][0]

    # Record 3
    line = f.readline()
    data = _read_record(line, "10e,10e,10s,10e,10e,10e")
    param["options"].update({
        "eps1": data[0],
        "eps2": data[1],
        "w_upstream": data[3],
        "w_newton": data[4],
        "derivative_factor": data[5],
    })

    # Record 4
    line = f.readline()
    data = _read_record(line, "20e,20e,20e,20e")
    if any(x is not None for x in data):
        data = _prune_nones_list(data)
        param["default"] = {"incon": data}

    # Remove Nones
    param["options"] = _prune_nones_dict(param["options"])
    param["extra_options"] = _prune_nones_dict(param["extra_options"])

    return param


def _read_momop(f):
    """Read MOMOP block data."""
    line = f.readline()
    data = _read_record(line, "40S")
    momop = {"more_options": {i+1: int(x) for i, x in enumerate(data[5]) if x.isdigit()}}

    return momop


def _read_indom(f):
    """Read INDOM block data."""
    indom = {"rocks": {}}

    while True:
        line = f.readline()

        if line.strip():
            rock = line[:5]
            line = f.readline()
            data = _read_record(line, "20e,20e,20e,20e")
            data = _prune_nones_list(data)
            indom["rocks"][rock]["incon"] = data
        else:
            break

    return indom


def _read_times(f):
    """Read TIMES block data."""
    times = {"times": []}

    # Record 1
    line = f.readline()
    data = _read_record(line, "5d,5d,10e,10e")
    n_times = data[0]

    # Record 2
    while len(times["times"]) < n_times:
        line = f.readline()
        data = _read_record(line, "10e,10e,10e,10e,10e,10e,10e,10e")
        times["times"] += _prune_nones_list(data)

    return times


def _read_solvr(f):
    """Read SOLVR block data."""
    solvr = {}

    line = f.readline()
    data = _read_record(line, "1d,2s,2s,3s,2s,10e,10e")
    solvr["solver"] = {
        "method": data[0],
        "z_precond": data[2],
        "o_precond": data[4],
        "rel_iter_max": data[5],
        "eps": data[6],
    }

    return solvr


def _read_oft(f, oft):
    """Read FOFT, COFT and GOFT blocks data."""
    history = {oft: []}

    while True:
        line = f.readline().rstrip()

        if line:
            history[oft].append(line)
        else:
            break

    return history


def _read_diffu(f):
    """Read DIFFU block data."""
    diffu = {"diffusion": []}

    for _ in range(2):
        line = f.readline()
        data = _read_record(line, "10e,10e,10e,10e,10e,10e,10e,10e")
        diffu["diffusion"].append(_prune_nones_list(data))

    return diffu


def _read_outpu(f):
    """Read OUTPU block data."""
    outpu = {"output": {}}

    # Format
    line = f.readline().strip()
    outpu["output"]["format"] = line if line else None

    # Variables
    line = f.readline().strip()
    if line.isdigit():
        n_var = int(line)
        outpu["output"]["variables"] = {}

        for _ in range(n_var):
            line = f.readline()
            data = _read_record(line, "20s,5d,5d")
            name = data[0].lower()
            outpu["output"]["variables"][name] = _prune_nones_list(data[1:])
            outpu["output"]["variables"][name] = (
                outpu["output"]["variables"][name]
                if len(outpu["output"]["variables"][name]) == 2
                else outpu["output"]["variables"][name][0]
                if len(outpu["output"]["variables"][name]) == 1
                else None
            )

    return outpu


def write(filename, parameters):
    """
    Write TOUGH input file.

    Parameters
    ----------
    filename : str
        Output file name.
    parameters : dict
        Parameters to export.

    """
    from .._common import Parameters, default

    if "rocks" not in parameters.keys():
        raise ValueError("Block 'ROCKS' (key 'rocks') is not defined.")
    if "options" not in parameters.keys():
        raise ValueError("Block 'PARAM' (key 'options') is not defined.")

    params = deepcopy(Parameters)
    params.update(deepcopy(parameters))

    for k, v in default.items():
        if k not in params["default"].keys():
            params["default"][k] = v

    for rock in params["rocks"].keys():
        for k, v in params["default"].items():
            if k not in params["rocks"][rock].keys() and k not in {"incon"}:
                params["rocks"][rock][k] = v

    buffer = write_buffer(params)
    with open(filename, "w") as f:
        for record in buffer:
            f.write(record)


@check_parameters(dtypes["PARAMETERS"])
def write_buffer(parameters):
    """Write TOUGH input file as a list of 80-character long record strings."""
    from .._common import eos, eos_select

    # Check that EOS is defined (for block MULTI)
    if parameters["isothermal"] and parameters["eos"] not in eos.keys():
        raise ValueError(
            "EOS '{}' is unknown or not supported.".format(parameters["eos"])
        )

    # Set some flags
    indom = False
    for rock in parameters["rocks"].values():
        if "incon" in rock.keys():
            if any(x is not None for x in rock["incon"][:4]):
                indom = True
                break

    # Deprecation warning: 'incon' is now in 'default' rather than in 'options'
    if "incon" in parameters["options"].keys():
        warnings.warn(
            "Defining 'incon' in 'options' is deprecated, define 'incon' in 'default'.",
            DeprecationWarning,
        )
        parameters["default"]["incon"] = parameters["options"].pop("incon")

    # Check that start is True if indom is True
    if indom and not parameters["start"]:
        logging.warning("Option 'START' is needed to use 'INDOM' conditions.")

    # Define input file contents
    out = ["{:80}\n".format(parameters["title"])]
    out += _write_rocks(parameters)
    out += _write_flac(parameters) if parameters["flac"] else []
    out += _write_multi(parameters) if parameters["eos"] else []
    out += _write_selec(parameters) if parameters["eos"] in eos_select else []
    out += _write_solvr(parameters) if parameters["solver"] else []
    out += _write_start() if parameters["start"] else []
    out += _write_param(parameters)
    out += _write_indom(parameters) if indom else []
    if parameters["more_options"]:
        if parameters["version"] == 3:
            out += _write_momop(parameters)
        else:
            logging.warning(
                "Defining 'more_options' is only available for 'version == 3'. Skipping."
            )
    out += _write_times(parameters) if parameters["times"] is not None else []
    out += _write_foft(parameters) if parameters["element_history"] is not None else []
    out += (
        _write_coft(parameters) if parameters["connection_history"] is not None else []
    )
    out += (
        _write_goft(parameters) if parameters["generator_history"] is not None else []
    )
    out += _write_gener(parameters) if parameters["generators"] else []
    out += _write_diffu(parameters) if parameters["diffusion"] else []
    if parameters["output"]:
        if parameters["version"] == 3:
            out += _write_outpu(parameters)
        else:
            logging.warning(
                "Defining 'output' is only available for 'version == 3'. Skipping."
            )
    out += _write_nover() if parameters["nover"] else []
    out += _write_endfi() if parameters["endfi"] else _write_endcy()
    return out


def _format_data(data):
    """Return a list of strings given input data and formats."""

    def to_str(x, fmt):
        x = "" if x is None or x == "" else x
        if isinstance(x, str):
            return fmt.replace("g", "").replace("e", "").format(x)
        else:
            return fmt.format(x)

    return [to_str(x, fmt) for x, fmt in data]


def _write_record(data):
    """Return a list with a single string."""
    return ["{:80}\n".format("".join(data))]


def _write_multi_record(data, ncol=8):
    """Return a list with multiple strings."""
    n = len(data)
    rec = [
        data[ncol * i : min(ncol * i + ncol, n)]
        for i in range(int(numpy.ceil(n / ncol)))
    ]
    return [_write_record(r)[0] for r in rec]


def _add_record(data, id_fmt="{:>5g}     "):
    """Return a list with a single string for additional records."""
    n = len(data["parameters"])
    rec = [(data["id"], id_fmt)]
    rec += [(v, "{:>10.3e}") for v in data["parameters"][: min(n, 7)]]
    return _write_record(_format_data(rec))


@check_parameters(dtypes["ROCKS"], keys="default")
@check_parameters(dtypes["MODEL"], keys=("default", "relative_permeability"))
@check_parameters(dtypes["MODEL"], keys=("default", "capillarity"))
@check_parameters(dtypes["ROCKS"], keys="rocks", is_list=True)
@check_parameters(
    dtypes["MODEL"], keys=("rocks", "relative_permeability"), is_list=True
)
@check_parameters(dtypes["MODEL"], keys=("rocks", "capillarity"), is_list=True)
@block("ROCKS", multi=True)
def _write_rocks(parameters):
    """
    TOUGH input ROCKS block data.

    Introduces material parameters for up to 27 different reservoir domains.

    """
    # Reorder rocks
    if parameters["rocks_order"] is not None:
        order = parameters["rocks_order"]
    else:
        order = parameters["rocks"].keys()

    out = []
    for k in order:
        # Load data
        data = default.copy()
        data.update(parameters["default"])
        data.update(parameters["rocks"][k])

        # Number of additional lines to write per rock
        # Always 2 since relative permeability and capillarity are copied from default
        nad = 2

        # Permeability
        per = data["permeability"]
        per = [per] * 3 if isinstance(per, float) else per
        if not (isinstance(per, (list, tuple, numpy.ndarray)) and len(per) == 3):
            raise TypeError()

        # Record 1
        out += _write_record(
            _format_data(
                [
                    (k, "{:5.5}"),
                    (nad if nad else None, "{:>5g}"),
                    (data["density"], "{:>10.4e}"),
                    (data["porosity"], "{:>10.4e}"),
                    (per[0], "{:>10.4e}"),
                    (per[1], "{:>10.4e}"),
                    (per[2], "{:>10.4e}"),
                    (data["conductivity"], "{:>10.4e}"),
                    (data["specific_heat"], "{:>10.4e}"),
                ]
            )
        )

        # Record 2
        out += _write_record(
            _format_data(
                [
                    (data["compressibility"], "{:>10.4e}"),
                    (data["expansion"], "{:>10.4e}"),
                    (data["conductivity_dry"], "{:>10.4e}"),
                    (data["tortuosity"], "{:>10.4e}"),
                    (data["b_coeff"], "{:>10.4e}"),
                    (data["xkd3"], "{:>10.4e}"),
                    (data["xkd4"], "{:>10.4e}"),
                ]
            )
        )

        # Relative permeability
        out += _add_record(data["relative_permeability"]) if nad >= 1 else []

        # Capillary pressure
        out += _add_record(data["capillarity"]) if nad >= 2 else []
    return out


@check_parameters(dtypes["MODEL"], keys=("default", "permeability_model"))
@check_parameters(dtypes["MODEL"], keys=("default", "equivalent_pore_pressure"))
@check_parameters(dtypes["MODEL"], keys=("rocks", "permeability_model"), is_list=True)
@check_parameters(
    dtypes["MODEL"], keys=("rocks", "equivalent_pore_pressure"), is_list=True
)
@block("FLAC", multi=True)
def _write_flac(parameters):
    """
    TOUGH input FLAC block data (optional).

    Introduces mechanical parameters for each material in ROCKS block data.

    """
    # Reorder rocks
    if parameters["rocks_order"]:
        order = parameters["rocks_order"]
    else:
        order = parameters["rocks"].keys()

    # Record 1
    out = _write_record(
        _format_data(
            [
                (1 if parameters["creep"] else 0, "{:5g}"),
                (parameters["porosity_model"], "{:5g}"),
            ]
        )
    )

    # Additional records
    for k in order:
        # Load data
        data = default.copy()
        data.update(parameters["default"])
        data.update(parameters["rocks"][k])

        # Permeability law
        out += _add_record(data["permeability_model"], "{:>10g}")

        # Equivalent pore pressure
        out += _add_record(data["equivalent_pore_pressure"])
    return out


@block("MULTI")
def _write_multi(parameters):
    """
    TOUGH input MULTI block (optional).

    Permits the user to select the number and nature of balance equations that will be
    solved. The keyword MULTI is followed by a single data record. For most EOS modules,
    this data block is not needed, as default values are provided internally. Available
    parameter choices are different for different EOS modules.

    """
    from .._common import eos

    out = list(eos[parameters["eos"]])
    out[0] = parameters["n_component"] if parameters["n_component"] else out[0]
    out[1] = out[0] if parameters["isothermal"] else out[0] + 1
    out[2] = parameters["n_phase"] if parameters["n_phase"] else out[2]

    # Handle diffusion
    if parameters["diffusion"]:
        out[3] = 8
        parameters["n_phase"] = out[2]  # Save for later check

    return [("{:>5d}" * len(out) + "\n").format(*out)]


@check_parameters(dtypes["SELEC"], keys="selections")
@block("SELEC")
def _write_selec(parameters):
    """
    TOUGH input SELEC block (optional).

    Introduces a number of integer and floating point parameters that are used for
    different purposes in different TOUGH modules (EOS7, EOS7R, EWASG, T2DM, ECO2N).

    """
    # Load data
    from .._common import select

    data = select.copy()
    data.update(parameters["selections"])

    # Record 1
    out = _write_record(_format_data([(v, "{:>5}") for v in data.values()]))

    # Record 2
    if parameters["extra_selections"] is not None:
        out += _write_multi_record(
            _format_data([(i, "{:>10.3e}") for i in parameters["extra_selections"]])
        )
    return out


@check_parameters(dtypes["SOLVR"], keys="solver")
@block("SOLVR")
def _write_solvr(parameters):
    """
    TOUGH input SOLVR block (optional).

    Introduces computation parameters, time stepping information, and default initial
    conditions.

    """
    from .._common import solver

    data = solver.copy()
    data.update(parameters["solver"])
    return _write_record(
        _format_data(
            [
                (data["method"], "{:1g}  "),
                (data["z_precond"], "{:>2g}   "),
                (data["o_precond"], "{:>2g}"),
                (data["rel_iter_max"], "{:>10.4e}"),
                (data["eps"], "{:>10.4e}"),
            ]
        )
    )


@block("START")
def _write_start():
    """
    TOUGH input START block (optional).

    A record with START typed in columns 1-5 allows a more flexible initialization. More
    specifically, when START is present, INCON data can be in arbitrary order, and need
    not be present for all grid blocks (in which case defaults will be used). Without
    START, there must be a one-to-one correspondence between the data in blocks ELEME
    and INCON.

    """
    from .._common import header

    out = "{:5}{}\n".format("----*", header)
    return [out[:11] + "MOP: 123456789*123456789*1234" + out[40:]]


@check_parameters(dtypes["PARAM"], keys="options")
@check_parameters(dtypes["MOP"], keys="extra_options")
@block("PARAM")
def _write_param(parameters):
    """
    TOUGH input PARAM block data.

    Introduces computation parameters, time stepping information, and default initial
    conditions.

    """
    # Load data
    from .._common import options

    data = options.copy()
    data.update(parameters["options"])

    # Table
    if not isinstance(data["t_steps"], (list, tuple, numpy.ndarray)):
        data["t_steps"] = [data["t_steps"]]

    # Record 1
    from .._common import extra_options

    _mop = deepcopy(extra_options)
    _mop.update(parameters["extra_options"])
    mop = _format_data([(_mop[k], "{:>1g}") for k in sorted(_mop.keys())])
    out = _write_record(
        _format_data(
            [
                (data["n_iteration"], "{:>2g}"),
                (data["verbosity"], "{:>2g}"),
                (data["n_cycle"], "{:>4g}"),
                (data["n_second"], "{:>4g}"),
                (data["n_cycle_print"], "{:>4g}"),
                ("{}".format("".join(mop)), "{:>24}"),
                (None, "{:>10}"),
                (data["temperature_dependence_gas"], "{:>10.4e}"),
                (data["effective_strength_vapor"], "{:>10.4e}"),
            ]
        )
    )

    # Record 2
    out += _write_record(
        _format_data(
            [
                (data["t_ini"], "{:>10.4e}"),
                (data["t_max"], "{:>10.4e}"),
                (-((len(data["t_steps"]) - 1) // 8 + 1), "{:>9g}."),
                (data["t_step_max"], "{:>10.4e}"),
                (None, "{:>10g}"),
                (data["gravity"], "{:>10.4e}"),
                (data["t_reduce_factor"], "{:>10.4e}"),
                (data["mesh_scale_factor"], "{:>10.4e}"),
            ]
        )
    )

    # Record 2.1
    out += _write_multi_record(
        _format_data([(i, "{:>10.4e}") for i in data["t_steps"]])
    )

    # Record 3
    out += _write_record(
        _format_data(
            [
                (data["eps1"], "{:>10.4e}"),
                (data["eps2"], "{:>10.4e}"),
                (None, "{:>10.4e}"),
                (data["w_upstream"], "{:>10.4e}"),
                (data["w_newton"], "{:>10.4e}"),
                (data["derivative_factor"], "{:>10.4e}"),
            ]
        )
    )

    # Record 4
    data = parameters["default"]["incon"]
    n = len(data)
    out += _write_record(_format_data([(i, "{:>20.4e}") for i in data[: min(n, 4)]]))
    return out


@check_parameters(dtypes["MOMOP"], keys="more_options")
@block("MOMOP")
def _write_momop(parameters):
    """
    TOUGH input MOMOP block data (optional).

    Provides additional options.

    """
    from .._common import more_options

    _momop = more_options.copy()
    _momop.update(parameters["more_options"])
    out = _write_record(
        _format_data([(_momop[k], "{:>1g}") for k in sorted(_momop.keys())])
    )
    return out


@block("INDOM", multi=True)
def _write_indom(parameters):
    """
    TOUGH input INDOM block data (optional).

    Introduces domain-specific initial conditions.

    """
    if parameters["rocks_order"]:
        order = parameters["rocks_order"]
    else:
        order = parameters["rocks"].keys()

    out = []
    for k in order:
        if "incon" in parameters["rocks"][k]:
            data = parameters["rocks"][k]["incon"]
            data = data[: min(len(data), 4)]
            if any(x is not None for x in data):
                out += ["{:5.5}\n".format(k)]
                out += _write_record(_format_data([(i, "{:>20.4e}") for i in data]))
    return out


@block("TIMES")
def _write_times(parameters):
    """
    TOUGH input TIMES block data (optional).

    Permits the user to obtain printout at specified times.

    """
    data = parameters["times"]
    n = len(data)
    out = _write_record(_format_data([(n, "{:>5g}")]))
    out += _write_multi_record(_format_data([(i, "{:>10.4e}") for i in data]))
    return out


@block("FOFT", multi=True)
def _write_foft(parameters):
    """
    TOUGH input FOFT block data (optional).

    Introduces a list of elements (grid blocks) for which time-dependent data are to be
    written out for plotting to a file called FOFT during the simulation.

    """
    return _write_multi_record(
        _format_data([(i, "{:>5g}") for i in parameters["element_history"]]), ncol=1
    )


@block("COFT", multi=True)
def _write_coft(parameters):
    """
    TOUGH input COFT block data (optional).

    Introduces a list of connections for which time-dependent data are to be written out
    for plotting to a file called COFT during the simulation.

    """
    return _write_multi_record(
        _format_data([(i, "{:>10g}") for i in parameters["connection_history"]]), ncol=1
    )


@block("GOFT", multi=True)
def _write_goft(parameters):
    """
    TOUGH input GOFT block data (optional).

    Introduces a list of sinks/sources for which time-dependent data are to be written
    out for plotting to a file called GOFT during the simulation.

    """
    return _write_multi_record(
        _format_data([(i, "{:>5g}") for i in parameters["generator_history"]]), ncol=1
    )


@check_parameters(dtypes["GENER"], keys="generators", is_list=True)
@block("GENER", multi=True)
def _write_gener(parameters):
    """
    TOUGH input GENER block data (optional).

    Introduces sinks and/or sources.

    """
    from .._common import generators

    # Handle multicomponent generators
    generator_data = []
    keys = [key for key in generators.keys() if key != "type"]
    for k, v in parameters["generators"].items():
        # Load data
        data = deepcopy(generators)
        data.update(v)

        # Check that data are consistent
        if not isinstance(data["type"], str):
            # Number of components
            num_comps = len(data["type"])

            # Check that values in dict have the same length
            for key in keys:
                if data[key] is not None:
                    if not isinstance(data[key], (list, tuple, numpy.ndarray)):
                        raise TypeError()
                    if len(data[key]) != num_comps:
                        raise ValueError()

            # Split dict
            for i in range(num_comps):
                generator_data.append(
                    (
                        k,
                        {
                            key: (data[key][i] if data[key] is not None else None)
                            for key in generators.keys()
                        },
                    )
                )
        else:
            # Only one component for this element
            # Check that values are scalar or 1D array_like
            for key in keys:
                if numpy.ndim(data[key]) not in {0, 1}:
                    raise ValueError()
            generator_data.append((k, data))

    out = []
    for k, v in generator_data:
        # Table
        ltab, itab = None, None
        if v["times"] is not None and isinstance(
            v["times"], (list, tuple, numpy.ndarray)
        ):
            ltab, itab = len(v["times"]), 1
            if not isinstance(v["rates"], (list, tuple, numpy.ndarray)):
                raise TypeError()
            if not (ltab > 1 and ltab == len(v["rates"])):
                raise ValueError()
        else:
            # Rates and specific enthalpy tables cannot be written without a
            # time table
            for key in ["rates", "specific_enthalpy"]:
                if v[key] is not None:
                    if numpy.ndim(v[key]) != 0:
                        raise ValueError()

        # Record 1
        out += _write_record(
            _format_data(
                [
                    (k, "{:5.5}"),
                    (None, "{:>5g}"),
                    (None, "{:>5g}"),
                    (None, "{:>5g}"),
                    (None, "{:>5g}"),
                    (ltab, "{:>5g}"),
                    (None, "{:>5g}"),
                    (v["type"], "{:4g}"),
                    (itab, "{:>1g}"),
                    (None if ltab else v["rates"], "{:>10.3e}"),
                    (None if ltab else v["specific_enthalpy"], "{:>10.3e}"),
                    (v["layer_thickness"], "{:>10.3e}"),
                ]
            )
        )

        # Record 2
        if ltab:
            out += _write_multi_record(
                _format_data([(i, "{:>14.7e}") for i in v["times"]]), ncol=4
            )

        # Record 3
        if ltab:
            out += _write_multi_record(
                _format_data([(i, "{:>14.7e}") for i in v["rates"]]), ncol=4
            )

        # Record 4
        if ltab and v["specific_enthalpy"] is not None:
            if isinstance(v["specific_enthalpy"], (list, tuple, numpy.ndarray)):
                specific_enthalpy = v["specific_enthalpy"]
            else:
                specific_enthalpy = numpy.full(ltab, v["specific_enthalpy"])
            out += _write_multi_record(
                _format_data([(i, "{:>14.7e}") for i in specific_enthalpy]), ncol=4
            )
    return out


@block("DIFFU")
def _write_diffu(parameters):
    """
    TOUGH input DIFFU block data (optional).

    Introduces diffusion coefficients.

    """
    if numpy.shape(parameters["diffusion"]) != (2, parameters["n_phase"]):
        raise ValueError()
    mass1, mass2 = parameters["diffusion"]

    out = []
    out += _write_multi_record(_format_data([(i, "{:>10.3e}") for i in mass1]), ncol=8)
    out += _write_multi_record(_format_data([(i, "{:>10.3e}") for i in mass2]), ncol=8)
    return out


@check_parameters(dtypes["OUTPU"], keys="output")
@block("OUTPU")
def _write_outpu(parameters):
    """
    TOUGH input OUTPU block data (optional).

    Specifies variables/parameters for printout.

    """
    from .._common import output

    data = deepcopy(output)
    data.update(parameters["output"])

    # Format
    out = []
    out += "{:20}\n".format(data["format"].upper()) if data["format"] else "\n"

    # Variables
    if data["variables"]:
        out += "{:15}\n".format(str(len(data["variables"])))

        for k, v in data["variables"].items():
            fmt = "{:20}"
            if v:
                v = v if isinstance(v, (list, tuple, numpy.ndarray)) else [v]
                if not (0 < len(v) < 3):
                    raise ValueError()
                fmt += "{:5}" * len(v)
                out += "{}\n".format(fmt.format(k.upper(), *v))
            else:
                out += "{}\n".format(fmt.format(k.upper()))

    return out


@block("NOVER")
def _write_nover():
    """TOUGH input NOVER block data (optional)."""
    return []


@block("ENDFI", noend=True)
def _write_endfi():
    """TOUGH input ENDFI block data (optional)."""
    return []


@block("ENDCY", noend=True)
def _write_endcy():
    """TOUGH input ENDCY block data (optional)."""
    return []
