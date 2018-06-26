#!/usr/bin/python

import argparse
import json
import os
import threading
import time
import socket
import urllib2
import logging
import logging.handlers
import sys

logging.basicConfig(level=logging.DEBUG)
logger = None

def start_rsync_server( args ):
    """
    start a rsync server

    Args:
        args - the command line arguments and must include parameter "--config" (rsyncd.conf")
    """
    config = "--config %s" % args.config if args.config else ""
    logger.info( "start rsync server with rsyncd.conf:%s" % config )
    os.system( "rsync --daemon --no-detach --bwlimit %d %s" % (args.bwlimit, config ) )

def start_rsync_client( args ):
    """
    start the rsync client

    Args:
        args - the command line arguments, must include "--config" parameter.
        the "--config" parameter points to a configuration file in json format
        for rsync, an example:
            [
              { 
               "srcs": [ "/folder1", "/folder2"],
               "dests": ["/dest1", "/dest2", "/dest3"]
              },
              {
              "srcs": [ "/folder3", "/folder4"],
              "dests": ["/dest4", "/dest5", "/dest6"]
              }
            ]
    """
    config = load_client_config( args.config )

    my_node_id = get_my_node( args )
    old_master_node = my_node_id

    while True:
        try:
            logger.debug( "try to get master node")
            master_node = get_master_node( args.leader_elect_url, args.leader_elect_resource )
            master_changed = old_master_node != master_node
            old_master_node = master_node
            logger.debug( "master node is %s" % master_node )

            if master_changed:
                logger.info( "master node is changed")
                time.sleep( args.sync_interval )
                continue
            #if I'm the master node, don't do the rsync
            if master_node == my_node_id:
                logger.info( "I'm the master node")
                time.sleep( args.sync_interval )
                continue

            #start rsync from the master node
            for item in config:
                if "srcs" in item and "dests" in item:
                    do_rsync( master_node, item["srcs"], item["dests"] )
        except Exception as ex:
            logger.error( "Fail to sync from remote node:%s" % ex )
        except KeyboardInterrupt as ex:
            logger.error( "get KeyboardInterrupt" )
            break
        try:
            logger.debug( "sleep %d" % args.sync_interval )
            time.sleep( args.sync_interval )
        except KeyboardInterrupt as ex:
            break

def do_rsync( master_node, srcs, dests ):
    """
    sync file from master node to this node

    Args:
        master_node - the master node(ip or hostname)
        srcs - folders/files in the master node
        dests - the destination folders in this node
    """
    for dest in dests:
        command = "rsync -r rsync://%s%s %s" % ( master_node, srcs[0] if len( srcs ) == 1 else "{%s}" % ",".join(srcs), dest )
        try:
            print command
            if os.system( command ) == 0:
                print "succeed to do rsync"
        except Exception as ex:
            print ex
            print "fail to execute command:", command

def get_master_node( leader_election_url, resource, my_node_id, ttl ):
    """
    get the master node
    """
    r = urllib2.urlopen( url = "%s/%s" % ( leader_election_url, resource ) )

    if r.getcode() / 100 == 2:
        result = json.loads( r.read() )
        if "leader" in result: return result["leader"]
    raise Exception( "fail to get leader" )

def get_my_node( args ):
    """
    get node identifier of this node
    """
    return args.node_id if args.node_id else socket.gethostname()

def load_client_config( config_file ):
    """
    load the client configuration from json file

    Args:
        config_file - the json based configuration file
    """
    with open( config_file ) as fp:
        return json.load( fp )
    return {}

def parse_args():
    parser = argparse.ArgumentParser( description = "sync files with rsync" )
    subparsers = parser.add_subparsers( help = "sub parsers" )
    server_parser = subparsers.add_parser( "start-server", help = "start rsync server" )
    server_parser.add_argument( "--config", help = "the rsyncd configuration file", required = True )
    server_parser.add_argument( "--bwlimit", help = "bandwidth limit in bytes, default is 4M", required = False, type = int, default = 4194304 )
    server_parser.add_argument( "--log-file", help = "the log file", required = False )
    server_parser.add_argument( "--log-level", help = "the log level", default = "INFO", choices=["CRITICAL","FATAL","ERROR","WARN","INFO","DEBUG"])
    server_parser.set_defaults( func = start_rsync_server )
    client_parser = subparsers.add_parser( "start-client", help = "start the rsync client" )
    client_parser.add_argument( "--config", help = "rsync client config", required = True )
    client_parser.add_argument( "--sync-interval", help = "rsync interval in seconds, default is 300 seconds", required = False, type = int, default = 300 )
    client_parser.add_argument( "--leader-elect-url", help = "leader election url", required = True )
    client_parser.add_argument( "--leader-elect-resource", help = "the leader election resource", required = True )
    client_parser.add_argument( "--node-id", help = "the node id for test only, don't set it in product env", required = False )
    client_parser.add_argument( "--log-file", help = "the log file", required = False )
    client_parser.add_argument( "--log-level", help = "the log level", default = "INFO", choices=["CRITICAL","FATAL","ERROR","WARN","INFO","DEBUG"])
    client_parser.set_defaults( func = start_rsync_client )
    return parser.parse_args()

def init_logger( args ):
    global logger

    logger = logging.getLogger( "start-rsync" )
    logger.propagate = False
    FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    if args.log_file:
        handler = logging.handlers.RotatingFileHandler( args.log_file, maxBytes = 50*1024*1024, backupCount = 10 )
    else:
        handler = logging.StreamHandler( stream = sys.stdout )
    handler.setLevel(logging.getLevelName( args.log_level ) )
    handler.setFormatter( logging.Formatter( FORMAT ) )
    logger.addHandler( handler )

def main():
    args = parse_args()
    init_logger( args )
    args.func( args )
    

if __name__ == "__main__":
    main()
