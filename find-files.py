#!/usr/bin/python

import argparse
import os
import subprocess

def blue_color( text ):
    return "\033[34m%s\033[0m"%text

def green_color( text ):
    return "\033[32m%s\033[0m"% text

def no_color( text ):
    return text

def find_files( path ):
    files = []
    os.path.walk( path, lambda arg, dirname, names: files.extend( [ os.path.join( dirname, name ) for name in names ] ), None )
    return filter( lambda filename: os.path.isfile( filename ), files )
    #return files

def sort_files_by_name( files, reverse = False ):
    return sorted( files, reverse = reverse )


def sort_files_by_date( files, reverse = False ):
    files_with_modified_time = []
    for filename in files:
        files_with_modified_time.append( (  filename, os.path.getmtime( filename ) ) )
    files_with_modified_time = sorted( files_with_modified_time, key = lambda x: x[1], reverse = reverse )
    return map( lambda x: x[0], files_with_modified_time )

def sort_files_by_size( files, reverse = False ):
    files_with_size = []
    for filename in files:
        files_with_size.append( ( filename, os.path.getsize( filename ) ) )
    return map( lambda x: x[0], sorted( files_with_size, key = lambda x: x[1], reverse = reverse  ) )

def no_sort( files, reverse = False ):
    return files

def get_biggest_file_size( files ):
    biggest_file_size = 0
    for filename in files:
        if os.path.isfile( filename ):
            size = os.path.getsize( filename )
        else:
            size = 99
        if size > biggest_file_size:
            biggest_file_size = size
    return biggest_file_size

def print_files( files, with_color = False ):
    biggest_file_size = get_biggest_file_size( files )

    size_width = len( "%d" % biggest_file_size )
    size_format = "%%%ds" % size_width
    for filename in files:
        try:
            if os.path.isdir( filename ):
                color_func = blue_color
            elif os.path.isfile( filename ) and os.access( filename, os.X_OK ):
                color_func = green_color
            else:
                color_func = no_color

            text = subprocess.check_output( [ "ls", "-l", filename] ).strip().split()
            text[4] = size_format % text[4]
            text = " ".join( text )

            if with_color:
                print color_func( text )
            else:
                print text
        except Exception as ex:
            print ex

def parse_args():
    parser = argparse.ArgumentParser( description = "find files under directory" )
    parser.add_argument( "--sort-by", help = "the sort method", choices = [ "date", "name", "size"] )
    parser.add_argument( "--head", help = "first n lines" )
    parser.add_argument( "--tail", help = "last n lines" )
    parser.add_argument( "--without-color", help = "no colorful output", action = "store_true" )
    parser.add_argument( "path", help = "the file path" )
    return parser.parse_args()

def get_sort_func( sort_method ):
    sort_funcs = {"name": sort_files_by_name,
                  "date": sort_files_by_date,
                  "size": sort_files_by_size }

    return sort_funcs[ sort_method ] if sort_method in sort_funcs else no_sort

def main():
    args = parse_args()
    files = find_files( args.path )
    sort_func = get_sort_func( args.sort_by )
    files = sort_func( files )

    if args.head is not None:
        head_files = files[0: int( args.head ) ]
    else:
        head_files = None
    if args.tail is not None:
        tail_files = files[-1*int( args.tail): -1]
    else:
        tail_files = None

    printed_files = []
    if head_files is not None:
        printed_files.extend( head_files )
    if tail_files is not None:
        printed_files.extend( tail_files )
    if len( printed_files ) <= 0:
        printed_files = files
    print_files( printed_files, with_color = not args.without_color )

if __name__ == "__main__":
    main()

