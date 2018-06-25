#!/usr/bin/python

from flask import Flask
import argparse
import leaderelection
import json

app = Flask( __name__ )

redis_urls = None

@app.route("/leader/elect/<resource>/<node>/<int:ttl>")
def elect_leader( resource, node, ttl ):
    """
    elect the leader on resource with the node and ttl information

    Args:
        resource - leader election on this resource
        node - the node id
        ttl - the time to live in milliseconds
    """
    leader_election = create_leader_election( redis_urls, resource, node, ttl )
    try:
        leader = leader_election.elect_leader()
        return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        print ex
        return json.dumps( {"error": "fail to elect leader" } ), 501

@app.route( "/leader/get/<resource>")
def get_leader( resource ):
    """
    get the leader
    """
    leader_election = create_leader_election( redis_urls, resource, "ignore", 10 )
    try:
        leader = leader_election.get_leader()
        return json.dumps( {"leader": leader} ), 200
    except Exception as ex:
        print ex
        return json.dumps( {"error": "fail to get leader" } ), 501

def create_leader_election( redis_urls, resource, node, ttl ):
    """
    create a redis leader election object
    """
    return leaderelection.LeaderElection( redis_urls, resource, id = node, ttl = ttl )

def parse_args():
    parser = argparse.ArgumentParser( description = "leader election restful interface" )
    parser.add_argument( "--redis-urls", nargs="+", help = "redis url in format: redis://host:port/db", required = True )
    parser.add_argument( "--bind-addr", help = "the bind address, default is 127.0.0.1", required = False, default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the listening port, default is 5000", required = False, default = 5000, type = int )
    return parser.parse_args()

def main():
    args = parse_args()
    global redis_urls
    redis_urls = args.redis_urls
    app.run( host = args.bind_addr, port = args.port )

if __name__ == "__main__":
    main()
