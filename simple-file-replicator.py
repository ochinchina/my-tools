#!/usr/bin/env python

import argparse
import flask
import json
import logging
import logging.handlers
import mmap
import os
import re
import shutil
import subprocess
import threading
import time
import urllib2
from Queue import Queue
from flask import request, Response

logger = logging.getLogger( __name__ )
logHandler = None

def split_path( path ):
    result = []
    while True:
        head, tail = os.path.split( path )
        if len( tail ) <= 0: break
        result.append( tail )
        path = head
    return list( reversed( result ) )

class ModuleFiles:
    """
    manage all the files in one module
    """
    def __init__( self, module_name, path, include_patterns, exclude_patterns, update_interval ):
        self.module_name = module_name
        self.path = os.path.abspath( path )
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.update_interval = 300 if update_interval is None else update_interval
        self.next_update_time = 0
        self.files = {}
        self._lock = threading.Lock()

    def update_files( self ):
        """
        update the files
        """
        if self.next_update_time > time.time():
            with self._lock:
                return self.files

        self.next_update_time += self.update_interval

        tmpFiles = []
        os.path.walk( self.path, lambda arg, dirname, names: tmpFiles.extend( [ os.path.join( dirname, name ) for name in names if self._match_file_item( name ) ] ), None )
        allFiles = {}
        for f in tmpFiles:
            if os.path.isfile( f ):
                name = os.path.join( "/", self.module_name, f[ len( self.path ) + 1:] )
                size = os.path.getsize( f )
                allFiles[ name ] = size

        with self._lock:
            self.files = allFiles
            return self.files

    def file_added( self, name ):
        """
        a file is added
        """
        filename = self.get_abspath( name )
        if os.path.exists( filename ):
            size = os.path.getsize( filename )
            with self._lock:
                self.files[ name ] = size

    def file_removed( self, name ):
        with self._lock:
            del self.files[ name ]

    def exists( self, name ):
        """
        check if a file exists or not
        """
        with self._lock:
            return name in self.files

    def get_module_name( self ):
        return self.module_name

    def get_abspath( self, name ):
        """
        get the download file path
        """
        prefix = os.path.join( "/", self.module_name )
        if name.startswith( prefix ):
            return os.path.join( self.path, name[len( prefix ) + 1:] )
        return None


    def _match_pattern( self, name, pattern ):
        """
        check if the file basename matches the pattern or not
        """
        return re.match( pattern, name ) is not None

    def _match_file_item( self, name ):
        # check if the name matches any one of 'include-patterns'
        if self.include_patterns is not None and len( self.include_patterns ) > 0:
            matches = False
            for pattern in self.include_patterns:
                if self._match_pattern( name, pattern ):
                    matches = True
                    break
            if not matches: return False

        # check if the name matches any one of 'exclude-patterns'
        if self.exclude_patterns is not None and len( self.exclude_patterns ) > 0:
            for pattern in self.exclude_patterns:
                if self._match_pattern( name, pattern ):
                    return False
        return True

class AsyncPush:
    def __init__( self ):
        self.push_requests = Queue()
        th = threading.Thread( target = self._start_push_thread )
        th.setDaemon( True )
        th.start()

    def add_request( self, push_request ):
        self.push_requests.put( push_request )

    def _start_push_thread( self ):
        while True:
            push_request = self.push_requests.get()
            logger.info( "push file %s to url=%s" % ( push_request['filename'], push_request['url'] ) )
            try:
                if os.path.getsize( push_request['filename'] ) <= 0:
                    urllib2.urlopen( push_request['url'], data = "", timeout = 20 )
                else:
                    with open( push_request['filename'] ) as fp:
                        mmapped_file_as_string = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
                        urllib2.urlopen( push_request['url'], mmapped_file_as_string, timeout = 20 )
            except Exception as ex:
                logger.error( "fail to push file %s with error:%s" % (push_request['filename'], ex ) )

class MasterChecker:
    def __init__( self, master_check_script, check_interval = 10 ):
        self.master_check_script = master_check_script
        self.check_interval = check_interval
        self._locking = threading.Lock()

        if self.master_check_script is None or len( self.master_check_script ) <= 0:
            self.is_master_node = True
        else:
            self.is_master_node = False
            th = threading.Thread( target = self._start_check_master )
            th.setDaemon( True )
            th.start()


    def is_master( self ):
        """
        check if the local node is the master node

        Return:
            True if local node is the master node, False if the local node is not the master node
        """
        with self._locking:
            return self.is_master_node

    def _start_check_master( self ):
        while True:
            ret = self._check_master()
            with self._locking:
                self.is_master_node = ret
            time.sleep( self.check_interval )

    def _check_master( self ):
        try:
            return os.system( self.master_check_script ) == 0
        except Exception as ex:
            logger.error( "fail to check the master with script %s, error:%s" % (self.master_check_script, ex ) )

        return False

