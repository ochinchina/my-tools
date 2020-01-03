#!/usr/bin/python

import argparse
import json
from flask import request,Flask, Response
import os
import threading
import shutil
import sys
import time
import logging
import urllib2

logger = logging.getLogger( __name__ )

class Path:
    def __init__( self, path ):
        self.path = self._split_path( path )
        self.path = [ item for item in self.path if len( item ) > 0 and item != '/' ]
        print self.path

    def has_node_name( self ):
        return len( self.path ) > 0

    def get_node_name( self ):
        return self.path[0] if self.has_node_name() else None

    def get_path_without_node( self ):
        return "/".join( self.path[1:] ) if self.has_node_name() else "."

    def _split_path( self, path ):
        r = []
        while True:
            head, tail = os.path.split( path )
            if len( tail ) <= 0:
                r.append( head )
                return list( reversed( r ) )
            else:
                path = head
                r.append( tail )


class LogServer:
    def __init__( self, name, url, timeout = 60 ):
        self.name = name
        self.url = url[0:-1] if url.endswith('/') else url
        self.expire = time.time() + timeout

    def get_name( self ):
        return self.name

    def is_expired( self ):
        return time.time() > self.expire

    def list_files( self, path ):
        """
        list all the files from remote node
        """
        print "in LogServer.list_files, url=%s, path=%s" % ( self.url, path )
        try:
            url =  "%s/list?path=%s" % ( self.url, path )
            resp = urllib2.urlopen( url )
            return resp.read()
        except Exception as ex:
            logger.error( "fail to list files from path %s with error %s" % ( path, ex ) )
            print "%s" % ex
            return "%s" % ex
    def download_file( self, path ):
        try:
            url = "%s/download?path=%s" % (self.url, path )
            resp = urllib2.urlopen( url )
            response = Response()
            shutil.copyfileobj( resp, response.stream )
            return response
        except Exception as ex:
            return "%s" % ex
    def grep_file( self, path, pattern, recursive = False ):
        try:
            url = "%s/grep" % self.url
            data = json.dumps( {'path':path,'pattern':pattern, 'recursive': recursive } )
            resp = urllib2.urlopen( url, data = data )
            return resp.read()
        except Exception as ex:
            print ex
            return ""

    def find_file( self, path, pattern ):
        try:
            url = "%s/find" % self.url
            data = json.dumps( {'path':path,'pattern':pattern} )
            print "find url=%s,data=%s" % ( url, data )
            resp = urllib2.urlopen( url, data = data )
            return resp.read()
        except Exception as ex:
            print ex
            return ""
    def shell( self, script ):
        try:
            url = "%s/shell" % self.url
            data = json.dumps( {'script': script } )
            resp = urllib2.urlopen( url, data = data )
            return resp.read()
        except Exception as ex:
            print ex
            return "%s" % ex



class LogServerMgr:
    def __init__( self ):
        self.servers = {}
        self._lock = threading.Lock()

    def add_node( self, name, url, timeout = 60 ):
        with self._lock:
            self.servers[ name ] = LogServer( name, url )
            self._remove_expired()

    def get_servers( self ):
        """
        get all the registered servers
        """
        with self._lock:
            self._remove_expired()
            return [ self.servers[name] for name in self.servers ]

    def get_server( self, name ):
        with self._lock:
            self._remove_expired()
            return self.servers[ name ] if name in self.servers else None

    def _remove_expired( self ):
        expired_servers = [ name for name in self.servers if self.servers[name].is_expired() ]
        for name in expired_servers:
            del self.servers[ name ]

