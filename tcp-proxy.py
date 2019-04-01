#!/usr/bin/python

import os
import socket
import sys
import thread
import argparse

class TcpProxy:
    def __init__( self, proxy_host, proxy_port, debug ):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.debug = debug
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
            while True:
                data = recv_conn.recv(2048)
                if data:
                    forward_conn.sendall(data )
                    if self.debug: sys.stdout.write( data )
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
    return parser.parse_args()
     
#while True:
#    os.system( "/bin/sh -c \"nc -l 8088 < backpipe | tee -a in | nc 10.144.1.10 8080 | tee -a out.html > backpipe\"")

def parse_ip_address( addr ):
    pos = addr.rfind( ":" )
    return (addr[0:pos], int( addr[pos+1:] ) )

def main():
    args = parse_args()
    proxy_addr = parse_ip_address( args.proxy )
    listen_addr = parse_ip_address( args.listen )
    proxy = TcpProxy( proxy_addr[0], proxy_addr[1], debug = args.debug )
    proxy.create_listener( listen_addr[0], listen_addr[1] )

if __name__== "__main__":
    main()

