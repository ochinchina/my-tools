import argparse
import asyncleaderelection
import aiohttp
from aiohttp import web
redises = None

routes = web.RouteTableDef()


@routes.get("/heartbeat")
async def heart_beat( request ):
    return web.Response( body = "OK" )

@routes.get("/leader/elect/{resource}/{node}/{ttl}")
async def elect_leader( request ):
    """
    elect the leader on resource with the node and ttl information

    Args:
        resource - leader election on this resource
        node - the node id
        ttl - the time to live in milliseconds
    """
    resource = request.match_info['resource']
    node = request.match_info['node']
    ttl = int( request.match_info['ttl'] )
    leader_election = await create_leader_election( redises, resource, node, ttl )
    try:
        leader = await leader_election.elect_leader()
        return web.json_response( {"leader": leader} , status = 200 )
    except Exception as ex:
        print(ex)
        return web.json_response( {"error": "fail to elect leader" }, status = 501 )

@routes.get( "/leader/get/{resource}")
async def get_leader( request ):
    """
    get the leader
    """
    resource = request.match_info['resource']
    leader_election = await create_leader_election( redises, resource, "ignore", 10 )
    try:
        leader = await leader_election.get_leader()
        return web.json_response( {"leader": leader} )
    except Exception as ex:
        print(ex)
        return web.json_response( {"error": "fail to get leader" }, status = 501 )

async def create_leader_election( redises, resource, node, ttl ):
    """
    create a redis leader election object
    """
    return asyncleaderelection.LeaderElection( redises, resource, id = node, ttl = ttl )

def parse_args():
    parser = argparse.ArgumentParser( description = "leader election restful interface" )
    parser.add_argument( "--redis-urls", nargs="+", help = "redis url in format: redis://host:port/db", required = True )
    parser.add_argument( "--bind-addr", help = "the bind address, default is 127.0.0.1", required = False, default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the listening port, default is 5000", required = False, default = 5000, type = int )
    return parser.parse_args()

async def main( args ):
    global redises
    redises = await asyncleaderelection.create_redis_connections( args.redis_urls )
    app = web.Application()
    app.add_routes( routes )
    return app

    
if __name__ == "__main__":
    args = parse_args()
    web.run_app( main( args ), host = args.bind_addr, port = args.port )

