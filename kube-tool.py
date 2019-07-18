#!/usr/bin/python

import argparse
import json
import subprocess
import sys
from prettytable import PrettyTable

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

class Container:
    def __init__( self, container_info, status ):
        self.container_info = container_info
        self.status = status

    def get_name( self ):
        return self.container_info['name']

    def get_image( self ):
        return self.container_info['image']

    def get_status( self ):
        if self.status is None:
            return "Pending"
        if 'running' in self.status['state']:
            return "Running"
        if 'waiting' in self.status['state']:
            return self.status['state']['waiting']['reason']
        if 'terminated' in self.status['state']:
            return "Terminating"

class Pod:
    def __init__( self, pod_info ):
        self.pod_info = pod_info
        self.containers = []

        containers_info = {}

        #print json.dumps( pod_info, indent = 4 )
        #sys.exit( 1 )
        for info in pod_info['spec']['containers']:
            containers_info[ info['name'] ] = {'container': info }
        if 'containerStatuses' in pod_info['status']:
            for status_info in pod_info['status']['containerStatuses']:
                containers_info[ status_info['name'] ]['status'] = status_info

        for name in containers_info:
            self.containers.append( Container( containers_info[name][ 'container' ], containers_info[name]['status'] if 'status' in containers_info[name] else None ) )

    def get_containers( self ):
        return self.containers

    def get_name( self ):
        return self.pod_info['metadata']['name']

    def get_status( self ):
        terminatings = filter( lambda x: x == "Terminating", map( lambda x: x.get_status(), self.containers ) )
        return self.pod_info['status']['phase'] if len( terminatings ) <= 0 else 'Terminating'

    def get_pod_ip( self ):
        return self.pod_info['status']['podIP'] if 'podIP' in self.pod_info['status'] else ""

    def get_node_name( self ):
        return self.pod_info['spec']['nodeName'] if 'nodeName' in self.pod_info['spec'] else ""
    def get_host_ip( self ):
        return self.pod_info['status']['hostIP'] if 'hostIP' in self.pod_info['status'] else ""

class K8S:
    def __int__( self ):
        pass

    def list_pods( self, namespace ):
        """
        list all the pods
        """
        out = subprocess.check_output( ["kubectl", "get", "pod", "-o", "json", "-n", namespace ] )
        pods_info = json.loads( out )
        return [ Pod( pod_info ) for pod_info in pods_info['items'] ]

def get_pod( args ):
    k8s = K8S()
    pods = k8s.list_pods( args.namespace )
    x = PrettyTable()
    x.field_names  = ['pod', 'container', 'status'] if args.with_container else [ 'pod', 'pod-ip', 'host', 'host-ip', 'status' ]
    for pod in pods:
        if args.pod_name is not None and pod.get_name() != args.pod_name:
            continue
        if args.with_container:
            containers = pod.get_containers()
            for i in xrange( len(containers) ):
                container = containers[i]
                if i == 0:
                    x.add_row( [ TextColor.green( t ) for t in [ pod.get_name(), container.get_name(), container.get_status() ] ] )
                else:
                    x.add_row( [ "", container.get_name(), container.get_status() ] )
        else:
            x.add_row( [pod.get_name(), pod.get_pod_ip(), pod.get_node_name(), pod.get_host_ip(), pod.get_status() ] )

    print x

def parse_args():
    parser = argparse.ArgumentParser( description = "kubernetes enhance tools" )
    subparsers = parser.add_subparsers( help = "sub commands" )
    get_parser = subparsers.add_parser( "get", help = "get kubernetes resource" )
    get_subparsers = get_parser.add_subparsers( help = "sub commands" )
    get_pod_parser = get_subparsers.add_parser( "pod", help = "get pod")
    get_pod_parser.add_argument( "--namespace", "-n", help = "the kubernetes namespace", default = "default" )
    get_pod_parser.add_argument( "--with-container", action = "store_true", help = "list pod with container information" )
    get_pod_parser.add_argument( "pod_name", nargs = "?", help = "the pod name" )
    get_pod_parser.set_defaults( func = get_pod )
    return parser.parse_args()


def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
