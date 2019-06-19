#!/usr/bin/python

import argparse
import os
import sys

def upload_file( node_name, user, ssh_key, local_file, remote_file ):
    os.system( "scp -i %s -q %s %s@%s:%s" % ( ssh_key, local_file, user, node_name, remote_file ) )

def load_docker_image( node_name, user, ssh_key, local_file ):
    remote_file = "/tmp/%s" % os.path.basename( local_file )
    upload_file( node_name, user, ssh_key, local_file, remote_file )
    os.system( "ssh -i %s -q %s@%s sudo -i docker load -i %s" % ( ssh_key, user, node_name, remote_file ) )
    os.system( "ssh -i %s -q %s@%s sudo -i rm -rf %s" % ( ssh_key, user, node_name, remote_file ) )

def get_image_save_file( image_name ):
    pos = image_name.rfind( "/" )
    if pos != -1:
        image_name = image_name[pos+1:]
    pos = image_name.find( ":" )
    filename = "%s-latest.tar" if pos == -1 else "%s-%s.tar" % ( image_name[0:pos], image_name[ pos + 1:] )
    return filename

def save_image( image_name ):
    filename = get_image_save_file( image_name )
    if os.system( "docker save %s -o %s" % ( image_name, filename ) )  == 0:
        os.system( "gzip %s" % filename )
        return "%s.gz" % filename

    return None

def get_image_file( args ):
    if args.image_file is not None:
        return args.image_file

    images = []
    if args.image is not None:
        for image_name in args.image:
            filename = save_image( image_name )
            if filename is not None:
                images.append( filename )
    return images

def parse_args():
    parser = argparse.ArgumentParser( description = "load the docker image to remote node" )
    parser.add_argument( "--user", help = "the user to login to remote node", required = True )
    parser.add_argument( "--ssh-key", help = "the ssh key to login to remote node", required = True )
    parser.add_argument( "--node", help = "the remote ip / hostname", required = True, nargs = "+" )
    parser.add_argument( "--image-file", help = "the docker image file", required = False, nargs = "+" )
    parser.add_argument( "--image", help = "the docker image", required = False, nargs = "+" )
    return parser.parse_args()
def main():
    args = parse_args()
    images = get_image_file( args )

    for image in images:
        for node in args.node:
            load_docker_image( node, args.user, args.ssh_key, image )

if __name__ == "__main__":
    main()
