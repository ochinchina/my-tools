#!/usr/bin/python

import requests
import os
import sys
import shutil
import tempfile
import argparse
import subprocess
import json
import yaml

class TextColor:
    @staticmethod
    def red( text ):
        return '\033[0;31m%s\033[0m' % text
    @staticmethod
    def green( text ):
        return '\033[0;32m%s\033[0m' % text
    @staticmethod
    def blue( text ):
        return '\033[0;34m%s\033[0m' % text

def is_json_syntax_ok( filename ):
    try:
        with open( filename ) as fp:
            json.load( fp )
        return True
    except Exception as ex:
        print TextColor.red( "%s" % ex )
        return False

def is_yaml_syntax_ok( filename ):
    try:
        with open( filename ) as fp:
            yaml.load( fp )
        return True
    except Exception as ex:
        print TextColor.red( "%s" % ex )
        return False

def get_file_ext( filename ):
    pos = filename.rfind( '.' )
    if pos == -1 or pos == 0:
        return ""

    return filename[pos+1:]

def is_syntax_ok( filename ):
    ext = get_file_ext( filename )
    ext_syntax_checker = { "json": is_json_syntax_ok,
                           "yml": is_yaml_syntax_ok,
                           "yaml": is_yaml_syntax_ok }
    syntax_check_func = ext_syntax_checker[ ext ] if ext in ext_syntax_checker else None
    return syntax_check_func is None or syntax_check_func( filename )

def list_files( args ):
    """
    list all files in a directory
    """
    url = find_config_server_url( args )
    if args.dir:
        r = requests.get( "%s/list?dir=%s" % (url, args.dir ) )
    else:
        r = requests.get( "%s/list" % url )
    if r.status_code / 100 == 2:
        files = []
        dirs = []
        for f in r.json():
            if 'file' in f:
                files.append( "file {}".format( f['file'] ) )
            elif 'dir' in f:
                dirs.append( "dir {}".format( f['dir'] ) )
        print "\n".join( sorted( files ) )
        print "\n".join( sorted( dirs ) )

def cat_file( args ):
    url = find_config_server_url( args )
    temp_dir = tempfile.mkdtemp()
    file_name = download_file( url, args.file, temp_dir, True, True )
    with open( file_name ) as fp: sys.stdout.write( fp.read() )
    os.remove( file_name )
    os.rmdir( temp_dir )

def add_files( args ):
    """
    add a list of files to the configuration server
    """
    if not args.without_syntax_check:
        for f in args.files:
            if not is_syntax_ok( f ):
                print TextColor.red( "Fail to add the file %s to config-server because syntax of some files are not ok" % f )
                sys.exit( 1 )
    url = find_config_server_url( args )
    dest = args.dest if args.dest else ""
    for f in args.files:
        if os.path.isdir( f ):
            files = list_relative_files( f )
            for tmp in files:
                local_file = os.path.join( f, tmp )
                if os.path.isfile( local_file ): add_file( url, local_file, os.path.join( dest, tmp ) )
        elif os.path.isfile( f ):
            add_file( url, f, os.path.join( dest, os.path.basename( f ) ) )
        else:
            print( "{} is not a directory or file".format( f ) )

    commit( url )

def list_relative_files( dirname ):
    dirname = os.path.abspath( dirname )
    files = []
    os.path.walk( dirname, lambda arg, dirname, names: files.extend( [ os.path.join( dirname, name ) for name in names ] ), None )
    for i, f in enumerate( files ):
        files[i] = f[len( dirname ) + 1:]

    return files
def add_file( url, local_file, dest_file ):
    """
    saveg the local file to the file dest_file in NLS configuration server
    """
    with open( local_file ) as fp:
        data = fp.read()
        r = requests.post( "%s/upload?file=%s" % (url, dest_file ), data = data )
        if r.status_code / 100 == 2:
            print( "succeed to save local file {} to file {} in configuration server".format( local_file, dest_file ) )
        else:
            print( "fail to save local file {} to file {} in configuration server".format( local_file, dest_file ) )

