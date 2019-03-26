#!/usr/bin/env python

import argparse
import json
import os

CA_CONFIG = """{
   "signing": {
       "default": {
         "expiry": "876000h"
       },
       "profiles": {
         "server": {
           "expiry": "876000h",
           "usages": [
             "signing",
             "key encipherment",
             "server auth"
           ]
         },
         "client": {
           "expiry": "876000h",
           "usages": [
             "signing",
             "key encipherment",
             "client auth"
           ]
         },
         "peer": {
           "expiry": "876000h",
           "usages": [
             "signing",
             "key encipherment",
             "server auth",
             "client auth"
           ]
         }

       }
   }
}"""

CA_CSR = """{
  "CN": "etcd",
  "key": {
    "algo": "rsa",
    "size": 2048
  },
  "ca": {
    "expiry": "876000h"
  }
}"""

CLIENT_CSR = """{
 "CN": "kube-etcd-healthcheck-client",
 "key": {
     "algo": "rsa",
     "size": 2048
 },
 "hosts":[""]
}
"""

ETCD_PEER_CSR_TEMPLATE = """
{
    "CN": "kube-etcd-peer",
    "key": {
               "algo": "rsa",
               "size": 2048
    },
    "hosts": [
               "localhost",
               "127.0.0.1"
    ],
    "names": [{
              "O": "system:masters"
    }]
}
"""

ETCD_SERVER_CSR_TEMPLATE = """
{
    "CN": "kube-etcd",
    "key": {
               "algo": "rsa",
               "size": 2048
    },
    "hosts": [
               "localhost",
               "127.0.0.1"
    ]
}
"""

def change_expiry( element, expiry ):
    if type( element ) == dict and 'expiry' in element:
        element['expiry'] = expiry
    elif type(element) in ( list, dict ):
        for item in element:
            if type( element ) == dict:
                item = element[ item ]
            change_expiry( item, expiry )

def write_to_file( filename, csr_json, expiry ):
    change_expiry( csr_json, expiry )
    with open( filename, "wb" ) as fp:
        json.dump( csr_json, fp, indent = 4 )

def create_cert( profile, csr_json_file, output ):
    os.system( "cfssl gencert -ca=ca.pem -ca-key=ca-key.pem --config=ca-config.json -profile=%s %s | cfssljson -bare %s" % (profile, csr_json_file, output ) )

def create_etcd_peer_csr( nodes ):
    etcd_peer_csr = json.loads( ETCD_PEER_CSR_TEMPLATE )
    etcd_peer_csr['hosts'].extend( nodes )
    with open( "peer-csr.json", "wb" ) as fp:
        json.dump( etcd_peer_csr, fp, indent = 4 )

def create_etcd_server_csr( nodes ):
    etcd_server_csr = json.loads( ETCD_SERVER_CSR_TEMPLATE )
    etcd_server_csr['hosts'].extend( nodes )
    with open( "server-csr.json", "wb" ) as fp:
        json.dump( fp, etcd_server_csr, indent = 4 )

def parse_args():
    parser = argparse.ArgumentParser( description = "generate the k8s certificates" )
    parser.add_argument( "--expiry", help = "expire in days, default is 36500", type= int, default = 36500 )
    parser.add_argument( "--pki-dir", help = "kubernetes pki directory, default is /etc/kubernetes/pki/etcd", default = "/etc/kubernetes/pki/etcd" )
    parser.add_argument( "--nodes", help = "all the etcd nodes name and their IPs", required = True, nargs = "+" )
    return parser.parse_args()

def main():
    args = parse_args()
    expiry_in_hours = "%dh" % (args.expiry * 24)
    if not os.path.exists( args.pki_dir ):
        os.makedirs( args.pki_dir )
    os.chdir( args.pki_dir )
    write_to_file( "ca-config.json", json.loads( CA_CONFIG ), expiry_in_hours )
    write_to_file( "ca-csr.json", json.loads( CA_CSR ), expiry_in_hours )
    write_to_file( "client-csr.json", json.loads( CLIENT_CSR ), expiry_in_hours )
    create_etcd_peer_csr( args.nodes )
    os.system( "cfssl gencert -initca ca-csr.json | cfssljson -bare ca")
    create_cert( "server", "server-csr.json", "server" )
    create_cert( "client", "client-csr.json", "client" )
    create_cert( "client", "peer-csr.json", "peer" )



if __name__ == "__main__":
    main()

