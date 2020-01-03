#!/usr/bin/python

import argparse
import json
import os
import shutil
import tempfile
import urllib2

class TextColor:
    @classmethod
    def yellow( cls, text ):
        return '\033[0;33m%s\033[0m' % text

class LogViewer:
    def __init__( self, url ):
        self.url = url[0:-1] if url.endswith("/") else url

    def list_nodes( self ):
        r = urllib2.urlopen( "%s/nodes" % self.url )
        nodes = json.loads( r.read() )
        print "\n".join( nodes )

    def list_logs( self, path ):
        r = urllib2.urlopen( "%s/list?path=%s" % ( self.url, path ) )
        self.display( r.read() )

    def download_log_file( self, filename, dest, log_view_func = None ):
        r = urllib2.urlopen( "%s/download?path=%s" % ( self.url, filename) )
        with open( dest, "wb" ) as fp:
            shutil.copyfileobj( r, fp )
        if os.path.isfile( dest ) and log_view_func is not None:
            log_view_func( dest )

    def download_log_file_to_temp( self, filename, log_view_func = None ):
        f, dest = tempfile.mkstemp()
        os.close( f )
        self.download_log_file( filename, dest, log_view_func )
        os.remove( dest )

    def edit_log_file( self, filename ):
        self.download_log_file_to_temp( filename, lambda f: os.system( "vi %s" % f ) )

    def cat_log_file( self, filename ):
        self.download_log_file_to_temp( filename, lambda f: os.system( "cat %s" % f ) )

    def tail_log_file( self, filename, lines ):
        self.download_log_file_to_temp( filename, lambda f: os.system( "tail -n %d %s" % ( lines, f ) ) )

    def grep_log_file( self, path, pattern, recursive = False ):
        data = json.dumps( {'path': path, 'pattern': pattern, 'recursive': recursive } )
        r = urllib2.urlopen( "%s/grep" % self.url, data = data )
        self.display( r.read() )

    def find_log_file( self, path, pattern ):
        data = json.dumps( {'path': path, 'pattern': pattern } )
        r = urllib2.urlopen( "%s/find" % self.url, data = data )
        self.display( r.read() )

    def shell( self, nodes, script ):
        data = {'script': script }
        if nodes is not None and len( nodes ) > 0:
            data['nodes'] = nodes
        r = urllib2.urlopen( "%s/shell" % self.url, data = json.dumps( data ) )
        self.display( r.read() )

    def display( self, data ):
        try:
            node_data = json.loads( data )
            for name in node_data:
                print TextColor.yellow( "From node %s" % name )
                print node_data[ name ]
        except Exception as ex:
            print data


def get_url( args ):
    if args.url is not None:
        return args.url

def create_log_viewer( url ):
    return LogViewer( url )

def list_nodes( args ):
    create_log_viewer( args.url ).list_nodes()
def list_logs( args ):
    create_log_viewer( args.url ).list_logs( args.path )

def download_log_file( args ):
    create_log_viewer( args.url ).download_log_file( args.file, args.dest )

def edit_log( args ):
    create_log_viewer( args.url ).edit_log_file( args.file )

def find_log_files( args ):
    create_log_viewer( args.url ).find_log_file( args.path, args.pattern )

def grep_log( args ):
    create_log_viewer( args.url ).grep_log_file( args.path, args.pattern, recursive = args.recursive )

def cat_log( args ):
    create_log_viewer( args.url ).cat_log_file( args.file )

def tail_log( args ):
    create_log_viewer( args.url ).tail_log_file( args.file, args.lines )

def execute_shell( args ):
    create_log_viewer( args.url ).shell( args.nodes, args.script )

def parse_args():
    parser = argparse.ArgumentParser( description = "NLS log viewer" )
    parser.add_argument( "--url", help = "the url to the backend logger", required = False )
    subparsers = parser.add_subparsers( help = "sub commands" )
    ls_parser = subparsers.add_parser( "ls", help = "list all the files" )
    ls_parser.add_argument( "path", help = "the log path" )
    ls_parser.set_defaults( func = list_logs )

    node_parser = subparsers.add_parser( "nodes", help = "list all the nodes" )
    node_parser.set_defaults( func = list_nodes )


    download_parser = subparsers.add_parser( "download", help = "download file" )
    download_parser.add_argument( "file", help = "the remote log file" )
    download_parser.add_argument( "dest", help = "the local file name" )
    download_parser.set_defaults( func = download_log_file )

    edit_parser = subparsers.add_parser( "edit", help = "edit the given files" )
    edit_parser.add_argument( "file", help = "the file name" )
    edit_parser.set_defaults( func = edit_log )

    find_parser = subparsers.add_parser( "find", help = "find files with pattern" )
    find_parser.add_argument( "pattern", help = "the find pattern" )
    find_parser.add_argument( "path", help = "the search path" )
    find_parser.set_defaults( func = find_log_files )


    grep_parser = subparsers.add_parser( "grep", help = "grep pattern from files" )
    grep_parser.add_argument( "-r", "--recursive", help = "recursivly grep", action = "store_true" )
    grep_parser.add_argument( "pattern", help = "the grep pattern" )
    grep_parser.add_argument( "path", help = "the directory" )
    grep_parser.set_defaults( func = grep_log )

    cat_parser = subparsers.add_parser( "cat", help = "show the content of specified file" )
    cat_parser.add_argument( "file", help = "the remote file name" )
    cat_parser.set_defaults( func = cat_log )

    tail_parser = subparsers.add_parser( "tail", help = "show the content of specified file" )
    tail_parser.add_argument( "-n", "--lines", help = "number of lines to show", type = int, default = 10 )
    tail_parser.add_argument( "file", help = "the remote file name" )
    tail_parser.set_defaults( func = tail_log )

    shell_parser = subparsers.add_parser( "shell", help = "execute shell script" )
    shell_parser.add_argument( "script", help = "the shell script" )
    shell_parser.add_argument( "--nodes", nargs = "*", help = "the nodes" )
    shell_parser.set_defaults( func = execute_shell )

    return parser.parse_args()


def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