class ReplicateServer:
    def __init__( self, master_checker, fileConfig ):
        self.master_checker = master_checker
        self.module_files = {}
        for item in fileConfig:
            self.module_files[ item['name'] ] = ModuleFiles( item['name'],
                    item['dir'],
                    item['include-patterns'] if 'include-patterns' in item else None,
                    item['exclude-patterns'] if 'exclude-patterns' in item else None,
                    int( item['update-interval'] ) if 'update-interval' in item else 300 )

        self.files = {}
        self._lock = threading.Lock()
        self.master_checker = master_checker
        self.async_push = AsyncPush()
        self._retrieve_files()
        th = threading.Thread( target = self._start_file_retrieve )
        th.setDaemon( True )
        th.start()

    def get_files( self ):
        """
        get all the files
        """
        if not self.master_checker.is_master():
            return "Service Unavailable", 503
        if 'module' in request.args:
            module_name = request.args['module']
            if module_name not in self.files:
                return "No such module %s" % module_name, 404
            with self._lock:
                return Response( json.dumps( self.files[module_name] ), status = 200, mimetype='application/json' )

        with self._lock:
            all_files = {}
            for module_name in self.files: all_files.update( self.files[module_name] )
            return Response( json.dumps( all_files ), status = 200,  mimetype='application/json' )

    def download_file( self):
        """
        download a file
        """
        if not self.master_checker.is_master():
            return "Service Unavailable", 503

        if 'file' not in request.args:
            return "Missing file parameter", 404
        name = request.args['file']
        filename = self._get_download_file_abspath( name )
        if filename is None or not os.path.exists( filename ):
            return "Not found", 404
        return flask.send_file( filename )

    def async_push_file( self ):
        """
        push the files to the client specified URL.
        """
        if not self.master_checker.is_master():
            return "Service Unavailable", 503

        file_download_request = json.loads( request.data )
        url = file_download_request['url']
        filename = file_download_request['file']
        self.async_push.add_request( {"filename":self._get_download_file_abspath( filename ), "url": '%s?file=%s' % ( url, filename ) } )

        return "schedule for push"


    def _get_download_file_abspath( self, name ):
        for module_name in self.module_files:
            path = self.module_files[ module_name ].get_abspath( name )
            if path is not None:
                return path
        return None


    def _start_file_retrieve( self ):
        while True:
            self._retrieve_files()
            time.sleep( 10 )

    def _retrieve_files( self ):
        """
        start to retrieve the files according to the configuration
        """
        files = {}
        for module_name in self.module_files:
            files[ module_name ] = self.module_files[ module_name ].update_files()

        with self._lock:
            self.files = files

def load_server_file_config( filename ):
    """
    load the file configuration in following .json format

    [
      {
        "name": "the module name",
        "dir": "the file directory",
        "recursive": true,
        "include-patterns": [ ".+\.txt"],
        "exclude-patterns": [ ".+\.tmp"]
        "update-interval": 300
      },
      {
        "name": "the module name",
        "dir": "the file directory",
        "recursive": true,
        "include-patterns": [ ".+\.txt"],
        "exclude-patterns": [ ".+\.tmp"],
        "update-interval": 300
      }
    ]
    """
    with open( filename ) as fp:
        return json.load( fp )

def run_server( args ):
    master_checker = MasterChecker( args.master_checker, args.master_check_interval )
    replicate_server = ReplicateServer(  master_checker, load_server_file_config( args.file_config ) )
    app = flask.Flask( __name__ )
    app.add_url_rule( "/list", "list", replicate_server.get_files, methods=['GET'])
    app.add_url_rule( "/download", "download", replicate_server.download_file, methods = ['GET'] )
    app.add_url_rule( "/async_push", "async_push", replicate_server.async_push_file, methods = ['POST'] )
    app.logger.addHandler( logHandler )
    app.run( host = args.host, port = int(args.port), debug = True )

def load_push_config( filename ):
    """
    load the push configuration in following .json format:

    [
      { "name": "the module name",
        "dir": "the file directory",
        "update-interval": 300
      },
      { "name": "the module name",
        "dir": "the file directory",
        "update-interval": 300
      }
    ]
    """
    with open( filename ) as fp:
        return json.load( fp )


