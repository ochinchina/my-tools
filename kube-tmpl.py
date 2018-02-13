#!/usr/bin/python

import functools
import jinja2
import json
import argparse
import os
import tempfile

def load_configs( config_files ):
    result = {}
    for config_file in config_files:
        try:
            with open( config_file ) as fp:
                result.update( json.load(fp) )
        except:
            pass
    return result

def change_project( args, action ):
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
    install_parser.set_defaults( func = functools.partial( change_project, action = "create" ) )
    delete_parser = subparsers.add_parser( "delete", help = "delete a project" )
    delete_parser.add_argument( "--searchpath", help = "the search path of kubernetes .yaml file", required = False, default = "./" )
    delete_parser.add_argument( "--template", help = "the kubernetes .yaml template file", required = True )
    delete_parser.add_argument( "--config-file", help = "the configuration files", nargs = "*", required = True )
    delete_parser.add_argument( "--dry-run", help = "run without install", action = "store_true" )
    delete_parser.set_defaults( func = functools.partial( change_project, action = "delete" ) )
    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )

main()


