#!/usr/bin/python

import redis
import sys
import json

def get_string_size( redis_client, key ):
    return redis_client.strlen( key )

def get_list_size( redis_client, key ):
    return redis_client.llen( key )

def get_set_size( redis_client, key ):
    return redis_client.scard( key )

def get_zset_size( redis_client, key ):
    size = 0
    for v in redis_client.zrange( key, 0, -1 ):
        size += len( v )
    return size

def get_hash_size( redis_client, key ):
    return redis_client.hlen( key )

def get_size( redis_client, key ):
    t = redis_client.type( key )
    func_map = { "string": get_string_size,
                 "list": get_list_size,
                 "set": get_set_size,
                 "zset": get_zset_size,
                 "hash": get_hash_size }
    func = func_map[t] if t in func_map else None
    ttl = redis_client.ttl( key )
    if func is None:
        print "missing function to get size of %s" % t
        return t, ttl, -1
    else:
        return t, ttl, func( redis_client, key )

def dump_string( redis_client, key ):
    return json.dumps( { "key": key, "value": redis_client.get( key ) } )

def dump_zet( redis_client, key ):
    values_with_score = redis_client.zrange( key, 0, -1, withscores = True )
    values_with_score = map( lambda x: {"value": x[0], "score": x[1]}, values_with_score )
    return json.dumps( { "key": key, "zset": values_with_score } )

def dump_key( redis_client, key ):
    t = redis_client.type( key )
    func_map = { "string": dump_string,
                 "zset": dump_zet }
    func = func_map[t] if t in func_map else None
    return func( redis_client, key )

def redis_size_summary( r ):
    cursor = 0
    typed_keys_size = {}
    total_size = 0
    total_keys = 0
    biggest_ttl = -1
    while True:
        cursor, keys = r.scan( cursor )
        total_keys += len( keys )
        for key in keys:
            t, ttl, size = get_size( r, key )
            size += len( key )
            if biggest_ttl == -1 or biggest_ttl < ttl:
                biggest_ttl = ttl

            if t not in typed_keys_size: typed_keys_size[t] = {}
            typed_keys_size[t][key] = size
            if size > 0: total_size += size

        if cursor == 0 : break

    for t in typed_keys_size:
        keys_size = typed_keys_size[t]
        keys_size = sorted( keys_size.items(), key=lambda x: x[1], reverse = True )
        print_count = 100
        for item in keys_size:
            print "%s %s %d" % ( t, item[0], item[1] )
            print_count -= 1
            if print_count == 0: break

    print "total size:%d" % total_size
    print "total keys:%d" % total_keys
    print "biggest ttl:%d" % biggest_ttl

def dump_redis( r ):
    cursor = 0
    loops = 100000
    while True:
        cursor, keys = r.scan( cursor )
        for key in keys:
            print dump_key( r, key )
        loops -= 1
        if cursor == 0 or loops == 0: break

r = redis.Redis( host = sys.argv[1], port = int( sys.argv[2] ), db = 0 )

dump_redis( r )