class PushServer:
    def __init__( self, push_host, push_port, push_config, notifier ):
        self.push_host = push_host
        self.push_port = push_port
        self.push_config = push_config
        self.notifier = notifier

    def start( self ):
        app = flask.Flask( __name__ )
        app.add_url_rule( "/save", "save", self._save_file, methods=['POST'])
        app.logger.addHandler( logHandler )
        app.run( host = self.push_host, port = self.push_port )

    def _save_file( self ):
        if 'file' not in request.args:
            return "Missing file parameter", 404

        filename = request.args[ 'file' ]
        filename = self._get_save_file( filename )

        if filename is None:
            return "Fail to save file %s" % request.args['file'], 404

        dirname = os.path.dirname( filename )
        if not os.path.exists( dirname ):
            os.makedirs( dirname )

        with open( filename, "wb" ) as fp:
            shutil.copyfileobj( request.stream, fp )

        logger.info( "succeed to save module file %s to real file %s" % ( request.args[ 'file' ], filename ) )

        if self.notifier is not None: self.notifier( request.args['file'] )

        return "succeed to save file"

    def _get_save_file( self, filename ):
        elements = split_path( filename )
        if len( elements ) > 0:
            for item in self.push_config:
                if elements[0] == item['name']:
                    return os.path.join( item['dir'], *elements[1:] )
        return None

class ReplicateServerDiscover:
    def __init__( self, host = None, host_script = None ):
        self.host = host
        self.host_script = host_script

    def get_server( self ):
        """
        get the server name

        Return:
            the ip/host name of server if succeed to find, None if fail to find
        """
        return self.host if self.host is not None else self._get_server_by_script()

    def _get_server_by_script( self ):
        """
        get the server by the script

        Return: server name/ip if succeed to find otherwise return None
        """
        try:
            output = subprocess.check_output( [ self.host_script ] ).strip()
            return output if len( output ) > 0 else None
        except Exception as ex:
            logger.error( "fail to run the script %s to find server with error:%s" % ( self.host_script, ex ) )
        return None


class ReplicateClient:
    def __init__( self, replicate_server_discover, server_port, push_host, push_port, push_config ):
        self.replicate_server_discover = replicate_server_discover
        self.server_port = server_port
        self.push_host = push_host
        self.push_port = push_port
        self.push_config = push_config
        self.module_files = {}
        for item in push_config:
            update_interval = 300 if 'update-interval' not in item else int( item['update-interval'] )
            name = item['name']
            self.module_files[ name ] = ModuleFiles( name, item['dir'], None, None, update_interval )

        self._start_push_server()

    def start_replicate( self ):
        while True:
            for module_name in self.module_files:
                sleep_seconds = 60 if self._replicate_module( module_name ) <= 0 else 10
                time.sleep( sleep_seconds )

    def _replicate_module( self, module_name ):
        server = self.replicate_server_discover.get_server()

        if server is None or len( server ) <= 0: return 0

        remote_files = self._download_module_files( server, module_name )
        # don't do anything is fail to download the remote module files
        if remote_files is not None:
            local_files = self.module_files[module_name].update_files()
            new_files = [ f for f in remote_files if f not in local_files or remote_files[f] != local_files[f] ]
            deleted_files = [ f for f in local_files if f not in remote_files ]

            self._delete_local_files( deleted_files )
            self._download_files( server, new_files )
            return len( new_files ) + len( deleted_files )
        else:
            return 0

    def _delete_local_files( self, files ):
        """
        delete the local saved files
        """
        for f in files:
            try:
                filename = self._get_real_filename( f )
                if os.path.exists( filename ):
                    logger.info( "remove local file %s" % filename )
                    os.remove( filename )
                    try:
                        os.rmdir( os.path.dirname( filename ) )
                    except Exception as e:
                        pass
            except Exception as ex:
                logger.error( "fail to remove file %s:%s" % (f, ex ))
    def _download_files( self, server, files ):
        """
        download the remote files to local
        """
        for f in files:
            pushed_file = { "url": "http://%s:%d/save" % ( self.push_host, self.push_port ), "file": f }
            try:
                logger.info( "request to push file %s from remote %s:%d to %s:%d" % ( f, server, self.server_port, self.push_host, self.push_port ) )
                req = urllib2.Request( "http://%s:%s/async_push" % ( server, self.server_port ), data = json.dumps( pushed_file ), headers = {"Content-Type": "application/json"})
                resp = urllib2.urlopen( req )
                if resp.getcode() / 100 in (2,3):
                    self._wait_file_downloaded( f, 300 )
            except Exception as ex:
                log.error( "fail to download file %s:%s" % (f, ex) )
    def _touch_file( self, filename ):
        """
        touch a file
        """
        dirname = os.path.dirname( filename )
        if not os.path.exists( dirname ):
            os.makedirs( dirname )
        with open( filename, "a" ):
            pass

    def _wait_file_downloaded( self, name, timeout ):
        """
        wait the file download
        """
        module_name = self._get_module_name( name )
        timeout_time = time.time() + timeout
        while timeout_time > time.time():
            if self.module_files[ module_name ].exists( name ):
                break
            time.sleep( 2 )

    def _get_real_filename( self, filename ):
        """
        get the real filename
        """
        elements = split_path( filename )
        if len( elements ) > 0:
            for item in self.push_config:
                if elements[0] == item['name']:
                    return os.path.join( item['dir'], *elements[1:] )
        return None

    def _download_module_files( self, server, module_name ):
        """
        downlolad all files in one module
        """
        try:
            resp = urllib2.urlopen( "http://%s:%d/list?module=%s" % ( server, self.server_port, module_name ) )
            if resp.getcode() / 100 in (2,3):
                data = resp.read()
                return json.loads( data )
        except Exception as ex:
            logger.error( "fail to download files included in module %s:%s" % (module_name, ex ) )
        return None

    def _start_push_server( self ):
        push_server = PushServer( self.push_host, self.push_port, self.push_config, self._file_pushed )
        th = threading.Thread( target = push_server.start )
        th.setDaemon( True )
        th.start()

    def _get_module_name( self, name ):
        """
        get the module name
        """
        return split_path( name )[0]

    def _file_pushed( self, name ):
        """
        a file is pushed to local system
        """
        module_name = self._get_module_name( name )
        if module_name in self.module_files:
            module_file = self.module_files[ module_name ]
            module_file.file_added( name )


