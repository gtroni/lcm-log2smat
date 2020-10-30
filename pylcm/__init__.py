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

import imageio
import numpy as np
import scipy.io.matlab.mio
from bot_core import image_t
from lcm import EventLog

from .scan_for_lcmtypes import make_lcmtype_dictionary

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
    sys.stderr.write("usage: % s %s < filename > \n" % (sname, str(longOpts)))
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


def msg_to_dict(  # noqa: C901, pylint: disable=R0912
    data,
    e_channel,
    msg,
    status_msg,
    verbose=False,
    lcm_timestamp=-1,
    decompress_jpeg=True,
    depth_image_shape=(480, 640),
):
    """Add information in msg to the dictionary data[e_channel]."""
    # Initializing channel
    if e_channel not in data:
        data[e_channel] = {}

        # Iterate each constant of the LCM message
        constants = msg_getconstants(msg)
        for const in constants:
            my_value = None
            my_value = eval("msg." + const)  # pylint: disable=W0123
            data[e_channel][const[:31]] = my_value
    # Get lcm fields and constants
    fields = msg_getfields(msg)
    # Iterate each field of the LCM message
    for field in fields:
        my_value = None
        my_value = eval(" msg." + field)  # pylint: disable=W0123
        if isinstance(my_value, (int, long, float, str, tuple, unicode)):
            try:
                data[e_channel][field[:31]].append(my_value)
            except KeyError:
                data[e_channel][field[:31]] = [my_value]

        elif hasattr(my_value, "__slots__"):
            submsg = eval("msg." + field)  # pylint: disable=W0123
            msg_to_dict(
                data[e_channel],
                field[:31],
                submsg,
                status_msg,
                verbose,
                decompress_jpeg=decompress_jpeg,
                depth_image_shape=depth_image_shape,
            )

        # Handles getting RBGD data from 'images' field
        elif (
            field == "images"
            and isinstance(my_value, list)
            and isinstance(my_value[0], image_t)
        ):
            if decompress_jpeg:
                # Read image_t.data to numpy arrays
                rgb_image = np.array(imageio.imread(my_value[0].data))
            else:
                # Else, keep RGB data compressed
                rgb_image = my_value[0].data
            depth_data = zlib.decompress(my_value[1].data)
            depth_image = np.frombuffer(depth_data, dtype="uint16").reshape(
                depth_image_shape
            )
            try:
                data[e_channel]["RGB"].append(rgb_image)
                data[e_channel]["depth"].append(depth_image)
            except KeyError:
                data[e_channel]["RGB"] = [rgb_image]
                data[e_channel]["depth"] = [depth_image]
        else:
            if verbose:
                status_msg = delete_status_message(status_msg)
                sys.stderr.write(
                    "ignoring field %s from channel %s. \n"
                    % (field, e_channel)
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
    fname, opts=None, decompress_jpeg=True, depth_image_shape=(480, 640)
):  # pylint: disable=R1710
    # pylint: disable=R0914,R0912,R0915
    """Parse LCM log.

    Keyword arguments:
    fname -- absolute path to LCM log, relative path is not supported
    opts -- dict of options. Default None returns dict
    decompress_jpeg -- whether or not to decompress jpeg. Default True
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
    if verbose:
        print("Searching for LCM types...")
    type_db = make_lcmtype_dictionary()

    channelsToProcess = re.compile(channelsToProcess)
    channelsToIgnore = re.compile(channelsToIgnore)
    log = EventLog(fname, "r")

    if printOutput:
        print("opened % s, printing output to %s \n" % (fname, printFname))
    ignored_channels = []
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
                sys.stderr.write("ignoring channel %s\n" % e.channel)
            ignored_channels.append(e.channel)
            continue

        packed_fingerprint = e.data[:8]
        lcmtype = type_db.get(packed_fingerprint, None)
        if not lcmtype:
            if verbose:
                status_msg = delete_status_message(status_msg)
                sys.stderr.write(
                    "ignoring channel %s -not a known LCM type\n" % e.channel
                )
            ignored_channels.append(e.channel)
            continue
        try:
            msg = lcmtype.decode(e.data)
        except:  # noqa: E722  pylint: disable=W0702
            status_msg = delete_status_message(status_msg)
            sys.stderr.write(
                "error: couldn't decode msg on channel %s\n" % e.channel
            )
            continue

        msgCount = msgCount + 1
        if printOutput and (msgCount % 5000) == 0:
            status_msg = delete_status_message(status_msg)
            status_msg = "read % d messages, % d %% done" % (
                msgCount,
                log.tell() / float(log.size()) * 100,
            )
            sys.stderr.write(status_msg)
            sys.stderr.flush()

        msg_to_dict(
            data,
            e.channel,
            msg,
            status_msg,
            verbose,
            (e.timestamp - startTime) / 1e6,
            decompress_jpeg=decompress_jpeg,
            depth_image_shape=depth_image_shape,
        )

    delete_status_message(status_msg)
    if verbose:
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
            loadFunc = """function [d imFnames]={_outBaseName}()
full_fname = '{_outFname}';
fname = '{_fullPathName}';
if (exist(full_fname,'file'))
filename = full_fname;
else
filename = fname;
end
d = load(filename);
""".format(
                _outBaseName=outBaseName,
                _outFname=outFname,
                _fullPathName=fullPathName,
            )
            print(loadFunc)
            mfile.write(loadFunc)

    return data
