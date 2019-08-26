#!/usr/bin/python

import argparse
import subprocess
import json
import re

def list_all_ips():
    """
    list all the ip addresses in the node

    Return:
        the ip addresses in map
    """
    out = subprocess.check_output( ['ip', 'a'] )
    result = {}
    for line in out.split( "\n" ):
        pos = line.find( ':' )
        if pos != -1 and line[0:pos].isdigit():
            words = line.split()
            dev_name = words[1][0:-1]
            result[dev_name] = {}
        else:
            words = line.split()
            if len(words) > 2 and words[0] == 'inet':
                ipv4 = words[1]
                if 'ipv4' not in result[dev_name]:
                    result[dev_name]['ipv4'] = []
                    result[dev_name]['ipv4'].append( ipv4 )
            elif len(words) > 2 and words[0] == 'inet6':
                ipv6 = words[1]
                if 'ipv6' not in result[dev_name]:
                    result[dev_name]['ipv6'] = []
                    result[dev_name]['ipv6'].append( ipv6 )
    return result

def print_all_ips( args ):
    print json.dumps( list_all_ips(), indent = 4 )

def extract_ip_addr( all_ips ):
    cidr_ips = [ ip for dev in all_ips for ip_type in all_ips[dev] for ip in all_ips[dev][ip_type] ]
    return [ ip.split('/')[0].strip() for ip in cidr_ips ]

def get_ip_addr( args ):
    all_ips = list_all_ips()
    # filter ip by the device name
    cur_ips = {}
    if args.dev:
        pattern = re.compile( args.dev )
        for ip_dev in all_ips:
            if pattern.match( ip_dev ):
                cur_ips[ ip_dev ] = all_ips[ip_dev]
    else:
        cur_ips = all_ips

    # filter the ip by the ip type
    all_ips = cur_ips
    cur_ips = {}
    if args.ip_type:
        for ip_dev in all_ips:
            if args.ip_type in all_ips[ip_dev]:
                if ip_dev not in cur_ips:
                    cur_ips[ip_dev] = {}
                cur_ips[ip_dev][args.ip_type] = all_ips[ip_dev][args.ip_type]
    else:
        cur_ips = all_ips

    ip_addrs = extract_ip_addr( cur_ips )
    if len( ip_addrs ) > 1 and args.all:
        print json.dumps( ip_addrs )
    elif len( ip_addrs ) > 0:
        print ip_addrs[0]

def parse_args():
    parser = argparse.ArgumentParser( description = "linux ip tools" )
    subparsers = parser.add_subparsers( help = "linux ip tools" )

    list_ip_parser = subparsers.add_parser( "list", help = "list all the ip address" )
    list_ip_parser.set_defaults( func = print_all_ips )

    get_ip_by_dev_parser = subparsers.add_parser( "get", help = "get ip addess" )
    get_ip_by_dev_parser.add_argument( "--dev", help = "device pattern", required = False )
    get_ip_by_dev_parser.add_argument( "--cidr", help = "cidr or ip address", required = False )
    get_ip_by_dev_parser.add_argument( "--ip-type", help = "ip type", choices = ['ipv4', 'ipv6'], required = False )
    get_ip_by_dev_parser.add_argument( "--all", help = "all the ip address in json array", action = "store_true", required = False )
    get_ip_by_dev_parser.set_defaults( func = get_ip_addr )

    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )


if __name__ == "__main__":
    main()


