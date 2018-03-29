#!/usr/bin/python

import argparse
import subprocess

def generate_token():
    """
    generate the token for "kubeadm join"
    """
    output = subprocess.check_output( ["kubeadm", "token", "generate"] )
    return output.strip()

def print_kubeadm_join( ttl ):
    """
    print a kubeadm join command with ttl(in seconds)
    """
    command = ["kubeadm", "token", "create", generate_token(), "--print-join-command" ]
    if ttl is not None:
        command.append( "--ttl" )
        if type(ttl) == str and not ttl.isdigit():
            command.append( ttl )
        elif int(ttl) == 0:
            command.append( "0" )
        else:
            command.append( "%ss" % ttl )
    output = subprocess.check_output( command )
    return output.strip()

def parse_args():
    parser = argparse.ArgumentParser( description = "print the kubeadm join command from master node" )
    parser.add_argument( "--ttl", help = "the time to live for the join command", required = False, default = "10" )
    return parser.parse_args()

def main():
    args = parse_args()
    print print_kubeadm_join( args.ttl )

if __name__ == "__main__":
    main()
