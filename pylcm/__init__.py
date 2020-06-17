#!/usr/bin/python
#
# Converts a LCM log to a "structured" format that is easier to work with
# external tools such as Matlab or Python. The set of messages on a given
# channel can be represented as a structure preserving the original lcm message
# structure.
# 
# pylcm is based on lcm-log2smat which is based on libbot2 script bot-log2mat.
# Modified by Duan Yutong, MKuoch

import os
import sys
import re
import pickle
long    = int
unicode = int
import scipy.io.matlab.mio
from lcm import EventLog
from .scan_for_lcmtypes import make_lcmtype_dictionary
import robotlocomotion as rl
import inspect
import imageio
import numpy as np
from io import BytesIO
from bot_core import image_t

longOpts = ["help", "print", "pickle", "format", "separator", "channelsToProcess", "ignore", "outfile", "lcm_packages"]

def usage():
    pname, sname = os.path.split(sys.argv[0])
    sys.stderr.write("usage: % s %s < filename > \n" % (sname, str(longOpts)))
    print( """
    -h --help                 print this message
    -p --print                Output log data to stdout instead of to .mat or .pkl
    -k --pickle               Output log data to python pickle .pkl instead of to .mat
    -f --format               print the data format to stderr
    -s --seperator=sep        print data with separator [sep] instead of default to ["" ""]
    -c --channelsToProcess=chan        Parse channelsToProcess that match Python regex [chan] defaults to [".*"]
    -i --ignore=chan          Ignore channelsToProcess that match Python regex [chan]
                              ignores take precedence over includes!
    -o --outfile=ofname       output data to [ofname] instead of default [filename.mat or filename.pkd or stdout]
    -l --lcmtype_pkgs=pkgs    load python modules from comma seperated list of packages [pkgs] defaults to ["botlcm"]
    -v                        Verbose

    """ )
    sys.exit()


def msg_getfields (lcm_msg):
    return lcm_msg.__slots__


def msg_getconstants (lcm_msg):
    # Get full list of valid attributes
    fulllist = dir(lcm_msg)
    # Get constants
    constantslist = [x for x in fulllist if not(x[0]=='_') 
                    if not(x=='decode')
                    if not(x=='encode')
                    if x not in msg_getfields (lcm_msg)]
    return constantslist


def msg_to_dict (data, e_channel, msg, status_msg, verbose=False, lcm_timestamp=-1):

    # Initializing channel
    if e_channel not in data:
        data[e_channel] = dict()

        # Iterate each constant of the LCM message
        constants = msg_getconstants (msg)
        for i in range(len(constants)):
            my_value = None
            my_value = eval('msg.' + constants[i])
            data[e_channel][constants[i][:31]] = my_value

    # Get lcm fields and constants
    fields = msg_getfields (msg)

    # Iterate each field of the LCM message
    for i in range(len(fields)):
        my_value = None
        my_value = eval(' msg.' + fields[i])
        if (isinstance(my_value,int)     or
            isinstance(my_value,long)    or 
            isinstance(my_value,float)   or 
            isinstance(my_value,tuple)   or 
            isinstance(my_value,unicode) or 
            isinstance(my_value,str)):
            try:
                data[e_channel][fields[i][:31]].append(my_value)
            except KeyError as AttributeError:
                data[e_channel][fields[i][:31]] = [(my_value)]
                
        elif (hasattr(my_value,'__slots__')):
            submsg = eval('msg.' + fields[i])
            msg_to_dict (data[e_channel], fields[i][:31], submsg, status_msg, verbose)
        
        # Handles getting RBGD data from 'images' field
        elif (fields[i] == "images" and 
              isinstance(my_value, list) and 
              isinstance(my_value[0], image_t)):
            # Read image_t.data to numpy arrays
            color_image = np.array(imageio.imread(my_value[0].data))
            #depth_image = np.array(imageio.imread(my_value[1].data))
            try:
                data[e_channel]['RGB'].append(color_image)
                #data[e_channel]['Depth'].append(depth_image)
            except KeyError as AttributeError:
                data[e_channel]['RGB'] = [(color_image)]
                #data[e_channel]['Depth'] = [(depth_image)]
        else:
            if verbose:
                status_msg = delete_status_message(status_msg)
                sys.stderr.write("ignoring field %s from channel %s. \n" %(fields[i], e_channel))
            continue

    # Add extra field with lcm_timestamp
    if lcm_timestamp > 0:
        try:
            data[e_channel]['lcm_timestamp'].append(lcm_timestamp)
        except KeyError as AttributeError:
            data[e_channel]['lcm_timestamp'] = [(lcm_timestamp)]


