#!/usr/bin/env python

import argparse
import subprocess
import os
import sys
import tempfile

"""
sync s3 files between to sides
"""
def list_s3_path( s3cfg, path ):
    command = ['s3cmd', '-c', s3cfg, 'ls' ]
    if path is not None: command.append( path )
    out = subprocess.check_output( command )
    result = []
    for line in out.split('\n'):
        fields = line.split()
        if len( fields ) <= 0: continue
        filename = fields[-1]
        if len( fields ) < 4:
            result.extend( list_s3_path( s3cfg, filename ) )
        else:
            result.append( filename )
    return result

def s3_basename( filename ):
    return os.path.basename( filename[len('s3://'):] ) if filename.startswith( 's3://' ) else ""

def s3_dirname( filename ):
    filename = os.path.dirname( filename[len('s3://'):] ) if filename.startswith( 's3://' ) else ""
    return "s3://%s" % filename if len( filename ) > 0 else ""

def s3_path_join( dirname, basename ):
    return "%s%s" % ( dirname, basename ) if dirname.endswith( '/' ) else "%s/%s" % ( dirname, basename )

def get_s3_bucket( filename ):
    """
    extract s3 bucket from filename
    """
    if filename.startswith( 's3://' ):
        pos = filename.find( '/', len( 's3://' ) )
        return filename if pos == -1 else filename[0:pos]
    else:
        return ""

def mk_s3_bucket( s3cfg, bucket ):
    try:
        subprocess.check_output( [ "s3cmd", "-c", s3cfg, "mb", bucket ] )
        return True
    except Exception as ex:
        print(ex)
        return False

def s3_bucket_exist( s3cfg, bucket ):
    """
    check if s3 bucket exists or not
    """
    try:
        subprocess.check_output( [ "s3cmd", "-c", s3cfg, "ls", bucket ] )
        return True
    except Exception as ex:
        print(ex)
        return False

def get_dest_s3file( src_dir, src_file, dest_file ):
    if src_file.startswith( src_dir ):
        if src_dir == src_file:
            return s3_path_join( dest_file , s3_basename( src_file ) ) if dest_file.endswith( '/' ) else dest_file
        if not src_dir.endswith( '/' ) and src_file[len(src_dir)] != '/':
            return ""
        else:
            filename = src_file[ len( src_dir ):] if src_dir.endswith( '/' ) else src_file[ len( src_dir ) + 1:]
            return s3_path_join( s3_dirname( dest_file ), filename )
    else:
        return ""

def mk_tempdir():
    temp_dir = tempfile.mkdtemp()
    return temp_dir 

def rm_tempdir( temp_dir ):
    files = []
    os.path.walk( temp_dir, lambda arg, dirname, names: files.extend( [ os.path.join( dirname, name ) for name in names ] ), None )
    files = list( reversed( files ) )
    for f in files:
        if os.path.isdir( f ):
            os.rmdir( f )
        else:
            os.remove( f )
    os.rmdir( temp_dir )

def copy_s3_file( src_s3cfg, src_file, dest_s3cfg, dest_file, public = False ):
    filename = download_s3_file( src_s3cfg, src_file)
    if filename is None:
       print( "Fail to download s3 file %s" % src_file )
    else:
        if not upload_s3_file( filename, dest_s3cfg, dest_file, public ):
            print( "Fail to copy %s to %s" % ( src_file, dest_file ) )
    rm_tempdir( os.path.dirname( filename ) )

def download_s3_file( src_s3cfg, s3_file ):
    temp_file = os.path.join( mk_tempdir(), s3_basename( s3_file ) )
    print( "download file %s from %s" % (s3_file, extract_s3host( src_s3cfg ) ) )
    try:
        out = subprocess.check_output( ['s3cmd', '-c', src_s3cfg, 'get', '-f', s3_file, temp_file ] )
        print( out )
        return temp_file
    except Exception as ex:
        print( "fail to download file %s from %s" % ( s3_file, extract_s3host( src_s3cfg ) ) )
        rm_tempdir( os.path.dirname( temp_file ) )
        return None

def upload_s3_file( local_file, dest_s3cfg, dest_file, public ):
    try:
        if public:
            print( "upload & public the file %s to %s" % (dest_file, extract_s3host( dest_s3cfg ) ) )
            out = subprocess.check_output( ['s3cmd', '-c', dest_s3cfg, 'put', "-P", local_file, dest_file ] )
        else:
            print( "upload & don't public the file %s to %s" % (dest_file, extract_s3host( dest_s3cfg) ) )
            out = subprocess.check_output( ['s3cmd', '-c', dest_s3cfg, 'put', local_file, dest_file ] )
        print( out )
        return True
    except Exception as ex:
        print(ex)
        return False

def extract_s3host( s3cfg ):
    with open( s3cfg ) as fp:
        for line in fp:
            line = line.strip()
            if line.startswith( "host_base" ):
                fields = line.split( '=' )
                if len( fields ) == 2:
                    return fields[1].strip()
    return None
def parse_args():
    parser = argparse.ArgumentParser( description = "sync s3 storage between sites" )
    parser.add_argument( "--src-s3cfg", help = "the source s3cfg file", required = True )
    parser.add_argument( "--dest-s3cfg", help = "the destination s3cfg file", required = True )
    parser.add_argument( "--src-file", help = "the source file", required = True )
    parser.add_argument( "--dest-file", help = "the destination file", required = True )
    parser.add_argument( "-P", "--public", action="store_true", help = "make the s3 file available in public", required = False )

    return parser.parse_args()

def main():
    args = parse_args()
    print( args )
    files = list_s3_path( args.src_s3cfg, args.src_file )
    exist_s3_buckets = []
    for f in files:
        dest_filename = get_dest_s3file( args.src_file, f , args.dest_file )
        dest_s3_bucket = get_s3_bucket( dest_filename )
        if dest_s3_bucket not in exist_s3_buckets:
            if s3_bucket_exist( args.dest_s3cfg, dest_s3_bucket ):
                exist_s3_buckets.append( dest_s3_bucket ) 
            elif mk_s3_bucket( args.dest_s3cfg, dest_s3_bucket ):
                exist_s3_buckets.append( dest_s3_bucket )
            else:
                print( "Fail to make non-exist bucket %s" % dest_s3_bucket )
                sys.exit( 1 )
        copy_s3_file( args.src_s3cfg, f, args.dest_s3cfg, dest_filename, args.public )


if __name__ == "__main__":
    main()
