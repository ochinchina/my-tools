#!/usr/bin/python

import argparse
import os
import sys

def eval_var( s ):
    pos = s.find( ':' )
    if pos == -1:
        return os.environ[s] if s in os.environ else ""
    else:
        varname = s[0:pos]
        value = s[pos+1:]
        if value.startswith( '-' ):
            value = value[1:]
        if varname in os.environ:
            value = os.environ[varname]
        return value

def expandvars( s ):
    s = os.path.expandvars( s )
    while True:
        start = s.find( '${')
        if start == -1:
            return s
        end = s.find( '}', start )
        if end == -1:
            return s
        s = s[0:start] + eval_var( s[start+2:end] ) + s[ end+1: ]

def parse_args():
    parser = argparse.ArgumentParser( description = "envsust in python")
    parser.add_argument( "--output", "-o", help = "output file" )
    parser.add_argument( "filename", help = "the input filename or - from stdin" )
    return parser.parse_args()

def expandvars_in_file( infile, outfile ):
    for line in infile:
        outfile.write( expandvars( line ) )

def main():
    args = parse_args()
    outfile = open( args.output, "w" ) if args.output is not None else sys.stdout
    infile = sys.stdin if args.filename == '-' else open( args.filename )
    expandvars_in_file( infile, outfile)
    if outfile != sys.stdout: outfile.close()
    if infile != sys.stdin: infile.close()

if __name__ == "__main__":
    main()
