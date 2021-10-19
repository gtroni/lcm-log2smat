"""Convert a LCM log to a python dict and optionally export .pkl or .mat."""

# !/usr/bin/python3
#
# Converts a LCM log to a "structured" format that is easier to work with
# external tools such as Matlab or Python. The set of messages on a given
# channel can be represented as a structure preserving the original lcm message
# structure.
# pylcm is based on lcm-log2smat which is based on libbot2 script bot-log2mat.
# Modified by Duan Yutong, MKuoch

import os
import pickle
import re
import sys
import zlib

import numpy as np
import scipy.io.matlab.mio
from lcm import EventLog

try:
    import imageio
except ImportError:
    pass  # no jpeg decompression

from .scan_for_lcmtypes import make_lcmtype_dictionary

# make dict and import discovered LCM types upon import
# to avoid multiprocessing crashing
TYPE_DB = make_lcmtype_dictionary()

long = int
unicode = int
longOpts = [
    "help",
    "print",
    "pickle",
    "format",
    "separator",
    "channelsToProcess",
    "ignore",
    "outfile",
]


def usage():
    """Options for extracting the lcm log data."""
    _, sname = os.path.split(sys.argv[0])
    sys.stderr.write(f"usage: {sname} {longOpts} < filename > \n")
    print(
        """
    -h --help                 print this message
    -p --print                Output log data to stdout instead of .mat or .pkl
    -k --pickle               Output log data to python .pkl instead of .mat
    -f --format               print the data format to stderr
    -s --seperator=sep        print with separator [sep] instead of ["" ""]
    -c --channelsToProcess=chan        Parse channelsToProcess that match
                                       Python regex [chan] defaults to [".*"]
    -i --ignore=chan          Ignore channelsToProcess that match regex [chan]
                              ignores take precedence over includes!
    -o --outfile=ofname       output data to [ofname] instead of default
    -v                        Verbose

    """
    )
    sys.exit()


def msg_getfields(lcm_msg):
    """Get the fields of lcm_msg."""
    return lcm_msg.__slots__


def msg_getconstants(lcm_msg):
    """Get the constants of lcm_msg."""
    # Get full list of valid attributes
    fulllist = dir(lcm_msg)
    # Get constants
    constantslist = [
        x
        for x in fulllist
        if not (x[0] == "_")
        if not (x == "decode")
        if not (x == "encode")
        if x not in msg_getfields(lcm_msg)
    ]
    return constantslist


# the image type in the lcmlog is required to have at least
# data, width, and height attributres
_SUPPORTED_IMAGE_TYPES = {
    "<class 'bot_core.image_t.image_t'>",
    "<class 'drake.lcmt_image.lcmt_image'>",
}


def msg_to_dict(
    channel,
    msg,
    lcm_timestamp=-1,
):
    """Convert a single message to dict recursively without root data."""
    data = {}
    if hasattr(msg, "__slots__"):
        for const in msg_getconstants(msg):
            data[const[:31]] = getattr(msg, const)
    for field in msg_getfields(msg):
        value = getattr(msg, field)
        if isinstance(value, (int, long, float, str, tuple, unicode)):
            data[field] = value
        elif hasattr(value, "__slots__"):
            data[field] = msg_to_dict(
                channel, value, lcm_timestamp=lcm_timestamp
            )
        elif isinstance(value, list):
            if isinstance(value[0], list):
                # e.g. lcmt_polynomial_matrix polynomial_matrices[num_segments]
                data[field] = [
                    tuple(
                        msg_to_dict(channel, item, lcm_timestamp=lcm_timestamp)
                        for item in row
                    )
                    for row in value
                ]
            else:
                data[field] = tuple(
                    msg_to_dict(channel, item, lcm_timestamp=lcm_timestamp)
                    for item in value
                )
        else:
            print(f"ignoring field {field} from channel {channel}")
    if lcm_timestamp > 0:
        data["lcm_timestamp"] = lcm_timestamp
    return data


