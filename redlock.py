#!/usr/bin/python

import redis
import random
import string

UPDATE_LOCK_SCRIPT = """
if redis.call("set",KEYS[1], ARGV[1], "NX", "PX", ARGV[2] ) == "OK" then
    return 1
elseif redis.call("get",KEYS[1]) == ARGV[1] then
    redis.call( "pexpire", KEYS[1], ARGV[2] )
    return 1
else
    return 0
end
"""


UNLOCK_SCRIPT = """
if redis.call( "get", KEYS[1]) == ARGV[1] then
    redis.call("del", KEYS[1] )
    return 1
else
    return 0
end
"""
class UpdateRedLock:
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

    def lock( self):
        """
        get lock on the resource.
        if already get the lock, update its ttl value
        """
        urls = self._get_urls()
        locked_nodes = 0
        for url in urls:
            try:
                if self._from_url( url ).eval( UPDATE_LOCK_SCRIPT, 1, self.resource, self.id, self.ttl ) == 1:
                    locked_nodes += 1
            except:
                pass

        return locked_nodes > len( urls ) / 2

    def unlock( self):
        """
        release the lock on resource
        """
        urls = self._get_urls()
        unlocked_nodes  = 0
        for url in urls:
            try:
                if self._from_url( url ).eval( UNLOCK_SCRIPT, 1, self.resource, self.id) == 1:
                    unlocked_nodes += 1
            except:
                pass
        return unlocked_nodes > len( urls ) / 2

    def _get_urls( self ):
        return [ self.redis_urls ] if type( self.redis_urls ) == str or isinstance( self.redis_urls, redis.RestictRedis) else self.redis_urls
    def _from_url( self, redis_url ):
        return redis.StrictRedis.from_url( redis_url ) if type( redis_url ) == str else redis_url

    def _create_id( self ):
        CHARACTERS = string.ascii_letters + string.digits
        return ''.join(random.choice(CHARACTERS) for _ in range(16)).encode()

