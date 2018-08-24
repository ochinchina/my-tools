#!/usr/bin/python

import re
import subprocess
import sys

def get_terminal_max_lines():
    try:
        return int( subprocess.check_output( ['tput', 'lines'] ).strip() )
    except:
        pass

    try:
        return int( subprocess.check_output( ['stty', 'size'] ).split()[0] )
    except:
        pass

    try:
        out = subprocess.check_output( ['stty', '-a' ] )
        for line in out.split( "\n" ):
            fields = line.split( ";" )
            for field in fields:
                words = field.split()
                if len( words ) == 2 and words[0] == 'rows': return int( words[1] )
    except:
        pass

    return 50

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


class LineReader:
    def __init__( self, filename ):
        self.filename = filename
        self.fobj = None

    def __enter__( self ):
        if self.filename == None:
            return sys.stdin
        else:
            self.fobj = open( self.filename )
            return self.fobj

    def __exit__( self, *args ):
        if self.fobj is not None:
            self.fobj.close()

def read_line( filename, line_proc_func ):
    if filename is not None:
        with open( filename ) as fp:
            for line in fp:
                line_proc_func( line )
    else:
        for line in sys.stdin:
            line_proc_func( line )
        
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
    lines = 0
    max_lines_in_terminal = get_terminal_max_lines()
    with LineReader( filename ) as fp:
       for line in fp:
           lines += 1
           if lines % max_lines_in_terminal == 0:
               if filename is not None: raw_input()
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
    color_output_file( sys.argv[1] if len( sys.argv ) > 1 else None )
