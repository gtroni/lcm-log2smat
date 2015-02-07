#!/usr/bin/python
#
# Converts a LCM log to a "structured" format that is easier to work with
# external tools such as Matlab or Python. The set of messages on a given
# channel can be represented as a structure preserving the original lcm message
# structure.
# 
# lcm-log2smat is based on libbot2 script bot-log2mat.
# Modified by G.Troni

import os
import sys
import binascii
import types
import numpy
import re
import getopt
import cPickle as pickle
import pyclbr

# check which version for mio location
if sys.version_info < (2, 6):
    import scipy.io.mio
else:
    import scipy.io.matlab.mio

from lcm import EventLog


def usage():
    pname, sname = os.path.split(sys.argv[0])
    sys.stderr.write("usage: % s %s < filename > \n" % (sname, str(longOpts)))
    print """
    -h --help                 print this message
    -p --print                Output log data to stdout instead of to .mat or .pkl
    -k --pickle               Output log data to python pickle .pkl instead of to .mat
    -t --pickle-struct        python pickle data format as a structure instead of dictionary
    -f --format               print the data format to stderr
    -s --seperator=sep        print data with separator [sep] instead of default to ["" ""]
    -c --channelsToProcess=chan        Parse channelsToProcess that match Python regex [chan] defaults to [".*"]
    -i --ignore=chan          Ignore channelsToProcess that match Python regex [chan]
                              ignores take precedence over includes!
    -o --outfile=ofname       output data to [ofname] instead of default [filename.mat or filename.pkd or stdout]
    -l --lcmtype_pkgs=pkgs    load python modules from comma seperated list of packages [pkgs] defaults to ["botlcm"]
    -v                        Verbose

    """
    sys.exit()



def find_lcmtypes():
    alpha_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    lcmtypes = []
    regex = re.compile("_get_packed_fingerprint")
    
    dirs_to_check = sys.path

    for dir_name in dirs_to_check:
        for root, dirs, files in os.walk(dir_name):
            subdirs = root[len(dir_name):].split(os.sep)
            subdirs = [ s for s in subdirs if s ]

            python_package = ".".join(subdirs)

            for fname in files:
                if not fname.endswith(".py"):
                    continue
                
                mod_basename = fname[:-3]
                valid_modname = True
                for c in mod_basename:
                    if c not in valid_chars:
                        valid_modname = False
                        break
                if mod_basename[0] not in alpha_chars:
                    valid_modname = False
                if not valid_modname:
                    continue

                # quick regex test -- check if the file contains the 
                # word "_get_packed_fingerprint"
                full_fname = os.path.join(root, fname)
                try: 
                    contents = open(full_fname, "r").read()
                except IOError:
                    continue
                if not regex.search(contents):
                    continue
                
                # More thorough check to see if the file corresponds to a
                # LCM type module genereated by lcm-gen.  Parse the 
                # file using pyclbr, and check if it contains a class
                # with the right name and methods
                if python_package:
                    modname = "%s.%s" % (python_package, mod_basename)
                else:
                    modname = mod_basename
                try:
                    klass = pyclbr.readmodule(modname)[mod_basename]
                    if "decode" in klass.methods and \
                       "_get_packed_fingerprint" in klass.methods:

                        lcmtypes.append(modname)
                except ImportError:
                    continue
                except KeyError:
                    continue

            # only recurse into subdirectories that correspond to python 
            # packages (i.e., they contain a file named "__init__.py")
            subdirs_to_traverse = [ subdir_name for subdir_name in dirs \
                    if os.path.exists(os.path.join(root, subdir_name, "__init__.py")) ]
            del dirs[:]
            dirs.extend(subdirs_to_traverse)
    return lcmtypes

def make_lcmtype_dictionary():
    """Create a dictionary of LCM types keyed by fingerprint.

    Searches the specified python package directories for modules 
    corresponding to LCM types, imports all the discovered types into the
    global namespace, and returns a dictionary mapping packed fingerprints
    to LCM type classes.

    The primary use for this dictionary is to automatically identify and 
    decode an LCM message.

    """
    lcmtypes = find_lcmtypes()

    result = {}

    for lcmtype_name in lcmtypes:
        try:
            __import__(lcmtype_name)
            mod = sys.modules[lcmtype_name]
            type_basename = lcmtype_name.split(".")[-1]
            klass = getattr(mod, type_basename)
            fingerprint = klass._get_packed_fingerprint()
            result[fingerprint] = klass
            #print "importing %s" % lcmtype_name
        except:
            print "Error importing %s" % lcmtype_name
    return result
 
