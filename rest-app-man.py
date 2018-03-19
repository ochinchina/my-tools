#!/usr/bin/python

import argparse
from flask import Flask,request,send_file
import json
import os
import shutil
import subprocess
import sys

"""
"""

class ContentRange:
    def __init__( self, firstBytePos, lastBytePos, totalLength = None ):
        self.firstBytePos = firstBytePos
        self.lastBytePos = lastBytePos
        self.totalLength = totalLength

    @classmethod
    def parse( clss, s ):
        """
        parse the content of 'Content-Range'. The 'Content-Range' is defined in RFC7233
        its format is:

        Content-Range: bytes first-byte-pos-last-byte-pos/completeLength or *
        """
        words = s.split()
        if len( words ) == 2 and words[0] == 'bytes':
            words = words[1].split('/')
            if len( words ) == 2:
                totalLength = int( words[1] ) if words[1].isdigit() else -1
                words = words[0].split('-')
                if len( words ) == 2:
                    return ContentRange( int( words[0] ), int( words[1] ), totalLength )
        else: return None

    def __str__( self ):
        return "%d-%d/%s" % (self.firstBytePos, self.lastBytePos, "*" if self.totalLength < 0 else str( self.totalLength ) )

class Application:
    def __init__(self, app_conf ):
        """
        configuration example for application:

        {
            "command": "/bin/sleep",
            "args": [ "60" ],
            "auto-start": true,
            "env": {
                "env-var-1": "value1",
                "env-var-2", "value2"
            },
            "conf-root": "/root",
            "stop-command": "/bin/pkill",
            "stop-args": ["sleep"]
        }

        only the command parameter is mandatory and all other parameters
        are optional
        """
        command = app_conf['command']
        args = app_conf['args'] if 'args' in app_conf else None
        self.args = [ command ] + args if args is not None else []
        self.env = app_conf['env'] if 'env' in app_conf else os.environ
        self.auto_start = app_conf['auto-start'] if 'auto-start' in app_conf else False
        self.conf_root = os.path.abspath( app_config['conf-root'] ) if 'conf-root' in app_conf else os.path.abspath( '.' )
        self.stop_command = app_conf['stop-command'] if 'stop-command' in app_conf else None
        if self.stop_command and 'stop-args' in app_conf:
            self.stop_command.extend( app_conf['stop-args'] )
        self.process = None

    def start( self ):
        # if the process is already started, return
        if self.process and self.process.poll() == None:
            return False

        #start the process if it is not started
        self.process = subprocess.Popen( self.args, env = self.env, stdout = sys.stdout, stderr = sys.stderr )
        return self.is_running()

    def status( self ):
        """
        get the application status
        """
        if self.is_running():
            return "running"
        else: return "stopped"

    def is_running( self ):
        """
        check if the process is running or not
        """
        return self.process and self.process.poll() == None

    def stop( self ):
        """
        stop the running application
        """
        if self.is_running():
            # send stop command
            if self.stop_command:
                subprocess.check_output( self.stop_command )
            else:
                self.process.kill()
            # wait for exit
            self.process.wait()
        return not self.is_running()

    def restart( self ):
        """
        restart the application
        """
        if self.is_running():
            self.stop()
            self.process.wait()
        return self.start()

    def is_autostart( self ):
        """
        if the application is auto started application
        """
        return self.auto_start

    def upload_conf( self, conf_file_path, contentobj, contentRange ):
        """
        upload a configure file
        """
        file_path = os.path.join( self.conf_root, conf_file_path )
        # create dir if not exist
        if not os.path.exists( os.path.dirname( file_path ) ):
            os.makedirs( os.path.dirname( file_path ) )

        if contentRange.firstBytePos == 0:
            mode = "wb"
        else: mode = "rb+"
        with open( file_path, mode ) as fp:
            if contentRange:
                fp.seek( contentRange.firstBytePos )
            shutil.copyfileobj( request.stream, fp )
            return True
        return False
    
    def delete_conf( self, conf_file_path ):
        """
        delete a configure file or directory
        """
        file_path = os.path.join( self.conf_root, conf_file_path )
        # delete it if the file exists
        if os.path.exists( file_path ):
            shutil.rmtree( file_path )
            return True
        return False

    def get_full_conf_file_path( self, conf_file_path ):
        return os.path.join( self.conf_root, conf_file_path )

    def list_conf( self ):
        """
        list all the configuration file
        """
        result = []
        os.path.walk( self.conf_root, lambda arg, dirname, names: result.extend( [ os.path.join( dirname, name ) for name in names if os.path.isfile( os.path.join( dirname, name ) ) ] ), None )
        return [ file_path[len( self.conf_root ):] for file_path in result ]

