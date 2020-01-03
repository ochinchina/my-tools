#!/usr/bin/python

import argparse
import logging
from flask import Flask,request,send_file
import json
import os
import subprocess
import threading
import time
import urllib2

def which( process ):
    try:
        return subprocess.check_output(['which', process]).strip()
    except Exception as ex:
        return None

def get_shell():
    return which( '/bin/bash' ) or which( '/bin/sh' )

class LogServer:
    def __init__( self, log_dir ):
        os.chdir( log_dir )
        self.log_dir = log_dir

    def list_files( self ):
        try:
            path = request.args['path'] if 'path' in request.args else "."
            command = [ get_shell(), "-c", "ls --color=always -lrt %s" % self._get_path( path ) ]
            return subprocess.check_output( command )
        except subprocess.CalledProcessError as ex:
            return ex.output

    def download_file( self ):
        try:
            path = self._get_path( request.args['path'] ) if 'path' in request.args else None
            if path is None:
                return "Missing path parameter"
            if not os.path.isfile( path ):
                return "%s is not file or does not exist" % path
            return send_file( path )
        except Exception as ex:
            return "%s" % ex

    def grep_file( self ):
        try:
            req_info = json.load( request.stream )
            print req_info
            path = req_info['path'] if 'path' in req_info else None
            pattern = req_info['pattern'] if 'pattern' in req_info else None
            recursive = req_info['recursive'] if 'recursive' in req_info else False
            shell = get_shell()
            path = self._get_path( path )
            if os.path.isdir( path ):
                path = os.path.join( path, '*' )
            command = [shell, "-c", "grep -d %s --color=always '%s' %s" % ( 'recurse' if recursive else 'read', pattern, path ) ]
            print command
            return subprocess.check_output( command )
        except subprocess.CalledProcessError as ex:
            return ex.output

    def find_file( self ):
        try:
            req_info = json.load( request.stream )
            path = req_info['path'] if 'path' in req_info else None
            pattern = req_info['pattern'] if 'pattern' in req_info else None
            shell = get_shell()
            command = [shell, "-c", "find %s -name '%s'" % ( self._get_path( path ), pattern ) ]
            print command
            return subprocess.check_output( command )
        except subprocess.CalledProcessError as ex:
            return ex.output

    def shell( self ):
        try:
            req_info = json.load( request.stream )
            script = req_info['script']
            shell = get_shell()
            command = [shell, "-c", script ]
            return subprocess.check_output( command )
        except Exception as ex:
            print ex
            return "%s" % ex
    def _get_path( self, path ):
        print path
        path = os.path.split( path )
        print path
        path = "/".join( path[1:] if path[0] == '/' or len( path[0] ) <= 0 else path )
        print path
        return os.path.join( self.log_dir, path )

def register_server( register_name, register_url, log_proxy, register_interval = 10 ):
    server_info = json.dumps( {'name': register_name, 'url': register_url})
    while True:
        try:
            urllib2.urlopen( "%s/register" % log_proxy, data = server_info )
        except Exception as ex:
            print ex
        time.sleep( register_interval )

def parse_args():
    parser = argparse.ArgumentParser( description = "log server" )
    parser.add_argument( "--dir", help = "the log directory, default is ./", default = "./" )
    parser.add_argument( "--host", help = "the ip or host to listen,default is 127.0.0.1", default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the listening port, default is 5000", default = 5000, type = int )
    parser.add_argument( "--register-name", help = "the register name" )
    parser.add_argument( "--register-url", help = "the url registered to log proxy" )
    parser.add_argument( "--log-proxy", help = "the log proxy url" )
    return parser.parse_args()

def main():
    args = parse_args()
    if args.register_url is not None and args.log_proxy is not None:
        th = threading.Thread( target = register_server, args = ( args.register_name, args.register_url, args.log_proxy ) )
        th.setDaemon( True )
        th.start()

    logserver = LogServer( args.dir )
    app = Flask(__name__)
    app.add_url_rule( "/list", "list", logserver.list_files, methods=['GET'])
    app.add_url_rule( "/download", "download", logserver.download_file, methods=['GET'] )
    app.add_url_rule( "/grep", "grep", logserver.grep_file, methods=["POST"] )
    app.add_url_rule( "/find", "find", logserver.find_file, methods=["POST"] )
    app.add_url_rule( "/shell", "shell", logserver.shell, methods=["POST"] )
    app.run( host = args.host, port = args.port, debug = True, use_reloader = False )

if __name__ == "__main__":
    main()