def append_msg_to_dict(  # noqa: C901, pylint: disable=R0912
    data,
    e_channel,
    msg,
    status_msg,
    verbose=False,
    lcm_timestamp=-1,
    decompress_images=True,
    depth_dtype="uint16",
):
    """Append msg to the root data[e_channel] (recursively)."""
    # Initializing channel
    if e_channel not in data:
        data[e_channel] = {}
        # Iterate each constant of the LCM message
        constants = msg_getconstants(msg)
        for const in constants:
            data[e_channel][const[:31]] = getattr(msg, const)
    # Get lcm fields and constants
    fields = msg_getfields(msg)
    # Iterate each field of the LCM message
    for field in fields:
        my_value = getattr(msg, field)
        if isinstance(my_value, (int, long, float, str, tuple, unicode)):
            try:
                data[e_channel][field[:31]].append(my_value)
            except KeyError:
                data[e_channel][field[:31]] = [my_value]

        elif hasattr(my_value, "__slots__"):
            append_msg_to_dict(
                data[e_channel],
                field[:31],
                getattr(msg, field),
                status_msg,
                verbose,
                decompress_images=decompress_images,
                depth_dtype=depth_dtype,
            )

        # Handles getting RBGD data from 'images' field
        elif (
            field == "images"
            and isinstance(my_value, list)
            and str(type(my_value[0])) in _SUPPORTED_IMAGE_TYPES
        ):
            if decompress_images:  # Read lcmt_image.data to numpy arrays
                rgb = np.array(imageio.imread(my_value[0].data))
                depth_data = zlib.decompress(my_value[1].data)
                depth = np.frombuffer(depth_data, dtype=depth_dtype).reshape(
                    my_value[1].height, my_value[1].width
                )
            else:  # keep data compressed
                rgb, depth = my_value[0].data, my_value[1].data
            try:
                data[e_channel]["RGB"].append(rgb)
                data[e_channel]["depth"].append(depth)
            except KeyError:
                data[e_channel]["RGB"] = [rgb]
                data[e_channel]["depth"] = [depth]
        elif isinstance(my_value, list):
            data[e_channel][field] = tuple(
                msg_to_dict(e_channel, item, lcm_timestamp=lcm_timestamp)
                for item in my_value
            )
        else:
            status_msg = delete_status_message(status_msg)
            sys.stderr.write(
                f"ignoring field {field} from channel {e_channel}"
            )
            continue

    # Add extra field with lcm_timestamp
    if lcm_timestamp > 0:
        try:
            data[e_channel]["lcm_timestamp"].append(lcm_timestamp)
        except KeyError:
            data[e_channel]["lcm_timestamp"] = [lcm_timestamp]


def delete_status_message(stat_msg):
    """Remove stat_msg from stderr."""
    if stat_msg:
        sys.stderr.write("\r")
        sys.stderr.write(" " * (len(stat_msg)))
        sys.stderr.write("\r")
    return ""


