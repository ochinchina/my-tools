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

def print_files( files, with_color = False ):
    for filename in files:
        try:
            if os.path.isdir( filename ):
                color_func = blue_color
            elif os.path.isfile( filename ) and os.access( filename, os.X_OK ):
                color_func = green_color
            else:
                color_func = no_color

            text = subprocess.check_output( [ "ls", "-l", filename] ).strip()
            if with_color:
                print color_func( text )
            else:
                print text
        except Exception as ex:
            print ex

def parse_args():
    parser = argparse.ArgumentParser( description = "find files under directory" )
    parser.add_argument( "--sort-by", help = "the sorted method, default is name", choices = [ "date", "name", "size"], default = "name" )
    parser.add_argument( "--head", help = "first n lines" )
    parser.add_argument( "--tail", help = "last n lines" )
    parser.add_argument( "--without-color", help = "no colorful output", action = "store_true" )
    parser.add_argument( "path", help = "the file path" )
    return parser.parse_args()

def get_sort_func( sort_method ):
    sort_funcs = {"name": sort_files_by_name,
                  "date": sort_files_by_date,
                  "size": sort_files_by_size }

    return sort_funcs[ sort_method ]

def main():
    args = parse_args()
    files = find_files( args.path )
    sort_func = get_sort_func( args.sort_by )
    files = sort_func( files )

    if args.head is not None:
        head_files = files[0: int( args.head ) ]
    if args.tail is not None:
        tail_files = files[-1*int( args.tail): -1]

    if head_files is not None:
        print_files( head_files, with_color = not args.without_color )
    if tail_files is not None:
        print_files( tail_files, with_color = not args.without_color )
    if head_files is None and tail_files is None:
        print_files( files, with_color = not args.without_color )

if __name__ == "__main__":
    main()
