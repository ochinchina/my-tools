#!/usr/bin/python

import functools
import jinja2
import json
import argparse
import os
import tempfile
import yaml

def load_configs( config_files ):
    """
    load the .json or .yaml configuration file. if same item in multiple
    configuration file, the later one will overwrite the previous one

    Args:
        config_files: list of configuration file, and eash one configuration file
        must be in json or in yaml format
    Returns:
        the merged configuration items
    """
    result = {}
    for config_file in config_files:
        try:
            with open( config_file ) as fp:
                if config_file.endswith( ".json" ) or config_file.endswith( ".js" ):
                    result.update( json.load(fp) )
                else:
                    result.update( yaml.safe_load( fp ) )
        except:
            pass
    return result

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
    templateLoader = jinja2.FileSystemLoader( searchpath = args.searchpath )
    templateEnv = jinja2.Environment( loader=templateLoader )
    template = templateEnv.get_template( args.template )
    config = load_configs( args.config_file )
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
    subparsers = parser.add_subparsers( help = "install a project" )
    install_parser = subparsers.add_parser( "install", help = "install a project" )
    install_parser.add_argument( "--searchpath", help = "the search path of kubernetes .yaml file", required = False, default = "./" )
    install_parser.add_argument( "--template", help = "the kubernetes .yaml template file", required = True )
    install_parser.add_argument( "--config-file", help = "the configuration files", nargs = "*", required = True )
    install_parser.add_argument( "--dry-run", help = "run without install", action = "store_true" )
    install_parser.set_defaults( func = functools.partial( change_deployment, action = "create" ) )
    delete_parser = subparsers.add_parser( "delete", help = "delete a project" )
    delete_parser.add_argument( "--searchpath", help = "the search path of kubernetes .yaml file", required = False, default = "./" )
    delete_parser.add_argument( "--template", help = "the kubernetes .yaml template file", required = True )
    delete_parser.add_argument( "--config-file", help = "the configuration files", nargs = "*", required = True )
    delete_parser.add_argument( "--dry-run", help = "run without install", action = "store_true" )
    delete_parser.set_defaults( func = functools.partial( change_deployment, action = "delete" ) )
    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )

main()


