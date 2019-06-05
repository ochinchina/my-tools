#!/usr/bin/python
import sys
import time
import logging
import etcd3
import flask
import threading
import json

app = flask.Flask( __name__ )
leader_election = None

class LeaseRefresh:
    def __init__( self ):
        self._lock = threading.Lock()
        self._resource_leases = {}
        

    def add_lease( self, resource, lease ):
        with self._lock:
            self._resource_leases[ resource ] = lease

    def refresh( self, resource ):
        with self._lock:
            self._refresh( resource )

    def _refresh( self, resource ):
        if resource in self._resource_leases:
            lease = self._resource_leases[ resource ]
            try:
                lease.refresh()
            except Exception as ex:
                del self._resource_leases[ resource ]
                lease.revoke()
                

class LeaderElection:

    def __init__( self, etcd_client, key_prefix = None ):
        self._client = etcd_client
        self._key_prefix = key_prefix
        self._lease = None
        self._lease_refresh = LeaseRefresh()

    def elect_leader( self, resource, my_id, ttl ):
        """
        elect a leader.

        Return: the elected leader
        """
        try:
            status, lease, leader = self._elect_leader( resource, my_id, ttl )
            if status:
                self._lease_refresh.add_lease( resource, lease )
            elif leader == my_id:
                self._lease_refresh.refresh( resource )
            return leader
        except Exception as ex:
            print ex
        return None

    def get_leader( self, resource ):
        try:
            leader_key = resource if self._key_prefix is None else "%s/%s" % ( self._key_prefix, resource )
            value = self._client.get( leader_key )
            return value[0]
        except Exception as ex:
            print ex
        return None
    def _elect_leader( self, resource, my_id, ttl ):
        try:
            lease = self._client.lease( ttl )
            leader_key = resource if self._key_prefix is None else "%s/%s" % ( self._key_prefix, resource )
            status, responses = self._client.transaction(
                compare = [ self._client.transactions.version( leader_key ) == 0 ],
                success = [ self._client.transactions.put( leader_key, my_id, lease ) ],
                failure = [ self._client.transactions.get( leader_key ) ]
            ) 
            if status:
                return status, lease, my_id
            elif len( responses ) == 1 and len( responses[0] ) == 1:
                return status, lease, responses[0][0][0]
        except Exception as ex:
            print ex
        return None, None, None


@app.route( "/leader/elect/<resource>/<node>/<int:ttl>" )
def elect_leader( resource, node, ttl ):
    try:
        leader = leader_election.elect_leader( resource, node, ttl )
        return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        print ex
    return json.dumps( {"error": "fail to elect leader" } ), 501

@app.route( "/leader/get/<resource>")
def get_leader( resource ):
    try:
        leader = leader_election.get_leader( resource)
        if leader is not None: return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        print ex
    return json.dumps( {"error": "fail to elect leader" } ), 501

 
def main():
    import argparse
    parser = argparse.ArgumentParser( description = "elect leader from etcd cluster" )
    parser.add_argument( "--etcd-host", help = "the etcd host, default = 127.0.0.1", required = False, default = "127.0.0.1" )
    parser.add_argument( "--etcd-port", help = "the etcd port, default = 2379", required = False, default = 2379, type = int )
    parser.add_argument( "--ca-cert", help = "the etcd ca-cert", required = False )
    parser.add_argument( "--cert-key", help = "the etcd cert key", required = False )
    parser.add_argument( "--cert-cert", help = "the etcd cert", required = False )
    parser.add_argument( "--timeout", help = "the timeout in seconds for etcd operation", default = 2, type = int )
    parser.add_argument( "--port", help = "the port number to listen, default is 5000", default = 5000, type = int )
    args = parser.parse_args()

    params = { "host": args.etcd_host, "port": args.etcd_port, "timeout": args.timeout }
    if args.ca_cert: params[ "ca_cert" ] = args.ca_cert
    if args.cert_key: params[ "cert_key" ] = args.cert_key
    if args.cert_cert: params[ "cert_cert" ] = args.cert_cert

    client = etcd3.client( **params )

    global leader_election

    leader_election = LeaderElection( client )
    app.run( port = args.port, host = "0.0.0.0" )

if __name__ == '__main__':
    main()

