#!/usr/bin/python

import sys

if sys.argv[1] == 's3cmd' and sys.argv[2] == 'put' and sys.argv[-1].startswith( 's3://'):
    files = []
    s3dir = sys.argv[-1]

    #remove last /
    if s3dir.endswith( '/' ): s3dir = s3dir[0:-1]

    for f in sys.argv[3:-1]:
        if not f.startswith( '-' ): files.append( "%s/%s" % (s3dir, f ) )

    print "s3cmd get -f %s ." % " ".join( files )
else:
    print "not a s3cmd put command"
    
    