if __name__ == "__main__":
    import binascii
    print("Searching for LCM types...")
    lcmtypes = make_lcmtype_dictionary()
    num_types = len(lcmtypes)
    print("Found %d type%s" % (num_types, num_types==1 and "" or "s"))
    for fingerprint, klass in lcmtypes.items():
        print binascii.hexlify(fingerprint), klass.__module__


class structtype():
        pass


def msg_to_struct (data, event_channel, msg, statusMsg, lcm_timestamp=-1):

    # Initializing channel
    e_channel = event_channel.replace('.','_')
    if e_channel not in data.__dict__:
        exec(compile('data.' + e_channel + ' = structtype()', '<string>', 'exec'))

    # Temporary variable (linking to channel)
    exec(compile('data_e_channel = data.' + e_channel, '<string>', 'exec'))

    # Iterate each field of the LCM message
    for i in xrange(len(msg.__slots__)):

        myValue = None
        exec(compile('myValue = msg.' + msg.__slots__[i], '<string>', 'exec'))

        if (isinstance(myValue,int) or isinstance(myValue,float) or isinstance(myValue,tuple) or isinstance(myValue,str)):
            if msg.__slots__[i] not in data_e_channel.__dict__:
                exec(compile('data_e_channel.' + msg.__slots__[i] + ' = [(myValue)]', '<string>', 'exec'))
            else:
                exec(compile('data_e_channel.' + msg.__slots__[i] + '.append(myValue)', '<string>', 'exec'))
        
        elif (hasattr(myValue,'__slots__')):
            exec(compile('submsg = msg.' + msg.__slots__[i], '<string>', 'exec'))
            msg_to_struct (data_e_channel, msg.__slots__[i], submsg, statusMsg)        
        else:
            if verbose:
                statusMsg = deleteStatusMsg(statusMsg)
                sys.stderr.write("ignoring field %s from channel %s. \n" %(msg.__slots__[i], event_channel))
            continue
             
    # Add extra field with lcm_timestamp
    if lcm_timestamp > 0:
        if '__lcm_timestamp__' not in data_e_channel.__dict__:
            exec(compile('data_e_channel.__lcm_timestamp__'  + ' = [(lcm_timestamp)]', '<string>', 'exec'))
        else:
            exec(compile('data_e_channel.__lcm_timestamp__'  + '.append(lcm_timestamp)', '<string>', 'exec'))




def msg_to_dict (data, e_channel, msg, statusMsg, lcm_timestamp=-1):

    # Initializing channel
    if e_channel not in data:
        data[e_channel] = dict()
        
    # Iterate each field of the LCM message
    for i in xrange(len(msg.__slots__)):
        myValue = None
        exec(compile('myValue = msg.' + msg.__slots__[i], '<string>', 'exec'))
        if (isinstance(myValue,int) or isinstance(myValue,float) or isinstance(myValue,tuple) or isinstance(myValue,str)):
            try:
                data[e_channel][msg.__slots__[i]].append(myValue)
            except KeyError, AttributeError:
                data[e_channel][msg.__slots__[i]] = [(myValue)]

        elif (hasattr(myValue,'__slots__')):
            exec(compile('submsg = msg.' + msg.__slots__[i], '<string>', 'exec'))
            msg_to_dict (data[e_channel], msg.__slots__[i], submsg, statusMsg)

        else:
            if verbose:
                statusMsg = deleteStatusMsg(statusMsg)
                sys.stderr.write("ignoring field %s from channel %s. \n" %(msg.__slots__[i], e_channel))
            continue

    # Add extra field with lcm_timestamp
    if lcm_timestamp > 0:
        try:
            data[e_channel]['lcm_timestamp'].append(lcm_timestamp)
        except KeyError, AttributeError:
            data[e_channel]['lcm_timestamp'] = [(lcm_timestamp)]


def deleteStatusMsg(statMsg):
    if statMsg:
        sys.stderr.write("\r")
        sys.stderr.write(" " * (len(statMsg)))
        sys.stderr.write("\r")
    return ""

longOpts = ["help", "print", "pickle", "pickle-struct", "format", "separator", "channelsToProcess", "ignore", "outfile", "lcm_packages"]

try:
    opts, args = getopt.gnu_getopt(sys.argv[1:], "hpktvfs:c:i:o:l:", longOpts)
