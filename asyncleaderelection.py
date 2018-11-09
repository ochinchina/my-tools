
import asyncio
import aioredis
import random
import json


LEADER_ELECTION_SCRIPT = """local ret = redis.call("set",KEYS[1], ARGV[1], "NX", "PX", ARGV[2] )
if type( ret ) == "table" and ret["ok"] == "OK" then
    return ARGV[1]
else
    local leader = redis.call("get",KEYS[1])
    if leader == ARGV[1] then
        redis.call( "pexpire", KEYS[1], ARGV[2] )
    end
    return leader
end
"""


LEADER_RELEASE_SCRIPT = """if redis.call( "get", KEYS[1]) == ARGV[1] then
    redis.call("del", KEYS[1] )
    return 1
else
    return 0
end
"""

LEADER_GET_SCRIPT = """return redis.call( "get", KEYS[1])"""

async def create_redis_connections( redis_urls ):
    redises = []
    for url in redis_urls:
        r = await aioredis.create_redis_pool( url )
        redises.append( r )

    return redises

class LeaderElection:
    def __init__( self, redises, resource, ttl = None, id = None ):
        self.redises = redises
        self.resource = resource
        self.ttl = ttl or 10000
        self.id = id or self._create_id()

    def get_id( self ):
        return self.id

    async def elect_leader( self ):
        elections = {}
        for r in self.redises:
            try:
                leader = await r.eval( LEADER_ELECTION_SCRIPT, keys = [self.resource], args = [self.id, self.ttl] )
                if leader is None: continue
                if leader in elections:
                    elections[ leader ] = elections[ leader ] + 1
                else:
                    elections[ leader ] = 1
            except Exception as ex:
                print(ex)

        #find the leader if its vote pass half of redis instances
        leader = self._find_leader( elections )

        if leader is not None: return leader

        raise Exception( "fail to elect a leader")

    async def get_leader( self ):
        """
        get the leader
        """
        elections = {}
        for r in self.redises:
            try:
                leader = await r.evalsha( LEADER_GET_SCRIPT, keys = [self.resource] )
                if leader is None: continue
                if leader in elections:
                    elections[ leader ] += 1
                else:
                    elections[ leader ] = 1
            except Exception as ex:
                print(ex)
        leader = self._find_leader( elections )
        if leader is not None: return leader

        raise Exception( "fail to get leader")


    async def release_leader( self):
        """
        release the leader role on resource if I'm a leader
        """
        release_nodes  = 0
        for r in self.redises:
            try:
                ret = await r.eval( LEADER_SCRIPT, keys=[self.resource], args=[self.id] )
                if ret == 1:
                    release_nodes += 1
            except:
                pass
        return release_nodes > len( self.redises ) / 2

    def _find_leader( self, elections ):
        for leader in elections:
            if elections[leader] > len( self.redises ) / 2:
                return leader.decode("utf-8")
        return None
    def _create_id( self ):
        CHARACTERS = string.ascii_letters + string.digits
        return ''.join(random.choice(CHARACTERS) for _ in range(16)).encode()

async def _do_elect( redis_urls, resource, id, ttl ):
    redises = await create_redis_connections( redis_urls )
    leader_election = LeaderElection( redises, resource, id = id, ttl = ttl )
    leader = await leader_election.elect_leader()
    print( json.dumps( {"leader": leader }) )
    #print( "leader=%s" % leader )


def main():
    import argparse

    parser = argparse.ArgumentParser( description = "elect leader")
    parser.add_argument( "--redis-urls", nargs="+", required = True, help = "redis url in: redis://host:port/db" )
    parser.add_argument( "--resource", required = True, help = "the leader elect on resource" )
    parser.add_argument( "--id", required = False, help = "my identifier or random selected id")
    parser.add_argument( "--ttl", required = False, type = int, help = "the time to live in milliseconds, default is 10000", default = 10000)
    args = parser.parse_args()
    asyncio.get_event_loop().run_until_complete( _do_elect( args.redis_urls, args.resource, args.id, args.ttl ) )

if __name__ == "__main__":
    main()