def run_client( args ):
    """
    load as client
    """
    push_config = load_push_config( args.push_config )
    replicate_server_discover = ReplicateServerDiscover( args.host, args.host_script )
    repliate_client = ReplicateClient( replicate_server_discover, args.port, args.push_host, args.push_port, push_config )
    repliate_client.start_replicate()

def parse_args():
    parser = argparse.ArgumentParser( description = "replicate files between the nodes" )
    subparsers = parser.add_subparsers( help = "sub-commands" )

    server_parser = subparsers.add_parser( "server", help = "run as a server" )
    server_parser.add_argument( "--host", help = "the host/ip address to listen, default is 0.0.0.0", default = "0.0.0.0", required = False )
    server_parser.add_argument( "--port", help = "the listening port number, default is 5000", default = 5000, type = int, required = False )
    server_parser.add_argument( "--master-checker", help = "script to check if I'm the master node", required = False )
    server_parser.add_argument( "--master-check-interval", help = "the master check interval if parameter --master-checker is set", type = int, required = False, default = 10 )
    server_parser.add_argument( "--file-config", help = "the file configuration in .json format", required = True )
    server_parser.add_argument( "--log-file", help = "the log filename", required = False )

    server_parser.set_defaults( func = run_server )

    client_parser = subparsers.add_parser( "client", help = "run as a client" )
    client_parser.add_argument( "--host", help = "the server host name or ip address", required = False )
    client_parser.add_argument( "--host-script", help = "get the server name or ip address from host", required = False )
    client_parser.add_argument( "--port", help = "the server listening port number, default is 5000", default = 5000, required = False, type = int )
    client_parser.add_argument( "--push-host", help = "async push host name or ip address, default is 0.0.0.0", required = False, default = "0.0.0.0" )
    client_parser.add_argument( "--push-port", help = "async push port number, default is 5000", required = False, type = int, default = 5000 )
    client_parser.add_argument( "--push-config", help = "the push configuration in .json format", required = True )
    client_parser.add_argument( "--log-file", help = "the log filename", required = False )
    client_parser.set_defaults( func = run_client )

    return parser.parse_args()

def init_logger( log_file ):
    global logHandler
    logger.setLevel( logging.DEBUG )
    if log_file is None:
        logHandler = logging.StreamHandler()
    else:
        logHandler = logging.handlers.RotatingFileHandler( log_file, maxBytes = 50*1024*1024, backupCount = 10 )
    logHandler.setLevel( logging.DEBUG )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logHandler.setFormatter( formatter )
    logger.addHandler( logHandler )

def main():
    args = parse_args()
    init_logger( args.log_file )
    args.func( args )


if __name__ == "__main__":
    main()