class AppMan:
    def __init__( self, app_configs ):
        self.apps = {}
        for name, conf in app_configs.iteritems():
            self.apps[name ] = Application( conf )
        self.start_autostart_app()

    def start_autostart_app( self ):
        for name, app in self.apps.iteritems():
            if app.is_autostart():
                print "start application %s" % name
                app.start()

    def get_apps( self ):
        return self.apps

    def start_app( self, name ):
        """
        start app with name
        """
        app = self.apps[name] if name in self.apps else None
        if app is not None:
            if app.is_running():
                return "%s is running already" % name
            elif app.start():
                return  "succeed to start application %s" % name
            else: return "fail to start application %s" % name
        else:
            return "no such application %s" % name

    def list_app( self):
        """
        list all the applications
        """
        return json.dumps( [ name for name in self.apps ] )

    def app_status( self, name ):
        """
        get the status of application
        """
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name
        return json.dumps( {'name': name, 'status': app.status() })
    def restart_app( self, name ):
        """
        restart a application
        """
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name

        if app.restart():
            return  "succeed to restart application %s" % name
        else: return "fail to restart application %s" % name

    def stop_app( self, name ):
        """
        stop app with name
        """
        app = self.apps[name] if name in self.apps else None
        if app is not None:
            if app.is_running():
                if app.stop():
                    return "succeed to stop application %s" % name
                else: return "fail to stop application %s" % name
            else: return "application %s is not started" % name
        else:
            return "no such application %s" % name

    def upload_conf( self, name, path ):
        """
        upload the configuration file

        Args:
            name - the application name
            path - the file to save
        """
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name

        contentRange = ContentRange.parse( request.headers['Content-Range'] ) if 'Content-Range' in request.headers else None
            
        if app.upload_conf(path, request.stream, contentRange ):
            return "succeed to save config file %s" % path
        else: return "fail to save config file %s" % path

    def delete_conf( self, name, path ):
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name

        if app.delete_conf( path ):
            return "succeed to delete config file %s" % path
        else: return "fail to delete config file %s" % path

    def download_conf( self, name, path ):
        """
        download the application configuration file
        """
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name, 404

        # get full path of configure file
        full_path = app.get_full_conf_file_path( path )
        if os.path.exists( full_path ) and os.path.isfile( full_path ):
            return send_file( full_path, mimetype = "application/octetstream" )
        else: return "no such file", 404

    def list_conf( self, name ):
        app = self.apps[name] if name in self.apps else None
        if app is None:
            return "no such application %s" % name, 404

        return json.dumps( app.list_conf() )


def load_args():
    parser = argparse.ArgumentParser( description = "Application Manager with Restful interface" )
    parser.add_argument( "--conf-file", help = "application configuration file", required = True )
    parser.add_argument( "--log-file", help = "the log file", required = False )
    parser.add_argument( "--host", help = "the host/ip address to listen", required = False, default="127.0.0.1" )
    parser.add_argument( "--port", help = "the listening port", required = False, default = "5000" )
    parser.add_argument( "--log-level", help = "the log level: CRITICAL,ERROR,WARNING,INFO,DEBUG", required = False, default="DEBUG" )
    return parser.parse_args()

def load_config_file( conf_file ):
    with open( conf_file ) as fp:
        return json.load( fp )
    return {}

def init_logger( args ):
    if args.log_file:
        import logging
        logging.basicConfig(filename=args.log_file,level=logging.DEBUG)

def main():
    args = load_args()
    init_logger( args ) 
    app_man =  AppMan( load_config_file( args.conf_file ) )
    app = Flask(__name__)
    app.add_url_rule( "/list/app", "list_app", app_man.list_app, methods = ['GET'] )
    app.add_url_rule( "/status/app/<name>", "app_status", app_man.app_status, methods = ['GET'] )
    app.add_url_rule( "/start/app/<name>", "start_app", app_man.start_app, methods=['PUT', 'POST'])
    app.add_url_rule( "/stop/app/<name>", "stop_app", app_man.stop_app, methods=['PUT', 'POST'])
    app.add_url_rule( "/restart/app/<name>", "restart_app", app_man.restart_app, methods=["PUT", "POST"] )
    app.add_url_rule( "/upload/conf/<name>/<path:path>", "upload_conf", app_man.upload_conf, methods=["POST"])
    app.add_url_rule( "/delete/conf/<name>/<path:path>", "delete_conf", app_man.delete_conf, methods=["PUT", "POST"] )
    app.add_url_rule( "/download/conf/<name>/<path:path>", "download_conf", app_man.download_conf, methods = ['GET'] )
    app.add_url_rule( "/list/conf/<name>", "list_conf", app_man.list_conf, methods = ['GET'] )
    app.run( host = args.host, port = int(args.port) )

if __name__ == "__main__":
    main()

