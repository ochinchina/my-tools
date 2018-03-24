#!/usr/bin/python

import sys
import os

def download_go_package( package ):
    words = package.split( "/" )
    if len( words ) > 2 and words[0] == "golang.org" and words[1] == "x":
        package_dir_name = "%s/src/%s" % (os.environ['GOPATH'], "/".join( words[0:2] ) )
        if not os.path.exists( package_dir_name ):
            os.makedirs( package_dir_name )
        os.chdir( package_dir_name )
        os.system( "git clone https://github.com/golang/%s" %  words[2] )


for package in sys.argv[1:]:
    download_go_package( package )
