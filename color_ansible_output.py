#!/usr/bin/python

import re
import sys

def green():
    sys.stdout.write( '\033[0;32m' )

def grey():
    sys.stdout.write( '\033[0;37m' )

def normal():
    sys.stdout.write( '\033[0m' )

def white():
    sys.stdout.write( '\033[1;37m')

def yellow():
    sys.stdout.write( '\033[1;33m' )

def red():
    sys.stdout.write( '\033[0;31m' )

def blue():
    sys.stdout.write( '\033[0;34m' )

def cyan():
    sys.stdout.write( '\033[0;36m' )

def find_space( s, start ):
    n = len( s )
    while start < n:
        if s[start].isspace():
            return start
        else:
            start += 1
    return start

def find_non_space( s, start ):
    n = len( s )
    while start < n:
        if not s[start].isspace():
            return start
        else:
            start += 1
    return start

def color_play_recap( line ):
    index = line.find( ':' )
    if index > 0:
        yellow()
        sys.stdout.write( line[0:index] )
        index += 1
        white()
        sys.stdout.write( ':' )
        end = find_non_space( line, index )
        end = find_space( line, end )
        green()
        sys.stdout.write( line[index:end] )
        index = end + 1
        end = find_non_space( line, index )
        end = find_space( line, end )
        yellow()
        sys.stdout.write( line[index:end] )
        white()
        sys.stdout.write( line[ end + 1:] )
        
def color_output_file( filename ):
    line_colors = {
                   r"changed:": yellow,
                   r"ok": green,
                   r"TASK": white,
                   r"PLAY": white,
                   r"ansible-playbook \d": blue,
                   r"ansible-playbook": white,
                   r"<": blue,
                   r"META:": blue,
                   r"fatal:": red,
                   r"task path:": grey,
                   r"skipping:": cyan,
                   r"...ignoring": cyan,
                   r"\d+ plays": green
                  }
    playRecap = False
    with open( filename ) as fp:
       for line in fp:
           color_found = False
           for k, v in line_colors.iteritems():
               if re.match( k, line ):
                   color_found = True
                   v()
           if playRecap:
               color_play_recap( line )
           else:
               sys.stdout.write( line )
           playRecap = line.startswith( "PLAY RECAP" )

    normal() 

if __name__ == "__main__":
    color_output_file( sys.argv[1] )
