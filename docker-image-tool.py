#!/usr/bin/python

import argparse
import os
import subprocess
import tempfile

def save_images( args ):
    for image in args.images:
        save_image( image, args.dest, args.public )

def save_image( image, dest, public ):
    base_image_name = image.split( '/' )[-1]
    tmp = base_image_name.split(':' )
    if dest.startswith( 's3://'):
        dest_dir = os.path.abspath( tempfile.mkdtemp() )
    else:
        dest_dir = os.path.abspath( dest )
    if not os.path.exists( dest_dir ):
        os.makedirs( dest_dir )

    filename = '%s/%s-%s.tar' % ( dest_dir, tmp[0], tmp[1] if len( tmp ) == 2 else 'latest' )
    print "try to save image %s to file %s" % (image, filename )
    os.system( "docker save -o %s %s" % ( filename, image ) )
    print "compress file %s" % filename
    os.system( "gzip %s" % filename )
    filename = "%s.gz" % filename
    if dest.startswith( 's3://' ):
        command = "s3cmd put %s %s %s" % (filename, "-P" if public else "", dest )
        print command
        os.system( command )
        os.remove( filename )
        os.removedirs( dest_dir )

def load_images( args ):
    for src in args.src:
        load_image( src, args.force )

def list_containers():
    result = []
    out = subprocess.check_output( ['docker', 'ps', '-a'] )
    for index, line in enumerate( out.split( "\n" ) ):
        if index > 0 and len(line) > 0 and not line[0].isspace():
            words = line.split()
            if len( words ) > 3:
                result.append( {'container-id': words[0], 'image-id': words[1], 'status': 'running' if line.find( "Exited" ) == -1 else 'exited'} )
    return result

def find_container_with_image( image ):
    result = []
    image_id = find_image_id( image )
    containers = list_containers()
    for container in containers:
        if container['image-id'] == image_id or container['image-id'] == image:
            result.append( container )
    return result

def list_images():
    result = []
    out = subprocess.check_output( ['docker', 'images'] )
    for index, line in enumerate( out.split("\n" ) ):
        if index != 0:
            words = line.split()
            if len( words ) > 4:
                result.append( {'image': "%s:%s" % (words[0], words[1]), 'image-id': words[3] } )
    return result

def find_image_id( image ):
    images = list_images()
    for image_info in images:
        if image_info['image'] == image:
            return image_info['image-id']
    return None

def remove_image( image ):
    containers = find_container_with_image( image )
    for container in containers:
        if container['status'] == 'exited':
            os.system( 'docker rm %s' % container['container-id'] )
    os.system( 'docker rmi %s' % image )

def load_image( src, force ):
    if src.startswith( 's3://' ):
        dest_dir = os.path.abspath( tempfile.mkdtemp() )
        os.system( "s3cmd get %s %s" % ( src, dest_dir ) )
        src_file = "%s/%s" % (dest_dir, os.path.basename( src ) )
    else:
        src_file = src
    images = list_images() if force else []
    command = ['docker', 'load', '-i', src_file]
    out = subprocess.check_output( command )
    result = parse_image_load_result( out )
    for image_info in images:
        if result['image'] == image_info['image']:
            remove_image( result['image'] )
            os.system( ' '.join( command ) )
            break

    if src.startswith( 's3://' ):
        os.remove( src_file )
        os.removedirs( dest_dir )
        

def parse_image_load_result( result ):
    layers = []
    image = ""
    for line in result.split( "\n" ):
        print line
        pos = line.find( ": Loading layer" )
        if pos != -1:
            layers.append( line[0:pos] )
        else:
            pos = line.find( "Loaded image:")
            if pos != -1:
                image = line[pos+len( "Loaded image:"):].strip()
    return { 'layers': layers, 'image': image }

def parse_args():
    parser = argparse.ArgumentParser( description = "docker tools")
    subparsers = parser.add_subparsers( help = "docker tools" )
    save_parser = subparsers.add_parser( "save", help = "save the image")
    save_parser.add_argument( "-P", "--public", help = "share the image", action = "store_true" )
    save_parser.add_argument( "images", nargs='+', help = "the image with version" )
    save_parser.add_argument( "dest", default = ".", help = "the destination to save the image")
    save_parser.set_defaults( func = save_images )
    load_parser = subparsers.add_parser( "load", help = "load the image")
    load_parser.add_argument( "src", nargs='+', help = "load docker image" )
    load_parser.add_argument( "--force", action="store_true", help="force to load the image")
    load_parser.set_defaults( func = load_images )
    return parser.parse_args()


def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
