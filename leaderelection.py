#!/usr/bin/python

import redis
import random
import string

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


LEADER_RELEASE_SCRIPT = """
if redis.call( "get", KEYS[1]) == ARGV[1] then
    redis.call("del", KEYS[1] )
    return 1
else
    return 0
end
"""
class LeaderElection:
    def __init__( self, redis_urls, resource, ttl = None, id = None ):
        """
        create a UpdateRedLock object with parameters

        Args:
            redis_urls - the redis url in format: redis://host:port/db
            ttl - time to live in milliseconds, default is 10000 milliseconds
        """
        self.redis_urls = redis_urls
        self.resource = resource
        self.ttl = ttl or 10000
        self.id = id or self._create_id()

    def get_id( self ):
        """
        get my identifier
        """
        return self.id
    def elect_leader( self ):
        """
        elect a leader on resource.
        return the leader identifier
        """
        urls = self._get_urls()
        elections = {}
        for url in urls:
            try:
                leader = self._from_url( url ).eval( LEADER_ELECTION_SCRIPT, 1, self.resource, self.id, self.ttl )
                if leader in elections:
                    elections[ leader ] += 1
                else:
                    elections[ leader ] = 1
            except:
                pass

        #find the leader if its vote pass half of redis instances
        for leader in elections:
            if elections[leader] > len( urls ) / 2:
                return leader

        raise Exception( "fail to get a leader")

    def release_leader( self):
        """
        release the leader role on resource if I'm a leader
        """
        urls = self._get_urls()
        release_nodes  = 0
        for url in urls:
            try:
                if self._from_url( url ).eval( LEADER_SCRIPT, 1, self.resource, self.id) == 1:
                    release_nodes += 1
            except:
                pass
        return release_nodes > len( urls ) / 2

    def _get_urls( self ):
        return [ self.redis_urls ] if type( self.redis_urls ) == str or isinstance( self.redis_urls, redis.StrictRedis) else self.redis_urls
    def _from_url( self, redis_url ):
        return redis.StrictRedis.from_url( redis_url ) if type( redis_url ) == str else redis_url

    def _create_id( self ):
        CHARACTERS = string.ascii_letters + string.digits
        return ''.join(random.choice(CHARACTERS) for _ in range(16)).encode()


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser( description = "elect leader")
    parser.add_argument( "--redis-urls", nargs="+", required = True, help = "redis url in: redis://host:port/db" )
    parser.add_argument( "--resource", required = True, help = "the leader elect on resource" )
    parser.add_argument( "--id", required = False, help = "my identifier or random selected id")
    parser.add_argument( "--ttl", required = False, type = int, help = "the time to live in milliseconds, default is 10000", default = 10000)
    args = parser.parse_args()
    leader_election = LeaderElection( args.redis_urls, args.resource, id = args.id, ttl = args.ttl )
    leader = leader_election.elect_leader()
    print json.dumps( {"leader": leader})

if __name__ == "__main__":
    main()