def delete_status_message(stat_msg):
    if stat_msg:
        sys.stderr.write("\r")
        sys.stderr.write(" " * (len(stat_msg)))
        sys.stderr.write("\r")
    return ""

def parse_lcm(fname, opts=None):
    """fname is the path to LCM log, opts is a dict of options
    
    Bu default, if opts=None, return dict.
    """
    #default options
    lcm_packages = [ "botlcm"]

    verbose = False
    printOutput = False
    savePickle  = False
    printFormat = False
    channelsToIgnore = ""
    checkIgnore = False
    channelsToProcess = ".*"
    separator = ' '
    returnDict = False
    if opts is None:
        returnDict = True
    else:
        for o, a in opts.items():
            if o == "-v":
                verbose = True
            elif o in ("-h", "--help"):
                usage()
            elif o in ("-p", "--print"):
                printOutput = True
            elif o in ("-k", "--pickle"):
                savePickle = True
            elif o in ("-f", "--format"):
                printFormat = True
            elif o in ("-s", "--separator="):
                separator = a
            elif o in ("-o", "--outfile="):
                outFname = a
                printFname = a
            elif o in ("-c", "--channelsToProcess="):
                channelsToProcess = a
            elif o in ("-i", "--ignore="):
                channelsToIgnore = a
                checkIgnore = True
            elif o in ("-l", "--lcm_packages="):
                lcm_packages = a.split(",")
            else:
                assert f"unhandled option key {o}, value{a}"

    try:
        outFname
    except NameError:
        outDir, outFname = os.path.split(os.path.abspath(fname))
       
        if savePickle:
            outFname = outDir + "/" + outFname + ".pkl"
        else:
            outFname = outFname.replace(".", "_")
            outFname = outFname.replace("-", "_")
            outFname = outDir + "/" + outFname + ".mat"



    fullPathName = os.path.abspath(outFname)
    dirname = os.path.dirname(fullPathName)
    outBaseName = ".".join(os.path.basename(outFname).split(".")[0:-1])
    fullBaseName = dirname + "/" + outBaseName

    data = {}
    if printOutput:
        print("Searching for LCM types...")
    type_db = make_lcmtype_dictionary()

    channelsToProcess = re.compile(channelsToProcess)
    channelsToIgnore = re.compile(channelsToIgnore)
    log = EventLog(fname, "r")

    if printOutput:
        sys.stdout.write("opened % s, printing output to %s \n" % (fname, printFname))
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
        if ((checkIgnore and channelsToIgnore.match(e.channel) and len(channelsToIgnore.match(e.channel).group())==len(e.channel)) \
             or (not channelsToProcess.match(e.channel))):
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
                sys.stderr.write("ignoring channel %s -not a known LCM type\n" % e.channel)
            ignored_channels.append(e.channel)
            continue
        try:
            msg = lcmtype.decode(e.data)
        except:
            status_msg = delete_status_message(status_msg)
            sys.stderr.write("error: couldn't decode msg on channel %s\n" % e.channel)
            continue
        
        msgCount = msgCount + 1
        if printOutput and (msgCount % 5000) == 0:
            status_msg = delete_status_message(status_msg)
            status_msg = "read % d messages, % d %% done" % (msgCount, log.tell() / float(log.size())*100)
            sys.stderr.write(status_msg)
            sys.stderr.flush()
        
        msg_to_dict (data, e.channel, msg, status_msg, verbose, (e.timestamp - startTime) / 1e6)

    if returnDict:
        return data
    
    delete_status_message(status_msg)
    if not printOutput:
                
        sys.stderr.write("loaded all %d messages, saving to % s\n" % (msgCount, outFname))

        if savePickle:

            # Pickle the list/dictonary using the highest protocol available.
            with open(outFname, 'wb') as f:
                pickle.dump(data, f, -1)
        else:
            # Matlab format using scipy
            if sys.version_info < (2, 6):
                scipy.io.mio.savemat(outFname, data)
            else:
                scipy.io.matlab.mio.savemat(outFname, data, oned_as='row')


            with open(dirname + "/" + outBaseName + ".m", "w", encoding='utf-8') as mfile:
                loadFunc = """function [d imFnames]={_outBaseName}()
full_fname = '{_outFname}';
fname = '{_fullPathName}';
if (exist(full_fname,'file'))
    filename = full_fname;
else
    filename = fname;
end
d = load(filename);
""".format(_outBaseName=outBaseName, _outFname=outFname, _fullPathName=fullPathName)
            
                print(loadFunc)
                mfile.write(loadFunc)