def download_file( url, file_name, out_dir, keep_path, force_overwrite ):
    """
    download a file from configuration server
    """
    r = requests.get( "%s/download?file=%s" % (url, file_name), stream = True )
    if r.status_code / 100 == 2:
        local_file_name = os.path.abspath( "%s/%s" % ( out_dir, file_name ) ) if keep_path else os.path.abspath( "%s/%s" % ( out_dir, os.path.basename( file_name ) ) )
        if not force_overwrite and os.path.exists( local_file_name ):
            input = raw_input("the local file %s exists already, overwrite it(Y/N)?" % local_file_name)
        else:
            input = "y"
        if input in ['y', 'Y']:
            file_dir = os.path.dirname( local_file_name )
            if not os.path.exists( file_dir ):
                os.makedirs( file_dir )
            with open( local_file_name, "wb" ) as fp:
                shutil.copyfileobj( r.raw, fp )
                return local_file_name
    return None

def download_files( args ):
    """
    download a file and save it to local filesystem
    """
    url = find_config_server_url( args )
    for file_name in args.files:
        download_file( url, file_name, args.output, args.keep_path, args.force )

def find_a_editor():
    prefer_editors = ["vim", "vi", "nano"]

    for editor in prefer_editors:
        try:
            if os.system( "which %s" % editor ) == 0:
                return editor
        except ex as Exception:
            print ex
    return ""

def edit_file( args ):
    url = find_config_server_url( args )
    r = requests.get( "%s/download?file=%s" % (url, args.file), stream = True )
    if r.status_code / 100 == 2:
        fp = tempfile.NamedTemporaryFile( delete = False, suffix = ".%s" % get_file_ext( args.file )  )
        shutil.copyfileobj( r.raw, fp )
        fp.close()
        editor = args.editor if args.editor else find_a_editor()
        if not editor:
            print "Please set --editor parameter"
        else:
            with open( fp.name ) as f:
                data_before_edit = f.read()
            os.system( "%s %s" % ( editor, fp.name ) )
            if not args.without_syntax_check and not is_syntax_ok( fp.name ):
                print TextColor.red( "Fail to save the file to config-server because of syntax error" )
                sys.exit( 1 )
            with open( fp.name ) as f:
                data = f.read()
                if data == data_before_edit:
                    print "No change in file"
                else:
                    r = requests.post( "%s/upload?file=%s" % (url, args.file ), data = data )
                    print r.content
                    commit( url )
        os.remove( fp.name )

def create_branch( args ):
    """
    create branch
    """
    url = find_config_server_url( args )
    r = requests.put( "%s/make_branch?branch=%s" % (url, args.name ), stream = True )
    print r.content

def list_branch( args ):
    """
    list all the branches
    """
    url = find_config_server_url( args )
    r = requests.get( "%s/list_branch" % url, stream = True )
    print r.content


def delete_file( args ):
    url = find_config_server_url( args )
    r = requests.put( "%s/delete?file=%s" % (url, args.file), stream = True )
    return r.content

def switch_branch( args ):
    url = find_config_server_url( args )
    r = requests.put( "%s/switch_branch?branch=%s" % (url, args.name ), stream = True )
    print r.content

def list_all_files( url ):
    """
    list all the files in the config-server
    """
    dirs = [ '/' ]
    files = []


    while len( dirs ) > 0:
        cur_dir = dirs.pop()
        r = requests.get( "%s/list?dir=%s" % (url, cur_dir ) )
        if r.status_code / 100 == 2:
            for f in r.json():
                if 'file' in f:
                    files.append( f['file'] )
                elif 'dir' in f:
                    dirs.append( f['dir'] )
    return files

