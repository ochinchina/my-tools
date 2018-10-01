#!/usr/bin/python

import os
import time
import urllib2
import sys

r = urllib2.urlopen( "http://baidu.com" if len( sys.argv ) == 1 else sys.argv[1] )
headers = r.info().dict
if 'date' in headers:
    t = time.strptime( headers['date'], '%a, %d %b %Y %H:%M:%S GMT' )
    os.system( 'date %02d%02d%02d%02d%02d' % ( t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_year ) )

