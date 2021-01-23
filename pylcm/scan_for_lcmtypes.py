#!/usr/bin/python3
"""Find all lcmtypes defined in the system by waorking through the paths."""
import os
import pyclbr
import re
import sys
from io import open


def find_lcmtypes():  # noqa: C901, pylint: disable=R0912
    """Find lcm types."""
    alpha_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    valid_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    )
    _lcmtypes = []
    regex = re.compile("_get_packed_fingerprint")

    dirs_to_check = sys.path
    if os.getenv("LCMPATH"):
        dirs_to_check += os.getenv("LCMPATH").split(":")

    for dir_name in dirs_to_check:
        for root, dirs, files in os.walk(dir_name):
            subdirs = root[len(dir_name) :].split(os.sep)
            subdirs = [s for s in subdirs if s]

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
                    with open(full_fname, "r", encoding="latin1") as f:
                        contents = f.read()
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
                    _klass = pyclbr.readmodule(modname)[mod_basename]
                    if (
                        "decode" in _klass.methods
                        and "_get_packed_fingerprint" in _klass.methods
                    ):

                        _lcmtypes.append(modname)
                except ImportError:
                    continue
                except KeyError:
                    continue

            # only recurse into subdirectories that correspond to python
            # packages (i.e., they contain a file named "__init__.py")
            subdirs_to_traverse = [
                subdir_name
                for subdir_name in dirs
                if os.path.exists(
                    os.path.join(root, subdir_name, "__init__.py")
                )
            ]
            del dirs[:]
            dirs.extend(subdirs_to_traverse)
    return _lcmtypes


def make_lcmtype_dictionary():
    """Create a dictionary of LCM types keyed by fingerprint.

    Searches the specified python package directories for modules
    corresponding to LCM types, imports all the discovered types into the
    global namespace, and returns a dictionary mapping packed fingerprints
    to LCM type classes.

    The primary use for this dictionary is to automatically identify and
    decode an LCM message.
    """
    result = {}
    for lcmtype_name in find_lcmtypes():
        try:
            __import__(lcmtype_name)
            mod = sys.modules[lcmtype_name]
            type_basename = lcmtype_name.split(".")[-1]
            _klass = getattr(mod, type_basename)
            _fingerprint = _klass._get_packed_fingerprint()
            result[_fingerprint] = _klass
        except Exception as e:  # pylint: disable=W0703 (broad-except)
            print(f"Error importing {lcmtype_name}: {e}")
    return result


if __name__ == "__main__":
    import binascii

    print("Searching for LCM types...")
    lcmtypes = make_lcmtype_dictionary()
    num_types = len(lcmtypes)
    print("Found %d type%s" % (num_types, num_types == 1 and "" or "s"))
    for fingerprint, klass in lcmtypes.items():
        print(binascii.hexlify(fingerprint), klass.__module__)
