#!/usr/bin/python

import json
import urllib2
import sys

def get_tags( image):
    tmp = image.split("/")
    if len( tmp ) == 3:
        f = urllib2.urlopen("https://%s/v2/%s/tags/list" % (tmp[0], "/".join( tmp[1:] ) ) )
    else:
        fetch = False
        try:
            f = urllib2.urlopen("https://registry.hub.docker.com/v1/repositories/%s/tags" % image )
            fetch = True
        except Exception as ex:
            pass
        if not fetch:
            f = urllib2.urlopen("https://%s/v2/%s/tags/list" % (tmp[0], "/".join( tmp[1:] ) ) )
    try:
        jsonData = json.loads( f.read() )
        tags = []
        if type(jsonData) is list:
            for data in jsonData:
                tags.append( data["name"] )
        elif "tags" in jsonData:
            for data in jsonData["tags"]:
                tags.append( data )
        tags = sorted( tags )
        print "\n".join( tags )
    except:
        print "not find %s" % image

if __name__ == "__main__":
    get_tags( sys.argv[1] )
