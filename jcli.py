#!/usr/bin/python

import argparse
import socket
import sys
import json
import logging
import logging.handlers
import time

logger = logging.getLogger( __name__ )

class JCli:
    def __init__( self, host, port, user, password ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def connect( self, timeout = 0 ):
        timeoutTime = time.time() + timeout
        while timeout <= 0 or time.time() < timeoutTime:
            try:
                self._connect()
                self._login()
                logger.info( "connect to {}:{} successfully".format( self.host, self.port ) )
                break
            except Exception as ex:
                logger.exception( ex )
                time.sleep( 2 )

    def _login( self ):
        self._expect( "Authentication required." )
        self._send( "" )
        self._expect( "Username:" )
        self._send( self.user )
        self._expect( "Password:" )
        self._send( self.password )
        self._expect( "jcli :" )

    def _connect( self ):
        self.sock = socket.create_connection( ( self.host, self.port ) )

    def add_smpp_connect( self, cid, host, port, user, password, throughput ):
        self.execute_cmd( "smppccm -a" )
        self.execute_cmd( "cid %s" % cid )
        self.execute_cmd( "host %s" % host )
        self.execute_cmd( "port %s" % str( port ) )
        self.execute_cmd( "username %s" % user )
        self.execute_cmd( "password %s" % password )
        self.execute_cmd( "submit_throughput %s" % str( throughput ) )
        self.execute_cmd( "ok" )

    def add_default_mt_router( self, connector ):
        self.execute_cmd( "mtrouter -a" )
        self.execute_cmd( "type DefaultRoute" )
        self.execute_cmd( "connector smppc(%s)" % connector )
        self.execute_cmd( "rate 0.00" )
        self.execute_cmd( "ok" )

    def add_http_connector( self, cid, url, http_method ):
        self.execute_cmd( "httpccm -a" )
        self.execute_cmd( "cid %s" % cid )
        self.execute_cmd( "url %s" % url )
        self.execute_cmd( "method %s" % http_method )
        self.execute_cmd( "ok" )

    def add_default_mo_router( self, connector ):
        self.execute_cmd( "morouter -a" )
        self.execute_cmd( "type DefaultRoute" )
        self.execute_cmd( "connector http(%s)" % connector )
        self.execute_cmd( "ok" )
    def add_group( self, gid):
        self.execute_cmd( "group -a" )
        self.execute_cmd( "gid %s" % gid )
        self.execute_cmd( "ok" )

    def add_user( self, uid, gid, username, password ):
        self.execute_cmd( "user -a" )
        self.execute_cmd( "username %s" % username )
        self.execute_cmd( "password %s" % password )
        self.execute_cmd( "gid %s" % gid )
        self.execute_cmd( "uid %s" % uid )
        self.execute_cmd( "ok" )

    def execute_cmd( self, cmd ):
        logger.info( "%s" % cmd )
        self._send( cmd )
        if cmd == "ok":
            if self._expect( [">", "jcli :"] ) == 0:
                self._send( "ko" )
                self._expect( "jcli :" )
        elif cmd == "ko":
            self._expect( "jcli :" )
        else:
            self._expect( ">" )

    def _send( self, s ):
        logger.info( s )
        self.sock.sendall( "%s\n" % s )

    def _expect( self, expects ):
        if not isinstance( expects, list ):
            expects = [ expects ]
        buf = ""
        while True:
            data = self.sock.recv(1)
            if not data: break
            buf = buf + data
            for i, s in enumerate( expects ):
                if buf.find( s ) != -1:
                    logger.info( buf )
                    return i

def parse_args():
    parser = argparse.ArgumentParser( description = "jasmin client in python" )
    parser.add_argument( "--host", help = "jasmin admin host, default is 127.0.0.1", default = "127.0.0.1" )
    parser.add_argument( "--port", help = "jasmin admin port, default is 8990", default = 8990, type = int )
    parser.add_argument( "--user", help = "jasmin admin user, default is jcliadm", default = "jcliadm" )
    parser.add_argument( "--password", help = "jasmin admin password, default is jclipwd", default = "jclipwd" )
    parser.add_argument( "--batch-file", help = "jasmin batch command in file" )
    parser.add_argument( "--log-file", help = "the log file" )
    return parser.parse_args()

def init_logger( log_file ):
    if log_file is None:
        handler = logging.StreamHandler( stream = sys.stdout )
    else:
        handler = logging.handlers.RotatingFileHandler( log_file, maxBytes = 50 * 1024 * 1024, backupCount= 10 )
    logger.addHandler( handler )
    handler.setLevel( logging.DEBUG )
    handler.setFormatter( logging.Formatter( "%(asctime)-15s %(levelname)s - %(message)s") )
    logger.setLevel( logging.DEBUG )

def load_commands( filename ):
    with open( filename ) as fp:
        commands = []
        for line in fp:
            line = line.strip()
            if line.startswith( '#' ) or len( line ) <= 0: continue
            commands.append( line )
        return commands

def main():
    args = parse_args()
    init_logger( args.log_file )
    logger.info( "start jcli" )
    cli = JCli( args.host, args.port, args.user, args.password )
    cli.connect( 0 )
    if args.batch_file is not None:
        for command in load_commands( args.batch_file ):
            cli.execute_cmd( command )

if __name__ == "__main__":
    main()