def backup_config( args ):
    """
    backup the NLS configuration
    """
    url = find_config_server_url( args )
    files = list_all_files( url )
    tmp_dir = tempfile.mkdtemp()
    filename = os.path.abspath( args.filename )
    if not filename.endswith( ".tar.gz" ): filename = "{}.tar.gz".format( filename )

    for f in files:
        download_file( url, f, tmp_dir, True, True )
    os.chdir( tmp_dir )
    os.system( "tar cv * | gzip -c >{}".format( filename )  )
    os.system( "rm -rf {}".format( tmp_dir ) )
    print( "backup the NLS configuration to file {}".format( filename ) )

def restore_config( args ):
    """
    restore the NLS configuration from file backuped before
    """
    url = find_config_server_url( args )
    if os.path.isfile( args.filename ):
        tmp_dir = tempfile.mkdtemp()
        os.system( "tar -zxvf {} -C {}".format( args.filename, tmp_dir ) )
        config_dir = tmp_dir
    elif os.path.isdir( args.filename ):
        config_dir = args.filename
    else:
        print( "file or directory {} does not exist".format( args.filename ) )
        return

    config_dir = os.path.abspath( config_dir )
    if os.path.isdir( config_dir ):
        files = []
        os.path.walk( config_dir, lambda arg, dirname, names: files.extend( [ os.path.join( dirname, name ) for name in names ] ), None )
        for f in files:
            if os.path.isfile( f ):
                dest_file = f[ len( config_dir ) + 1:]
                add_file( url, f, dest_file )

    if os.path.isfile( args.filename ):
        os.system( "rm -rf {}".format( tmp_dir ) )

    commit( url )

def make_tag( args ):
    """
    make tag
    """
    url = find_config_server_url( args )
    r = requests.put( "%s/make_tag?tag=%s" % (url, args.name ), stream = True )
    print r.content

def switch_tag( args ):
    """
    switch to tag
    """
    url = find_config_server_url( args )
    r = requests.put( "%s/switch_tag?tag=%s" % (url, args.name ), stream = True )
    print r.content

def list_tag( args ):
    """
    list all tags
    """
    url = find_config_server_url( args )
    r = requests.get( "%s/list_tag" % url, stream = True )
    print r.content

def commit( url ):
    """
    commit the change
    """
    r = requests.put( "%s/commit" % url )
    print r.content

def find_config_server_url( args ):
    if args.url:
        return args.url
    try:
        out = subprocess.check_output(['kubectl', 'describe', 'service', 'config-server'] )
        for line in out.split( "\n" ):
            if line.startswith( "IP:"):
                ip = line[3:].strip()
            elif line.startswith( "Port:"):
                port = line.split()[-1].split( "/")[0]
        return "http://%s:%s" % ( ip, port )
    except Exception as ex:
        print ex
        print "Please check if VNLS config server is started or set --url parameter"
        sys.exit(1)

