#!/usr/bin/python

import re
import sys

with open( sys.argv[1] ) as fp:
    for line in fp:
        matches = re.findall( "\x1b\[[0-9;]*[a-zA-Z]", line )
        if matches is not None and len( matches ) > 0:
            for match in matches:
                line = line.replace( match, "")
        print( line.rstrip() )
