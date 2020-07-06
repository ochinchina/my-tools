#!/usr/bin/python

import socket
import argparse

def parse_args():
    parser = argparse.ArgumentParser( description = "send udp message to server" )
    parser.add_argument( "--host", help = "the udp server ip or host name", required = True )
    parser.add_argument( "--port", help = "the udp server listening port", required = True, type = int )
    parser.add_argument( "--data", help = "the data send to server" )
    parser.add_argument( "--data-file", help = "the data file sent to server" )
    return parser.parse_args()

def read_data( args ):
    if args.data is not None:
        return args.data
    if args.data_file is None:
        return None
    with open( args.data_file ) as fp:
        return fp.read()

def main():
    args = parse_args()
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    data = read_data( args )
    sock.sendto( data, ( args.host, args.port ) )

if __name__ == "__main__":
    main()