def load_args():
    parser = argparse.ArgumentParser( description="edit the configuration file" )
    subparsers = parser.add_subparsers( help="edit the configuration file")
    list_parser = subparsers.add_parser( "ls", help = "list all configuration files")
    list_parser.add_argument( "--url", required = False, help = "the base url")
    list_parser.add_argument( "dir", nargs="?", help = "the directory to be listed", default = "/")
    list_parser.set_defaults( func = list_files )
    cat_parser = subparsers.add_parser( "cat", help = "display the content of configuration file" )
    cat_parser.add_argument( "--url", required = False, help = "the base url")
    cat_parser.add_argument( "file", help = "the file to be displayed" )
    cat_parser.set_defaults( func = cat_file )
    add_parser = subparsers.add_parser( "add", help = "add a file to configuration" )
    add_parser.add_argument( "--url", required = False, help = "the base url")
    add_parser.add_argument( "--dest", required = False, help = "the destination dir" )
    add_parser.add_argument( "--without-syntax-check", action = "store_true", help = "don't check the syntax of added file" )
    add_parser.add_argument( "files", nargs = "+", help = "the files to be added" )
    add_parser.set_defaults( func = add_files )
    download_parser = subparsers.add_parser( "download", help = "download one or more configuration files")
    download_parser.add_argument( "--url", required = False, help = "the base url")
    download_parser.add_argument( "--output", required = False, default = "./", help = "the output directory to save the file")
    download_parser.add_argument( "--force", required = False, action = "store_true", help = "force to overwrite the same local file")
    download_parser.add_argument( "--keep-path", required = False, action = "store_true", help = "keep the path hierarchy" )
    download_parser.add_argument( "files", nargs = "+", help = "the files to be dowloaded" )
    download_parser.set_defaults( func = download_files )
    edit_parser = subparsers.add_parser( "edit", help = "edit a file" )
    edit_parser.add_argument( "--url", required = False, help = "the base url" )
    edit_parser.add_argument( "--editor", required = False, help = "the editor to be used")
    edit_parser.add_argument( "--without-syntax-check", action = "store_true", help = "don't check the syntax of added file" )
    edit_parser.add_argument( "file",  help = "the file to be edit" )
    edit_parser.set_defaults( func = edit_file )

    delete_parser = subparsers.add_parser( "delete", help = "delete a file" )
    delete_parser.add_argument( "--url", required = False, help = "the base url" )
    delete_parser.add_argument( "file",  help = "the file to be deleted" )
    delete_parser.set_defaults( func = delete_file )

    branch_parser = subparsers.add_parser( "branch", help = "manage branch" )
    branch_subparsers = branch_parser.add_subparsers( help="branch management")
    branch_create_parser = branch_subparsers.add_parser( "create", help = "create a branch" )
    branch_create_parser.add_argument( "--url", required = False, help = "the base url")
    branch_create_parser.add_argument( "name", help = "the branch to be created" )
    branch_create_parser.set_defaults( func = create_branch )
    branch_list_parser = branch_subparsers.add_parser( "ls", help = "list the branches" )
    branch_list_parser.add_argument( "--url", required = False, help = "the base url")
    branch_list_parser.set_defaults( func = list_branch )
    branch_switch_parser = branch_subparsers.add_parser( "switch", help = "switch to branch" )
    branch_switch_parser.add_argument( "--url", required = False, help = "the base url")
    branch_switch_parser.add_argument( "name", help = "the branch name" )
    branch_switch_parser.set_defaults( func = switch_branch )

    backup_parser = subparsers.add_parser( "backup", help = "backup the configuration" )
    backup_parser.add_argument( "--url", required = False, help = "the base url")
    backup_parser.add_argument( "filename", help = "the name of file to save the backup configuration in .tar.gz format" )
    backup_parser.set_defaults( func = backup_config )

    restore_parser = subparsers.add_parser( "restore", help = "restore the configuration" )
    restore_parser.add_argument( "--url", required = False, help = "the base url" )
    restore_parser.add_argument( "filename", help = "the name of backup file" )
    restore_parser.set_defaults( func = restore_config )

    tag_parser = subparsers.add_parser( "tag", help = "tag management" )
    tag_subparsers = tag_parser.add_subparsers( help="tag management")
    make_tag_parser = tag_subparsers.add_parser( "make", help = "make tag" )
    make_tag_parser.add_argument( "name", help = "the tag name" )
    make_tag_parser.add_argument( "--url", required = False, help = "the base url")
    make_tag_parser.set_defaults( func = make_tag )

    switch_tag_parser = tag_subparsers.add_parser( "switch", help = "make tag" )
    switch_tag_parser.add_argument( "name", help = "the tag name" )
    switch_tag_parser.add_argument( "--url", required = False, help = "the base url")
    switch_tag_parser.set_defaults( func = switch_tag )

    list_tag_parser = tag_subparsers.add_parser( "ls", help = "make tag" )
    list_tag_parser.add_argument( "--url", required = False, help = "the base url")
    list_tag_parser.set_defaults( func = list_tag )

    return parser.parse_args()

def unset_http_proxy():
    if 'http_proxy'  in os.environ: del os.environ['http_proxy']
    if 'https_proxy' in os.environ: del os.environ['https_proxy']
def main():
    unset_http_proxy()
    args = load_args()
    args.func(args)

if __name__ == "__main__":
    main()
