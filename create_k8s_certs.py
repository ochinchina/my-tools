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
     }
   }
 }
}"""

CA_CSR = """{
 "CN": "kubernetes",
 "key": {
   "algo": "rsa",
   "size": 2048
 },
 "ca": {
   "expiry": "876000h"
 }
}"""

FRONT_PROXY_CA_CSR = """{
  "CN": "kubernetes-front-proxy",
  "key": {
    "algo": "rsa",
    "size": 2048
  },
  "ca": {
    "expiry": "876000h"
  }
}"""

FRONT_PROXY_CLIENT_CSR = """{
  "CN": "front-proxy-client",
  "hosts": [],
  "key": {
    "algo": "rsa",
    "size": 2048
  }
}"""

APISERVER_KUBELET_CLIENT_CSR = """{
  "CN": "kube-apiserver-kubelet-client",
  "hosts": [],
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

APISERVER_ETCD_CLIENT_CSR = """{
  "CN": "kube-apiserver-etcd-client",
  "hosts": [],
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

APISERVER_CSR_TEMPLATE = """{
  "CN": "kube-apiserver",
  "hosts": [
    "localhost",
    "127.0.0.1",
    "10.96.0.1",
    "kubernetes",
    "kubernetes.default",
    "kubernetes.default.svc",
    "kubernetes.default.svc.cluster",
    "kubernetes.default.svc.cluster.local"
  ],
  "key": {
    "algo": "rsa",
    "size": 2048
  }
}"""

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

def create_apiserver_csr( masters ):
    apiserver_csr = json.loads( APISERVER_CSR_TEMPLATE )
    print( apiserver_csr )
    apiserver_csr['hosts'].extend( masters )
    with open( "apiserver-csr.json", "wb" ) as fp:
        json.dump( apiserver_csr, fp, indent = 4 )

def create_cert( ca_pem, ca_key_pem, ca_config, profile, csr_json_file, output_file ):
    os.system( "cfssl gencert -ca=%s -ca-key=%s --config=%s --profile=%s %s | cfssljson -bare %s" % ( ca_pem, ca_key_pem, ca_config, profile, csr_json_file, output_file ) )

def parse_args():
    parser = argparse.ArgumentParser( description = "generate the k8s certificates" )
    parser.add_argument( "--expiry", help = "expire in days, default is 36500", type= int, default = 36500 )
    parser.add_argument( "--pki-dir", help = "kubernetes pki directory, default is /etc/kubernetes/pki", default = "/etc/kubernetes/pki" )
    parser.add_argument( "--master", help = "all the master host name and their IPs", required = True, nargs = "+" )
    return parser.parse_args()


def main():
    args = parse_args()
    expiry_in_hours = "%dh" % (args.expiry * 24)
    os.chdir( args.pki_dir )
    write_to_file( "ca-config.json", json.loads( CA_CONFIG ), expiry_in_hours )
    write_to_file( "ca-csr.json", json.loads( CA_CSR ), expiry_in_hours )
    write_to_file( "front-proxy-ca-csr.json", json.loads( FRONT_PROXY_CA_CSR ), expiry_in_hours )
    write_to_file( "front-proxy-client-csr.json", json.loads( FRONT_PROXY_CLIENT_CSR ), expiry_in_hours )
    write_to_file( "apiserver-kubelet-client-csr.json", json.loads( APISERVER_KUBELET_CLIENT_CSR ), expiry_in_hours )
    write_to_file( "apserver-etcd-client-csr.json", json.loads( APISERVER_ETCD_CLIENT_CSR ), expiry_in_hours )
    os.system( "cfssl gencert -initca ca-csr.json | cfssljson -bare ca")
    os.system( "cfssl gencert -initca front-proxy-ca-csr.json | cfssljson -bare front-proxy-ca")
    create_apiserver_csr( args.master )
    create_cert( "ca.pem", "ca-key.pem", "ca-config.json", "server", "apiserver-csr.json", "apiserver" )
    create_cert( "front-proxy-ca.pem", "front-proxy-ca-key.pem", "ca-config.json", "client", "front-proxy-client-csr.json", "front-proxy-client" )
    create_cert( "ca.pem", "ca-key.pem", "ca-config.json", "client", "apiserver-kubelet-client-csr.json", "apiserver-kubelet-client" )
    create_cert( "etcd/ca.pem", "etcd/ca-key.pem", "ca-config.json", "client", "apserver-etcd-client-csr.json", "apserver-etcd-client" )
    os.system( "openssl genrsa -out sa.key 2048" )
    os.system( "openssl rsa -in sa.key -pubout -out sa.pub" )




if __name__ == "__main__":
    main()

