#!/usr/bin/env python

import atexit
import argparse
import base64
import tempfile
import yaml
import os

def load_conf_file( filename ):
    with open( filename ) as fp:
        return yaml.load( fp )

def get_value_by_key( root, key ):
    if key in root:
        return root[key]

    for name in root:
        item = root[name] if type( root ) == dict else name
        if type( item ) in (dict, list):
            value = get_value_by_key( item, key )
            if value is not None:
                return value
            
    return None

def write_cert_file( value ):
    f, name = tempfile.mkstemp()
    os.close( f )
    with open( name, "wb" ) as fp:
        fp.write( value )

    atexit.register( os.remove, name )
    return name

def print_cert_end_date( cert_file ):
    os.system( "openssl x509 -enddate -noout -in %s" % cert_file ) 
    os.system( "cfssl-certinfo --cert %s" % cert_file )
    os.system( "openssl x509 -text -noout -in %s" % cert_file )

def parse_args():
    parser = argparse.ArgumentParser( description = "check the k8s certificates expiration" )
    parser.add_argument( "--k8s-conf", help = "k8s configuration filea", required = True )
    parser.add_argument( "--key", help = "the key in the configuration file", required = True )
    return parser.parse_args()


def main():
    args = parse_args()
    root = load_conf_file( args.k8s_conf )
    value = get_value_by_key( root, args.key )
    fname = write_cert_file( base64.b64decode( value ) )
    print_cert_end_date( fname )
    

if __name__ == "__main__":
    main()

