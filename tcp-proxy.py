#!/usr/bin/python

import os
import socket
import sys
import thread
import argparse
import logging
import logging.handlers
import sys

logger = logging.getLogger( "tcp-proxy" )

def toHex( s ):
    r = []
    for c in s:
        t = hex( ord(c) )
        t = t.replace( '0x', '')
        if len( t ) == 1:
            t = "0%s" % t
        r.append(t)
    return "".join( r )

class Debug:
    def __init__( self, debug, debug_format ):
        self._debug = debug
        self._debug_format = debug_format

    def debug( self, src, dest, text ):
        if not self._debug:
            return

        if self._debug_format == "text":
            logger.debug( "%s -> %s: %s" % (src, dest, text ) )
        else:
            logger.debug( "%s -> %s: %s" % (src, dest, toHex( text ) ) )

class TcpProxy:
    def __init__( self, proxy_host, proxy_port, debug ):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self._debug = debug
    def connect_remote_proxy( self ):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(( self.proxy_host, self.proxy_port))
        return s

    def do_proxy( self, conn ):
        try:
            remote_proxy_conn = self.connect_remote_proxy()
            thread.start_new_thread( self.do_forward, (conn, remote_proxy_conn ) )
            thread.start_new_thread( self.do_forward, (remote_proxy_conn, conn ) )
        except Exception as ex:
            print ex

    def do_forward(self, recv_conn, forward_conn):
        try:
            src = recv_conn.getpeername()
            src = "%s:%s" % ( src[0], src[1] )
            dest = forward_conn.getpeername()
            dest = "%s:%s" % ( dest[0], dest[1] )
            while True:
                data = recv_conn.recv(2048)
                if data:
                    forward_conn.sendall(data )
                    self._debug.debug( src, dest, data )
                else:
                    break
        except:
            pass

    def create_listener( self, addr, port ):
        addrinfo = socket.getaddrinfo( addr, port )
        for item in addrinfo:
            listen_ok = False
            s = socket.socket( item[0], socket.SOCK_STREAM )
            try:
                s.bind((item[4][0], item[4][1]))
                s.listen( 10 )
                listen_ok = True
                while True:
                    conn, remote_addr = s.accept()
                    self.do_proxy( conn )
            except Exception as ex:
                print ex
            try:
                s.close()
            except:
                pass
            if listen_ok: break

def parse_args():
    parser = argparse.ArgumentParser( description = "TCP proxy" )
    parser.add_argument( "--listen", help = "the listen address in IP:PORT format", required = True )
    parser.add_argument( "--proxy", help = "the proxy address in IP:PORT format", required = True )
    parser.add_argument( "--debug", "-d", action = "store_true", help = "in debug mode", required = False )
    parser.add_argument( "--debug-format", help = "the output data format in debug", choices = ["text", "hex"], default = "text" )
    parser.add_argument( "--log-file", help = "the log file", required = False )
    return parser.parse_args()

def parse_ip_address( addr ):
    pos = addr.rfind( ":" )
    return (addr[0:pos], int( addr[pos+1:] ) )

def init_logger( log_file ):
    if log_file is None:
        handler = logging.StreamHandler( sys.stdout )
    else:
        handler = logging.handlers.RotatingFileHandler( log_file, maxBytes = 50 * 1024 * 1024, backupCount = 10 )
    logger.setLevel( logging.DEBUG )
    handler.setFormatter( logging.Formatter( "%(message)s" ) )
    logger.addHandler( handler )
def main():
    args = parse_args()
    init_logger( args.log_file )
    proxy_addr = parse_ip_address( args.proxy )
    listen_addr = parse_ip_address( args.listen )
    debug = Debug( args.debug, args.debug_format )
    proxy = TcpProxy( proxy_addr[0], proxy_addr[1], debug = debug )
    proxy.create_listener( listen_addr[0], listen_addr[1] )

if __name__== "__main__":
    main()