def parse_lcm(  # noqa: C901
    fname, opts=None, decompress_images=True, depth_dtype="uint16"
):  # pylint: disable=R1710
    # pylint: disable=R0914,R0912,R0915
    """Parse LCM log.

    Keyword arguments:
    fname -- absolute path to LCM log, relative path is not supported
    opts -- dict of options. Default None returns dict
    decompress_images -- whether or not to decompress images. Default True.
    depth_image_shape -- dimensions of depth image in LCM log.
                         Default assumed to be 640x480.
    """
    # Default options
    verbose = False
    printOutput = False
    savePickle = False
    saveMat = False
    channelsToIgnore = ""
    checkIgnore = False
    channelsToProcess = ".*"
    if opts is not None:
        for o, a in opts.items():
            if o == "-v":
                verbose = True
            elif o in ("-h", "--help"):
                usage()
            elif o in ("-p", "--print"):
                printOutput = True
            elif o in ("-k", "--pickle"):
                savePickle = True
            elif o in ("-m", "--mat"):
                saveMat = True
            elif o in ("-o", "--outfile="):
                outFname = a
                printFname = a
            elif o in ("-c", "--channelsToProcess="):
                channelsToProcess = a
            elif o in ("-i", "--ignore="):
                channelsToIgnore = a
                checkIgnore = True
            else:
                assert f"unhandled option key {o}, value{a}"

    try:
        outFname
    except NameError:
        outDir, outFname = os.path.split(os.path.abspath(fname))

        if savePickle:
            outFname = outDir + "/" + outFname + ".pkl"
        elif saveMat:
            outFname = outFname.replace(".", "_")
            outFname = outFname.replace("-", "_")
            outFname = outDir + "/" + outFname + ".mat"

    fullPathName = os.path.abspath(outFname)
    dirname = os.path.dirname(fullPathName)
    outBaseName = ".".join(os.path.basename(outFname).split(".")[0:-1])

    data = {}
    channelsToProcess = re.compile(channelsToProcess)
    channelsToIgnore = re.compile(channelsToIgnore)
    log = EventLog(fname, "r")

    if printOutput:
        print(f"opened {fname}, printing output to {printFname}")
    # channel name: packed fingerprint
    ignored_channels = {"LCM_SELF_TEST": b"lcm self"}
    msgCount = 0
    status_msg = ""
    startTime = 0

    # Iterate LCM log file
    for e in log:
        if msgCount == 0:
            startTime = e.timestamp

        if e.channel in ignored_channels:
            continue
        if (
            checkIgnore
            and channelsToIgnore.match(e.channel)
            and len(channelsToIgnore.match(e.channel).group())
            == len(e.channel)
        ) or (not channelsToProcess.match(e.channel)):
            if verbose:
                status_msg = delete_status_message(status_msg)
                sys.stderr.write(f"ignoring channel {e.channel}")
            ignored_channels[e.channel] = None
            continue

        packed_fingerprint = e.data[:8]
        lcmtype = TYPE_DB.get(packed_fingerprint, None)
        if not lcmtype:
            status_msg = delete_status_message(status_msg)
            sys.stderr.write(
                f"PyLCM: ignoring channel {e.channel}, "
                f"unknown LCM type with fingerprint {packed_fingerprint}\n"
            )
            ignored_channels[e.channel] = packed_fingerprint
            continue
        try:
            msg = lcmtype.decode(e.data)
        except:  # noqa: E722  pylint: disable=W0702
            status_msg = delete_status_message(status_msg)
            sys.stderr.write(f"ouldn't decode msg on channel {e.channel}")
            continue
        msgCount = msgCount + 1
        if printOutput and (msgCount % 5000) == 0:
            delete_status_message(status_msg)
            status_msg = (
                f"read {msgCount} messages, "
                f"{log.tell() / float(log.size()) * 100}% done"
            )
            sys.stderr.write(status_msg)
            sys.stderr.flush()
        append_msg_to_dict(
            data,
            e.channel,
            msg,
            status_msg,
            verbose,
            (e.timestamp - startTime) / 1e6,
            decompress_images=decompress_images,
            depth_dtype=depth_dtype,
        )
    if ignored_channels and not (
        len(ignored_channels) == 1
        and next(iter(ignored_channels)) == "LCM_SELF_TEST"
    ):
        print(
            f"Ignored {len(ignored_channels)} channels, "
            f"unkonwn packed fingerprint: {ignored_channels}"
        )
    delete_status_message(status_msg)
    if verbose or printOutput:
        print(f"Loaded all {msgCount} messages")
    if savePickle:  # Pickle format using the highest protocol available
        print(f"Saving pickle to: {outFname}")
        with open(outFname, "wb") as f:
            pickle.dump(data, f, -1)
    elif saveMat:  # Matlab format using scipy
        print(f"Saving pickle to: {outFname}")
        if sys.version_info < (2, 6):
            scipy.io.mio.savemat(outFname, data)
        else:
            scipy.io.matlab.mio.savemat(outFname, data, oned_as="row")

        with open(
            dirname + "/" + outBaseName + ".m", "w", encoding="utf-8"
        ) as mfile:
            loadFunc = f"""function [d imFnames]={outBaseName}()
full_fname = '{outFname}';
fname = '{fullPathName}';
if (exist(full_fname,'file'))
filename = full_fname;
else
filename = fname;
end
d = load(filename);
"""
            print(loadFunc)
            mfile.write(loadFunc)

    return data
