#!/usr/bin/python

import argparse
import os
import tempfile

def save_image( args ):
    image = args.image.split( '/' )[-1]
    tmp = image.split(':' )
    if args.dest.startswith( 's3://'):
        dest_dir = os.path.abspath( tempfile.mkdtemp() )
    else:
        dest_dir = os.path.abspath( args.dest )
    if not os.path.exists( dest_dir ):
        os.makedirs( dest_dir )

    filename = '%s/%s-%s.tar' % ( dest_dir, tmp[0], tmp[1] if len( tmp ) == 2 else 'latest' )
    print "try to save image %s to file %s" % (args.image, filename )
    os.system( "docker save -o %s %s" % ( filename, args.image ) )
    print "compress file %s" % filename
    os.system( "gzip %s" % filename )
    filename = "%s.gz" % filename
    if args.dest.startswith( 's3://' ):
        command = "s3cmd put %s %s" % (filename, args.dest )
        print command
        os.system( command )
        os.remove( filename )
        os.removedirs( dest_dir )

def load_image( args ):
    if args.src.startswith( 's3://' ):
        dest_dir = os.path.abspath( tempfile.mkdtemp() )
        os.system( "s3cmd get %s %s" % (args.src, dest_dir ) )
        src_file = "%s/%s" % (dest_dir, os.path.basename( args.src ) )
    else:
        src_file = args.src
    os.system( "docker load -i %s" % src_file )

    if args.src.startswith( 's3://' ):
        os.remove( src_file )
        os.removedirs( dest_dir )
        
def parse_args():
    parser = argparse.ArgumentParser( description = "docker tools")
    subparsers = parser.add_subparsers( help = "docker tools" )
    save_parser = subparsers.add_parser( "save", help = "save the image")
    save_parser.add_argument( "image", help = "the image with version" )
    save_parser.add_argument( "dest", default = ".", help = "the destination to save the image")
    save_parser.set_defaults( func = save_image )
    load_parser = subparsers.add_parser( "load", help = "load the image")
    load_parser.add_argument( "src", help = "load docker image" )
    load_parser.set_defaults( func = load_image )
    return parser.parse_args()


def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
