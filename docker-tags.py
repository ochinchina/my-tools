#!/usr/bin/python

import json
import urllib2
import sys

def get_tags( image):
    tmp = image.split("/")
    if len( tmp ) == 3:
        f = urllib2.urlopen("https://%s/v2/%s/tags/list" % (tmp[0], tmp[1] + "/" + tmp[2] ) )
    else:
        f = urllib2.urlopen("https://registry.hub.docker.com/v1/repositories/%s/tags" % image )
    try:
        jsonData = json.loads( f.read() )
        if type(jsonData) is list:
            for data in jsonData:
                print data["name"]
        elif "tags" in jsonData:
            for data in jsonData["tags"]:
                print data
    except:
        print "not find %s" % image

if __name__ == "__main__":
    get_tags( sys.argv[1] )
