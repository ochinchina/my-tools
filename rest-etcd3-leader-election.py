#!/usr/bin/python
import argparse
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
import etcd3
import flask
import threading
import json
import traceback

app = flask.Flask( __name__ )
leader_election = None
logger = logging.getLogger( "leader-election" )

class LeaderCache:
    def __init__( self, ttl ):
        self._lock = threading.Lock()
        self._ttl = ttl
        self._leaders = {}

    def add_leader( self, resource, leader ):
        with self._lock:
            self._leaders[ resource ] = { "leader": leader, "timeout": time.time() + self._ttl }

    def remove_leader( self, resource ):
        with self._lock:
            if resource in self._leaders: del self._leaders[ resource ]

    def get_leader( self, resource ):
        with self._lock:
            self._remove_timeout_items()
            return self._leaders[ resource ]["leader"] if resource in self._leaders else None

    def _remove_timeout_items( self ):
        timeout_items = [ resource for resource in self._leaders if self._leaders[ resource ][ "timeout"] < time.time() ]
        for resource in timeout_items:
            del self._leaders[ resource ]

class LeaseRefresh:
    def __init__( self ):
        self._lock = threading.Lock()
        self._resource_leases = {}


    def add_lease( self, resource, leader, lease ):
        """
        add the lease

        :param resource: the resource
        :type resource: string
        :param leader: the leader of resource
        :type leader: string
        :param lease: the lease
        :type lease: class:etcd3.Lease
        :returns: True if
        :rtype: bool
        """
        key = self._get_key( resource, leader )
        with self._lock:
            if key in self._resource_leases and self._resource_leases[key].id == lease.id:
                return False

            self._resource_leases[ key ] = lease
            return True

    def refresh( self, resource, leader ):
        """
        refresh the lease

        :rtype: bool
        """
        with self._lock:
            key = self._get_key( resource, leader )
            lease = self._resource_leases[ key ] if key in self._resource_leases else None
        return lease is not None and self._refresh( resource, leader, lease )

    def _refresh( self, resource, leader, lease ):
        try:
            resp = lease.refresh()
            if len( resp ) == 1 and resp[0].TTL > 0:
                logger.info( "%s refresh lease of %s successfully" % ( leader, resource ) )
                return True
            logger.error( "fail to refresh the lease of %s because of expiration" % resource )
        except Exception as ex:
            logger.error( "fail to refresh the lease of %s with error:%s" % (resource, traceback.format_exc() ) )
        del self._resource_leases[ self._get_key( resource, leader ) ]
        return False

    def _revoke_lease( self, lease, resource ):
        try:
            lease.revoke()
            lease.etcd_client.close()
            logger.info( "success to revoke lease of %s" % resource )
        except Exception as ex:
            logger.error( "fail to revoke lease of %s with error:%s" % (resource, traceback.format_exc() ) )

    def _get_key( self, resource, leader ):
        return "%s@%s" % (leader, resource )

class ClientManager:
    def __init__( self, connect_params ):
        self._connect_params = connect_params

    def get_client( self ):
        return etcd3.client( **self._connect_params )

    def release( self, client ):
        try:
            client.close()
        except Exception as ex:
            logger.error( "fail to close connect to etcd with error:%s" % ex )

