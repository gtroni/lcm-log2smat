##lcm-log2smat
-----
'lcm-log2smat' is a python utility to convert LCM log files to Matlab (.mat) or
Python Pickle (.pkl) files.

The script converts a LCM log to a "structured" format that is easier to work
with external tools such as Matlab or Python. The set of messages on a given
channel can be represented as a structure preserving the original LCM message
structure. 'lcm-log2smat' is based on 'libbot2' script 'bot-log2mat'.


###Run
-----
To convert a LCM log file (data.lcm) to a Matlab file (data.mat)
$ ./lcm-log2smat data.lcm -o data.mat

To convert a LCM log file (data.lcm) to Python Pickle file (data.pkd)
$ ./lcm-log2smat data.lcm -k  -o data.mat


###Licenses
-----

libbot2 is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published 
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

libbot2 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.



lcm-log2smat is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published 
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

lcm-log2smat is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.



You should have received a copy of the GNU Lesser General Public License
along with lcm-log2smat.  If not, see <http://www.gnu.org/licenses/>.