class LogProxy:
    def __init__( self ):
        self.server_mgr = LogServerMgr()

    def list_nodes( self ):
        return json.dumps( [ server.get_name() for server in self.server_mgr.get_servers() ] )

    def list_files( self ):
        path = Path( request.args['path'] if 'path' in request.args else "/" )
        servers = self._get_servers( path )
        result = {}
        for server in servers:
            result[server.get_name()] = server.list_files( path.get_path_without_node() )
        return json.dumps( result )

    def download_file( self ):
        path = Path( request.args['path'] if 'path' in request.args else "/" )
        servers = self._get_servers( path )
        if len( servers ) != 1:
            return "No such file"
        else:
            return servers[0].download_file( path.get_path_without_node() )

    def grep_file( self ):
        req_info = json.load( request.stream )
        path = Path( req_info['path'] if 'path' in req_info else '/' )
        pattern = req_info['pattern']
        recursive = req_info['recursive']
        servers = self._get_servers( path )

        result = {}
        for server in servers:
            result[server.get_name()] = server.grep_file( path.get_path_without_node(), pattern, recursive = recursive )

        return json.dumps( result )

    def find_file( self ):
        req_info = json.load( request.stream )
        path = Path( req_info['path'] if 'path' in req_info else '/' )
        pattern = req_info['pattern']
        servers = self._get_servers( path )

        result = {}
        for server in servers:
            result[ server.get_name() ] = server.find_file( path.get_path_without_node(), pattern )
        return json.dumps( result )

    def shell( self ):
        """
        execute shell script
        """
        req_info = json.load( request.stream )
        nodes = req_info['nodes'] if 'nodes' in req_info else None
        script = req_info['script']
        if nodes is None or len( nodes ) <= 0:
            servers = self.server_mgr.get_servers()
        else:
            servers = [ self.server_mgr.get_server( name ) for name in nodes ]
            servers = [ server for server in servers if server is not None ]
        result = {}
        for server in servers:
            result[ server.get_name() ] = server.shell( script )
        return json.dumps( result )

    def register_server( self ):
        try:
            server_info = json.load( request.stream )
            self.server_mgr.add_node( server_info['name'], server_info['url'], timeout = server_info['timeout'] if 'timeout' in server_info else 60 )
            return "OK"
        except Exception as ex:
            print ex
            return "%s" % ex

    def _get_servers( self, path ):
        """
        get the servers by the path
        """
        if isinstance( path, str ) or isinstance( path, unicode ):
            path = Path( path )

        if path.has_node_name():
            node_name = path.get_node_name()
            if node_name == '*':
                return self.server_mgr.get_servers()
            server = self.server_mgr.get_server( node_name )
            return [] if server is None else [ server ]
        else:
            return self.server_mgr.get_servers()

    def _remove_expired( self ):
        expired_servers = [ name for name in self.servers if self.servers[name].is_expired() ]
        for name in expired_servers:
            del self.servers[ name ]

def parse_args():
    parser = argparse.ArgumentParser( description = "logserver proxy" )
    parser.add_argument( "--host", help = "the listening ip/host, default is 127.0.0.1", default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the listening port number, default is 5000", default = 5000, type = int )
    return parser.parse_args()

def init_logger( log_file  = None):
    if log_file is not None:
        handler = logging.handlers.RotatingFileHandler( log_file, maxBytes=50*1024*1024, backupCount=10)
    else:
        handler = logging.StreamHandler( stream = sys.stdout )

    handler.setLevel( logging.DEBUG )
    handler.setFormatter( logging.Formatter( "%(asctime)s - %(levelname)s - %(message)s" ) )
    logger.setLevel( logging.DEBUG )
    logger.addHandler( handler )

def main():
    args = parse_args()
    init_logger()
    logproxy = LogProxy()
    app = Flask( __name__ )
    app.add_url_rule( "/register", "register", logproxy.register_server, methods = ["POST"])
    app.add_url_rule( "/nodes", "nodes", logproxy.list_nodes, methods=['GET'])
    app.add_url_rule( "/list", "list", logproxy.list_files, methods=['GET'])
    app.add_url_rule( "/download", "download", logproxy.download_file, methods=['GET'] )
    app.add_url_rule( "/grep", "grep", logproxy.grep_file, methods=['POST'] )
    app.add_url_rule( "/find", "find", logproxy.find_file, methods=['POST'] )
    app.add_url_rule( "/shell", "shell", logproxy.shell, methods = ['POST'] )
    app.run( host = args.host, port = args.port, debug = True )


if __name__ == "__main__":
    main()