except getopt.GetoptError, err:
    # print help information and exit:
    print str(err) # will print something like "option -a not recognized"
    usage()
if len(args) != 1:
    usage()
#default options
fname = args[0]
lcm_packages = [ "botlcm"]

printFname = "stdout"
printFile = sys.stdout
verbose = False
printOutput = False
savePickle  = False
savePickleStruct = False
printFormat = False
channelsToIgnore = ""
checkIgnore = False
channelsToProcess = ".*"
separator = ' '
for o, a in opts:
    if o == "-v":
        verbose = True
    elif o in ("-h", "--help"):
        usage()
    elif o in ("-p", "--print"):
        printOutput = True
    elif o in ("-k", "--pickle"):
        savePickle = True
    elif o in ("-t", "--pickle-struct"):
        savePickleStruct = True
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
        assert False, "unhandled option"


try:
    outFname
except NameError:
    outDir, outFname = os.path.split(os.path.abspath(fname))
    outFname = outFname.replace(".", "_")
    outFname = outFname.replace("-", "_")
    if savePickle:
        outFname = outDir + "/" + outFname + ".pkl"
    else:
        outFname = outDir + "/" + outFname + ".mat"



fullPathName = os.path.abspath(outFname)
dirname = os.path.dirname(fullPathName)
outBaseName = ".".join(os.path.basename(outFname).split(".")[0:-1])
fullBaseName = dirname + "/" + outBaseName

if savePickle and savePickleStruct:
    data = structtype()
else:
    data = {}

type_db = make_lcmtype_dictionary()

channelsToProcess = re.compile(channelsToProcess)
channelsToIgnore = re.compile(channelsToIgnore)
log = EventLog(fname, "r")

if printOutput:
    sys.stderr.write("opened % s, printing output to %s \n" % (fname, printFname))
    if printFname == "stdout":
        printFile = sys.stdout
    else:
        printFile = open(printFname, "w")
else:
    sys.stderr.write("opened % s, outputing to % s\n" % (fname, outFname))

ignored_channels = []
msgCount = 0
statusMsg = ""
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
            statusMsg = deleteStatusMsg(statusMsg)
            sys.stderr.write("ignoring channel %s\n" % e.channel)
        ignored_channels.append(e.channel)
        continue

    packed_fingerprint = e.data[:8]
    lcmtype = type_db.get(packed_fingerprint, None)
    if not lcmtype:
        if verbose:
            statusMsg = deleteStatusMsg(statusMsg)
            sys.stderr.write("ignoring channel %s -not a known LCM type\n" % e.channel)
        ignored_channels.append(e.channel)
        continue
    try:
        msg = lcmtype.decode(e.data)
    except:
        statusMsg = deleteStatusMsg(statusMsg)
        sys.stderr.write("error: couldn't decode msg on channel %s\n" % e.channel)
        continue
    
    msgCount = msgCount + 1
    if (msgCount % 5000) == 0:
        statusMsg = deleteStatusMsg(statusMsg)
        statusMsg = "read % d messages, % d %% done" % (msgCount, log.tell() / float(log.size())*100)
        sys.stderr.write(statusMsg)
        sys.stderr.flush()
    
    if savePickle and savePickleStruct:
        msg_to_struct (data, e.channel, msg, statusMsg, (e.timestamp - startTime) / 1e6)
    else:
        msg_to_dict (data, e.channel, msg, statusMsg, (e.timestamp - startTime) / 1e6)



deleteStatusMsg(statusMsg)
if not printOutput:
            
    sys.stderr.write("loaded all %d messages, saving to % s\n" % (msgCount, outFname))

    if savePickle:
        # Pickle the list using the highest protocol available.
        output = open(outFname, 'wb')
        pickle.dump(data, output, -1)
        output.close()
    else:
        # Matlab format using scipy
        if sys.version_info < (2, 6):
            scipy.io.mio.savemat(outFname, data)
        else:
            scipy.io.matlab.mio.savemat(outFname, data, oned_as='row')


        mfile = open(dirname + "/" + outBaseName + ".m", "w")
        loadFunc = """function [d imFnames]=%s()
full_fname = '%s';
fname = '%s';
if (exist(full_fname,'file'))
    filename = full_fname;
else
    filename = fname;
end
d = load(filename);
""" % (outBaseName, outFname, fullPathName)
        
        mfile.write(loadFunc);
        mfile.close()