class LeaderElection:

    def __init__( self, client_mgr, key_prefix = None ):
        self._client_mgr = client_mgr
        self._key_prefix = key_prefix
        self._lease_refresh = LeaseRefresh()
        self._leader_cache = LeaderCache( 1 )

    def elect_leader( self, resource, my_id, ttl ):
        """
        elect a leader.

        Return: the elected leader
        """
        try:
            if self._lease_refresh.refresh( resource, my_id ):
                return my_id
            logger.debug( "start to elect leader of %s with id %s and ttl %d" % (resource, my_id, ttl) )
            status, lease, leader = self._elect_leader( resource, my_id, ttl )
            logger.debug( "the leader of %s is %s" % ( resource, leader ) )
            if status:
                self._lease_refresh.add_lease( resource, leader, lease )
                logger.info( "%s becomes leader of %s" % ( leader, resource ) )
            elif lease is not None:
                if self._lease_refresh.add_lease( resource, leader, lease ):
                    if leader == my_id: self._lease_refresh.refresh( resource, my_id )
                else:
                    self._client_mgr.release( lease.etcd_client )
            # cache the leader
            if leader is None:
                self._leader_cache.remove_leader( resource )
            else:
                self._leader_cache.add_leader( resource, leader )

            return leader
        except Exception as ex:
            logger.error( "fail to elect leader of %s with error:%s" % ( resource, traceback.format_exc() ) )
        return None

    def get_leader( self, resource ):
        leader = self._leader_cache.get_leader( resource )
        if leader is not None: return leader

        client = self._client_mgr.get_client()
        try:
            leader_key = resource if self._key_prefix is None else "%s/%s" % ( self._key_prefix, resource )
            value = client.get( leader_key )
            leader = value[0]
            if leader is None:
                logger.debug( "no leader of %s is found" % resource )
            else:
                self._leader_cache.add_leader( resource, leader )
                logger.debug( "get leader %s of %s successfully" % (leader, resource) )
        except Exception as ex:
            logger.error( "fail to get the leader of %s with error:%s" % ( resource, traceback.format_exc() ) )
        self._client_mgr.release( client )
        return leader

    def _elect_leader( self, resource, my_id, ttl ):
        client = self._client_mgr.get_client()
        try:
            lease = client.lease( ttl )
            leader_key = resource if self._key_prefix is None else "%s/%s" % ( self._key_prefix, resource )
            status, responses = client.transaction(
                compare = [ client.transactions.version( leader_key ) == 0 ],
                success = [ client.transactions.put( leader_key, my_id, lease ) ],
                failure = [ client.transactions.get( leader_key ) ]
            )
            if status:
                return status, lease, my_id
            elif len( responses ) == 1 and len( responses[0] ) == 1:
                return status, etcd3.Lease(responses[0][0][1].lease_id, ttl, client), responses[0][0][0]
        except Exception as ex:
            logger.error( "fail to elect leader of %s with error:%s" % ( resource, traceback.format_exc() ) )
        self._client_mgr.release( client )
        return None, None, None


@app.route( "/leader/elect/<resource>/<node>/<int:ttl>" )
def elect_leader( resource, node, ttl ):
    try:
        leader = leader_election.elect_leader( resource, node, ttl / 1000 )
        if leader is not None:
            return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        logger.error( "fail to elect leader with error:%s" % ex )
    return json.dumps( {"error": "fail to elect leader" } ), 501

@app.route( "/leader/get/<resource>")
def get_leader( resource ):
    try:
        leader = leader_election.get_leader( resource)
        if leader is not None: return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        logger.error( "fail to get leader with error:%s" % ex )
    return json.dumps( {"error": "fail to elect leader" } ), 501

@app.route("/heartbeat")
def heartbeat():
    return "OK"

def init_logger( log_file ):
    if log_file is None:
        handler = logging.StreamHandler( sys.stdout )
    else:
        handler = RotatingFileHandler( log_file, maxBytes = 50*1024*1024, backupCount = 10 )
    handler.setFormatter( logging.Formatter( '%(asctime)s - %(name)s - %(levelname)s - %(thread)d - %(message)s' ) )
    logger.setLevel( logging.DEBUG )
    logger.addHandler( handler )

def parse_args():
    parser = argparse.ArgumentParser( description = "elect leader from etcd cluster" )
    parser.add_argument( "--etcd-host", help = "the etcd host, default = 127.0.0.1", required = False, default = "127.0.0.1" )
    parser.add_argument( "--etcd-port", help = "the etcd port, default = 2379", required = False, default = 2379, type = int )
    parser.add_argument( "--ca-cert", help = "the etcd ca-cert", required = False )
    parser.add_argument( "--cert-key", help = "the etcd cert key", required = False )
    parser.add_argument( "--cert-cert", help = "the etcd cert", required = False )
    parser.add_argument( "--timeout", help = "the timeout in seconds for etcd operation, default is 10 seconds", default = 10, type = int )
    parser.add_argument( "--port", help = "the port number to listen, default is 5000", default = 5000, type = int )
    parser.add_argument( "--log-file", help = "the log file" )
    return parser.parse_args()

def build_app( etcd_host, etcd_port, timeout, log_file, ca_cert = None, cert_key = None, cert_cert = None ):
    init_logger( log_file )
    params = { "host": etcd_host, "port": etcd_port, "timeout": timeout }
    if ca_cert: params[ "ca_cert" ] = ca_cert
    if cert_key: params[ "cert_key" ] = cert_key
    if cert_cert: params[ "cert_cert" ] = cert_cert

    client_mgr = ClientManager( params )

    global leader_election

    leader_election = LeaderElection( client_mgr, key_prefix = "/leader-election" )
    return app

def main():
    args = parse_args()
    app = build_app( args.etcd_host,
                     args.etcd_port,
                     args.timeout,
                     args.log_file,
                     ca_cert = args.ca_cert,
                     cert_key = args.cert_key,
                     cert_cert = args.cert_cert )

    app.run( port = args.port, host = "0.0.0.0" )

if __name__ == '__main__':
    main()
