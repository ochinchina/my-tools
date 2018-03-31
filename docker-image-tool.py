#!/usr/bin/python

import argparse
import os
import subprocess
import tempfile


def parse_build_between( build_between_info ):
    """
    parse the build between in format "[start_time-]end_time", the start_time and end_time is in
    format "d+[s|m|M|w|h|d|y]"
    """
    def to_seconds( build_time_info ):
        """
        convert the build time into a seconds

        Args:
            build_time_info - the build time in format "d+[s|m|M|w|h|d|y]", d stands for digital, s - seconds,
            m - minutes, M - months, w - weeks, h - hours, d - days, y - years
        Returns:
            the build time in seconds
        """
        time_units = {'s': 1, 'm': 60, 'M': 31*24*3600, 'h': 3600, 'w':7*24*3600,'d': 24*3600, 'y': 365*24*3600}
        return int(build_time_info) if build_time_info.isdigit() else (int(build_time_info[0:-1]) * time_units[ build_time_info[-1] ] )

    #if no start time
    pos = build_between_info.find( '-' )
    if pos == -1:
        return (-1, to_seconds( build_between_info ) )
    else:
        start_time = to_seconds( build_between_info[0:pos] ) if len( build_between_info[0:pos] )  > 0 else -1
        end_time = to_seconds( build_between_info[pos+1:] ) if len( build_between_info[pos+1:] ) > 0 else -1
        return (start_time, end_time )

def is_build_between( build_time, build_between):
    """
    check if the image is build between
    """
    if build_between[0] <= 0:
        return True if build_between[1] <= 0 else build_time <= build_between[1]
    else:
        if build_time < build_between[0]:
            return False

        return True if build_between[1] <= 0 else build_time <= build_between[1]

def get_images_build_between( build_between_info ):
    """
    get all images build matches build_between_info

    Args:
        build_between_info - the image build between information in format "start-end"
    Returns:
        all the images whose build time matches the build_between_info
    """
    out = subprocess.check_output( ['docker', 'images'] )
    time_units = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 24 * 3600, 'years': 365*24*3600, 'weeks': 7 * 24 * 3600, 'months': 31*24*3600 }
    build_between= parse_build_between( build_between_info )
    result = []
    for lineno, line in enumerate(out.split("\n")):
        if lineno == 0: continue
        words = line.split()
        if len( words ) > 5 and words[3].isdigit() and words[4] in time_units:
            build_time = time_units[ words[4] ] * int( words[3] )
            if is_build_between( build_time, build_between):
                result.append( words[0] + ":" + words[1] )
    return result

def save_images( args ):
    if args.images:
        images = args.images
    elif args.build_between:
        images = get_images_build_between( args.build_between)
    else:
        images = []

    for image in images:
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
    save_parser.add_argument( "--build-between", help = 'the image build between time in format "[start-]end" , the "start" and "end" is in format "d+[s|m|h|d|w|M|y" (s:seonds,m:minutes,h:hours,d:days,M:months,y:years), example: 10m(build less than 10 minutes), 10m-20m(build between 10 minutes to 20 minutes), 10m- (build greater than 10 minutes)', required = False )
    save_parser.add_argument( "--images", nargs='*', help = "the image with version", required = False )
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
