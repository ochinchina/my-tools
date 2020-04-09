#!/usr/bin/python

import argparse
import json
import os

"""
[
  {
    "name": "project-1",
    "host": "10.68.120.190",
    "nodes": {
        "node-00": "10.68.120.190",
        "node-01": "10.68.120.191",
        "node-02": "10.68.120.192",
        "node-03": "10.68.120.193",
        "node-04": "10.68.120.194",
    },
   "ssh-key": "/root/project-1.pem",
    "ssh-user": "god",
    "command": "sudo -i"
  },
  {
    "name": "project-2",
    "host": "10.68.110.80",
    "nodes": {
        "node-00": "10.68.110.80",
        "node-01": "10.68.110.81",
        "node-02": "10.68.110.82"
    },
    "ssh-user": "root",
    "ssh-passwd": "password"
  }
]
"""

def green_color( text ):
    return '\033[0;32m%s\033[0m' % text

def cyan_color( text ):
    return '\033[0;36m%s\033[0m' % text

def parse_args():
    parser = argparse.ArgumentParser( description = "NLS test environment" )
    parser.add_argument( "--config", help = "test env configuration file, default is ~/.nls-test-env.json", default = "~/.nls-test-env.json" )
    subparsers = parser.add_subparsers( help = "commands" )
    list_parser = subparsers.add_parser( "list", help = "list environments" )
    list_parser.add_argument( "--with-node", action = "store_true", help = "list nodes" )
    list_parser.set_defaults( func = list_envs )
    ssh_parser = subparsers.add_parser( "ssh", help = "ssh into the test env" )
    ssh_parser.add_argument( "env", help = "the environemt" )
    ssh_parser.set_defaults( func = ssh_env )
    scp_parser = subparsers.add_parser( "scp", help = "scp files to/from test env" )
    scp_parser.add_argument( "src", help = "source files" )
    scp_parser.add_argument( "dest", help = "destination files" )
    scp_parser.set_defaults( func = scp_env )
    return parser.parse_args()

def load_config( filename ):
    """
    """
    filename = os.path.expanduser( filename )
    with open( filename ) as fp:
        return json.load( fp )

def list_envs( args ):
    for env in load_config( args.config ):
        if args.with_node:
           print green_color( env['name'] )
           if 'nodes' in env:
               for node in env['nodes']:
                   print cyan_color( "    %s" % node )
        else:
            print green_color( env['name'] )


def find_node( config, name ):
    """
    find the node ip address

    Return: a tuple: node name, ssh-key, ssh-user, command to execute after ssh
    """
    for env in config:
        if env['name'] == name:
            return env['host'] if 'host' in env else None, env['ssh-key'] if 'ssh-key' in env else None, env['ssh-passwd'] if 'ssh-passwd' in env else None, env['ssh-user'], env['command'] if 'command' in env else None
        if name.startswith( env['name'] ) and "nodes" in env:
            for node in env['nodes']:
                possible_names = ( "%s.%s" % ( env['name'], node ), "%s-%s" % ( env['name'], node ), "%s_%s" % ( env['name'], node ) )
                if name in possible_names:
                    return env['nodes'][node], env['ssh-key'] if 'ssh-key' in env else None, env['ssh-passwd'] if 'ssh-passwd' in env else None, env['ssh-user'], env['command'] if 'command' in env else None
    return None, None, None, None, None

def ssh_env( args ):
    node, ssh_key, ssh_passwd, ssh_user, command = find_node( load_config( args.config ), args.env )
    if node is None:
        print "Fail to find %s" % args.env
    elif command is not None:
        if ssh_key is not None:
            os.system( 'ssh -o StrictHostKeyChecking=no -i %s -t %s@%s "%s"' % ( ssh_key, ssh_user, node, command ) )
        elif ssh_passwd is not None:
            print 'sshpass -p %s ssh -o StrictHostKeyChecking=no %s@%s "%s"' % (ssh_passwd, ssh_user, node, command )
            os.system( 'sshpass -p %s ssh -o StrictHostKeyChecking=no %s@%s "%s"' % (ssh_passwd, ssh_user, node, command ) )
    else:
        if ssh_key is not None:
            os.system( "ssh -i %s -o StrictHostKeyChecking=no %s@%s" % ( ssh_key, ssh_user, node ) )
        elif ssh_passwd is not None:
            print 'sshpass -p %s ssh -o StrictHostKeyChecking=no %s@%s' % (ssh_passwd, ssh_user, node)
            os.system( 'sshpass -p %s ssh -o StrictHostKeyChecking=no %s@%s' % (ssh_passwd, ssh_user, node) )

def find_scp_info( args, addr ):
    """
    return a tuple ( node, ssh-key, ssh-user, path )
    or the addr itself
    """
    pos_1 = addr.find( '@' )
    pos_2 = addr.find( ':' )
    config = load_config( args.config )
    if pos_1 != -1 and pos_2 != -1 and pos_2 > pos_1:
        dest_addr = addr[ pos_1 + 1: pos_2 ]
        node, ssh_key, ssh_passwd, ssh_user, command = find_node( config, dest_addr )
        return node, ssh_key, ssh_user, addr[pos_2+1:]
    else:
        return addr

def is_ip_v6( addr ):
    return addr.find( ':' ) != -1

def scp_env( args ):
    src_scp_info = find_scp_info( args, args.src )
    dest_scp_info = find_scp_info( args, args.dest )
    if isinstance( src_scp_info, tuple ) and isinstance( dest_scp_info, str ):
        node, ssh_key, ssh_user, path = src_scp_info
        node = "[%s]"% node if is_ip_v6( node ) else node
        command = "scp -i %s %s@%s:%s %s" % ( ssh_key, ssh_user, node, path, dest_scp_info )
        print command
        os.system( command )
    elif isinstance( src_scp_info, str ) and isinstance( dest_scp_info, tuple ):
        node, ssh_key, ssh_user, path = dest_scp_info
        node = "[%s]"% node if is_ip_v6( node ) else node
        command = "scp -i %s %s %s@%s:%s" % ( ssh_key, src_scp_info,  ssh_user, node, path )
        print command
        os.system( command )

def main():
    args = parse_args()
    args.func( args )


if __name__ == "__main__":
    main()
