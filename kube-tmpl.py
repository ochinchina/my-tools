#!/usr/bin/python

import functools
import jinja2
import json
import argparse
import os
import requests
import tempfile
import yaml

class NameItem:
    def __init__( self, name ):
        self.name = name
        self.index = -1
        if name.endswith( ']' ):
            pos = name.rfind('[' )
            if pos != -1:
                self.index = int ( name[ pos + 1: -1 ].strip() )
                self.name = name[0:pos]

    def is_array( self ):
        return self.index >= 0

def is_json_file( filename ):
    return filename.endswith( ".json" ) or filename.endswith( ".js" )

def load_value_file( value_file ):
    """
    load value file from remote web server or local file system
    """
    if value_file.startswith( "http://" ) or value_file.startswith( "https://" ):
        r = requests.get( value_file )                
        if r.status_code / 100 == 2:
            if is_json_file( value_file ):
                return json.loads( r.content )
            else:
                return yaml.safe_load( r.content )
    else:
        with open( value_file ) as fp:
            if is_json_file( value_file ):
                return json.load(fp)
            else:
                return yaml.safe_load( fp )

def load_value_files( value_files ):
    """
    load the .json or .yaml configuration file. if same item in multiple
    configuration file, the later one will overwrite the previous one

    Args:
        value_files: list of configuration file, and eash one configuration file
        must be in json or in yaml format
    Returns:
        the merged configuration items
    """
    result = {}
    for value_file in value_files:
        print load_value_file( value_file )
        result.update( load_value_file( value_file ) )
    return result

def parse_values( values ):
    """
    parse the values from command line

    Args:
        values: a list of value, each value will be in following format:
          name1.name2.name3=value
          or name1[0].name2.name3= value
    Returns:
        a dictionary
    """
    result = {}
    for value in values:
        pos = value.find( '=' )
        if pos == -1:
           pos = value.find( ':' )
        if pos != -1:
           key = value[0:pos].strip()
           v = value[pos+1:].strip()
           words = key.split( ".")
           items = []
           for w in words:
               items.append( NameItem( w ) )
           cur_result = result
           for i, item in enumerate( items ):
               if item.is_array():
                   if item.name not in cur_result:
                       cur_result[ item.name ] = []
                   while len( cur_result[ item.name ] ) <= item.index:
                       cur_result[ item.name ].append( {} )
                   if i == len( items ) -1:
                       cur_result[ item.name ][item.index] = v
                   else:
                       cur_result = cur_result[ item.name ][item.index]
               else:
                   if item.name not in cur_result:
                       cur_result[ item.name ] = {}
                   if i == len( items ) -1:
                       cur_result[ item.name ] = v
    return result

def load_template( templateEnv, template_path ):
    if template_path.startswith( "http://" ) or template_path.startswith( "https://" ):
        r = requests.get( template_path )
        if r.status_code / 100 == 2:
            return templateEnv.from_string( r.content )
    else:
        return templateEnv.get_template( os.path.abspath( template_path ) ) 

def change_deployment( args, action ):
    """
    change the kubernetes deployment

    Args:
        args: the command line arguments
        action: must be create or delete
    Returns:
        if --dry-run flag is in the command line, only print the changed template
        otherwise it will call kubectl command to create/delete deployments
    """
    templateLoader = jinja2.FileSystemLoader( searchpath = "/" )
    templateEnv = jinja2.Environment( loader=templateLoader )
    template = load_template( templateEnv, args.template )
    config = {}
    if args.value_files:
        config.update( load_value_files( args.value_files) )
    if args.values:
        config.update( parse_values( args.values ) )
    if args.dry_run:
        print template.render( config )
    else:
        with tempfile.NamedTemporaryFile( suffix = ".yaml", delete = False ) as fp:
            fp.write( template.render( config ) )
            filename = fp.name
        try:
            os.system( "kubectl %s -f %s" % ( action, filename ) )
        except:
            pass
        os.remove( filename )

def parse_args():
    parser = argparse.ArgumentParser( description = "generate template" )
    parser.add_argument( "--template", help = "the kubernetes .yaml template file", required = True )
    parser.add_argument( "--value-files", help = "the configuration files", nargs = "*", required = False )
    parser.add_argument( "--dry-run", help = "run without real action", action = "store_true" )
    parser.add_argument( "--values", help = "the values", nargs = "*", required = False )
    subparsers = parser.add_subparsers( help = "install a project" )
    install_parser = subparsers.add_parser( "install", help = "install a project" )
    install_parser.set_defaults( func = functools.partial( change_deployment, action = "create" ) )
    delete_parser = subparsers.add_parser( "delete", help = "delete a project" )
    delete_parser.set_defaults( func = functools.partial( change_deployment, action = "delete" ) )
    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()


