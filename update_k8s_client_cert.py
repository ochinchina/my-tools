#!/usr/bin/env python

import atexit
import argparse
import base64
import json
import tempfile
import yaml
import os
import subprocess

CA_CONFIG = """{
    "signing": {
        "default": {
            "expiry": "24h"
        },
        "profiles": {
            "client": {
                "usages": [
                    "signing",
                    "key encipherment",
                    "client auth"
                ],
                "expiry": "24h"
            },
            "server": {
                "usages": [
                    "signing",
                    "key encipherment",
                    "server auth"
                ],
                "expiry": "24h"
            }
        }
    }
}
"""

ADMIN_CSR = """{
    "hosts": [],
    "CN": "kubernetes-admin",
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "O": "system:masters"
        }
    ]
}"""

SCHEDULER_CSR = """{
    "hosts": [],
    "CN": "system:kube-scheduler",
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}"""

CONTROLLER_MANAGER_CSR = """{
    "hosts": [],
    "CN": "system:kube-controller-manager",
    "key": {
        "algo": "rsa",
        "size": 2048
    }
}"""

KUBELET_CSR_TEMPLATE =  """{
    "hosts": [],
    "CN": "system:node:<NODE_NAME>",
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "O": "system:nodes"
        }
    ]
}"""



def load_conf_file( filename ):
    with open( filename ) as fp:
        return yaml.load( fp )

def exist_key( element, key ):
    """
    check if the key exists or not at any level

    Args:

      element: the dict element
      key: the key be cheked

    Return:
      True if the key exists at any level of the element
    """
    print( "=========================\n%s" % element )
    if type( element ) == dict and key in element:
        return True

    if type( element ) in ( dict, list ):
        for name in element:
            item = element[name] if type( element ) == dict else name
            if type( item ) in (dict, list) and exist_key( item, key ):
                return True
    else:
        return False

def backup_conf_file( filename ):
    i = 0
    while True:
        i += 1
        backup_filename = "%s.back_%d" % ( filename, i )
        if not os.path.exists( backup_filename ):
            os.system( "cp %s %s" % ( filename, backup_filename ) )
            break

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

def set_key_value( root, key, value ):
    if key in root:
        root[key] = value
    else:
        for name in root:
            item = root[name] if type( root ) == dict else name
            if type( item ) in (dict, list):
                set_key_value( item, key, value )

def change_expiry( element, expiry ):
    if type( element ) == dict and 'expiry' in element:
        element['expiry'] = expiry
    elif type(element) in ( list, dict ):
        for item in element:
            if type( element ) == dict:
                item = element[ item ]
            change_expiry( item, expiry )

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

def create_ca_config( expiry ):
    ca_config = json.loads( CA_CONFIG )
    change_expiry( ca_config, expiry )
    with open( "ca-config.json", "wb" ) as fp:
        json.dump( ca_config, fp, indent = 4 )

def create_ca_csr():
    os.system( "openssl x509 -in ca.crt -signkey ca.key -x509toreq -out ca.csr" )

def create_cert( profile, csr_json_file, output ):
    os.system( "cfssl gencert -ca=pki/ca.crt -ca-key=pki/ca.key --config=ca-config.json -profile=%s %s | cfssljson -bare %s" % (profile, csr_json_file, output ) )

def parse_args():
    parser = argparse.ArgumentParser( description = "check the k8s certificates expiration" )
    parser.add_argument( "--kube-dir", help = "kubernetes configuration dir to store configuration file such as admin.conf, scheduler.conf, default is /etc/kubernetes", required = False, default = "/etc/kubernetes" )
    parser.add_argument( "--expiry", help = "expiration in days, default is 36500", default = 36500, type = int )
    parser.add_argument( "--nodes", help = "all the node names in the cluster", nargs = "*" )
    return parser.parse_args()

def base64_file( filename ):
    with open( filename ) as fp:
        return base64.b64encode( fp.read() )

def replace_key( element, key, value ):
    if type( element ) == dict and key in element:
        element[ key ] = value
    elif type( element ) in (dict, list):
        for name in element:
            item = element[name] if type( element ) == dict else name
            replace_key( item, key, value )

def to_yaml( element ):
    return yaml.dump( element, default_flow_style = False )

def replace_conf_file( filename, replaced_key_values ):
    content = load_conf_file( filename )
    for key in replaced_key_values:
        replace_key( content, key, replaced_key_values[key] )
    backup_conf_file( filename )
    with open( filename, "wb" ) as fp:
        fp.write( to_yaml( content ) )

def create_worker_kubelet_client_csr( node ):
    content = KUBELET_CSR_TEMPLATE.replace( "<NODE_NAME>", node )
    with open( "kubelet-client-csr.json", "wb" ) as fp:
        fp.write( content )

def is_local_node( node ):
    try:
        out = subprocess.check_output( ['hostname'] ).strip()
        return out == node
    except:
        return False

def main():
    args = parse_args()
    os.chdir( args.kube_dir )
    expiry_hours = "%dh" % ( args.expiry * 24 )
    create_ca_config( expiry_hours )
    create_ca_csr()
    client_conf = { "admin.conf": ADMIN_CSR, "controller-manager.conf": CONTROLLER_MANAGER_CSR, "scheduler.conf": SCHEDULER_CSR }

    for filename in client_conf:
        csr_filename = filename.replace( ".conf", "-csr.json" )
        with open( csr_filename, "wb" ) as fp:
            fp.write( client_conf[ filename ] )
        pem_file = filename.replace( ".conf", "" )
        create_cert( "client", csr_filename, pem_file )
        client_cert = base64_file( "%s.pem" % pem_file )
        client_key = base64_file( "%s-key.pem" % pem_file )
        replace_conf_file( filename, {"client-certificate-data": client_cert, "client-key-data": client_key } )

    for node in args.nodes:
        create_worker_kubelet_client_csr( node )
        create_cert( "client", "kubelet-client-csr.json", "kubelet-client-%s" % node )
        if is_local_node( node ) and exist_key( load_conf_file( "kubelet.conf" ), "client-certificate-data" ): 
            client_cert = base64_file( "kubelet-client-%s.pem" % node )
            client_key = base64_file( "kubelet-client-%s-key.pem" % node )
            replace_conf_file( "kubelet.conf", {"client-certificate-data": client_cert, "client-key-data": client_key } )
        
if __name__ == "__main__":
    main()

