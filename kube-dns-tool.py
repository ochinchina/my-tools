#!/usr/bin/python

import argparse
import json
import subprocess
import yaml

"""
a tool to operate the kube-dns ConfigMap in the kubernetes.

This tool is designed to the O&M operators to update the kube-dns ConfigMap.
"""

def dump_kube_dns_cm( kube_dns_cm_file = None ):
    """
    dump the kube-dns ConfigMap and parse it as a dict object

    Args:
        kube_dns_cm_file - load the config map from file if this is set, otherwise get the kube-dns
                           ConfigMap with "kubectl get cm kube-dns -n kube-system -o yaml"
    Return:
        a python dict object
    """
    if kube_dns_cm_file is not None:
        with open( kube_dns_cm_file ) as fp:
            return yaml.load( fp )

    out = subprocess.check_output( ['kubectl', 'get', 'cm', 'kube-dns', '-n', 'kube-system', '-o', 'yaml'] )
    return yaml.load( out )

def dump_kube_dns( args ):
    """
    dump the kube-dns configmap and print it
    """
    print subprocess.check_output( ['kubectl', 'get', 'cm', 'kube-dns', '-n', 'kube-system', '-o', 'yaml'] )
 
def list_upstreams( args ):
    """
    list all upstream DNS servers
    """
    kube_dns = dump_kube_dns_cm()
    if 'data' in kube_dns and 'upstreamNameservers' in kube_dns['data']:
        print ",".join( json.loads( kube_dns['data']['upstreamNameservers'] ) )

def update_kube_dns( kube_dns, dry_run ):
    """
    update the kube-dns ConfigMap to the system

    Args:
        kube_dbns - a python dict object in format dumped by the dump_kube_dns_cm() method
        dry_run - print the kube_dns in yaml format but not update to the system if it is True
    """
    removed_metadata_fields = ['resourceVersion', 'selfLink', 'uid', 'creationTimestamp']
    for field in removed_metadata_fields:
        if field in kube_dns['metadata']: del kube_dns['metadata'][field]

    r = yaml.dump( kube_dns, default_flow_style = False )
    if dry_run:
        print r
    else:
        p = subprocess.Popen( ['kubectl', 'apply', '-f', '-' ], stdin = subprocess.PIPE )
        p.communicate( r )

def add_upstreams( args ):
    """
    add some upstream DNS servers
    """
    kube_dns = dump_kube_dns_cm( args.kube_dns_cm_file )
    if 'data' not in kube_dns: kube_dns['data'] = {}
    upstreamServers = json.loads( kube_dns['data']['upstreamNameservers'] ) if 'upstreamNameservers' in kube_dns['data'] else []
    for server in args.upstreamServers:
        if server not in upstreamServers:
            upstreamServers.append( server )

    if len( upstreamServers ) > 0:
        kube_dns['data']['upstreamNameservers'] = json.dumps( upstreamServers )

    update_kube_dns( kube_dns, args.dry_run ) 

def del_upstreams( args ): 
    """
    delete some upstream DNS servers
    """
    kube_dns = dump_kube_dns_cm( args.kube_dns_cm_file )
    if 'data' not in kube_dns or 'upstreamNameservers' not in kube_dns['data']:
        return

    upstreamServers = json.loads( kube_dns['data']['upstreamNameservers'] )
    for server in args.upstreamServers:
        upstreamServers.remove( server )

    if len( upstreamServers ) <= 0:
        del kube_dns['data']['upstreamNameservers']
    else:
        kube_dns['data']['upstreamNameservers'] = json.dumps( upstreamServers )
        update_kube_dns( kube_dns, args.dry_run )

def list_stub_domains( args ):
    """
    list all the stub domain DNS servers
    """
    kube_dns = dump_kube_dns_cm( args.kube_dns_cm_file )
    if 'data' not in kube_dns or 'stubDomains' not in kube_dns['data']:
        return

    stubDomains = json.loads( kube_dns['data']['stubDomains'] )
    for domain in stubDomains:
        print "%s:%s" % (domain, ",".join( stubDomains[domain] ) )
    
def parse_command_line_stub_domain( stubDomain ):
    """
    parse the stubDomain in format "domain:dns-server-1,dns-server-2,...,dns-server-n"

    Args:
        stubDomain - stubdomain in format "domain:dns-server-1,dns-server-2,...,dns-server-n"

    Returns:
        a tuple with two elements:
        - domain name
        - a list of dns-server
    """
    pos = stubDomain.find( ':' )
    return stubDomain[0:pos], stubDomain[pos+1:].split(',') if pos > 0 else None

def add_stub_domains( args ):
    """
    add the stub domains
    """
    stubDomains = {}
    for stubDomain in args.stubDomains:
        domain, dns_servers = parse_command_line_stub_domain( stubDomain ) 
        if domain is None:
            print "stubDomain %s is in invalid format" % stubDomain
            continue
        stubDomains[ domain ] = dns_servers

    if len( stubDomains ) > 0:
        kube_dns = dump_kube_dns_cm( args.kube_dns_cm_file )
        stubDomains.update( json.loads( kube_dns['data']['stubDomains'] ) if 'data' in kube_dns and 'stubDomains' in kube_dns['data'] else {} )
        if 'data' not in kube_dns: kube_dns['data'] = {}
        kube_dns['data']['stubDomains'] = json.dumps( stubDomains )
        update_kube_dns( kube_dns, args.dry_run )

def del_stub_domains( args ):
    """
    delete the stub domains
    """
    kube_dns = dump_kube_dns_cm( args.kube_dns_cm_file )

    # if no stubDomains, nothing to do
    if 'data' not in kube_dns or 'stubDomains' not in kube_dns['data']:
        return None

    # remove the stubDomain by name
    stubDomains = json.loads( kube_dns['data']['stubDomains'] )
    deletedDomains = 0
    for domain in args.stubDomains:
        if domain in stubDomains:
            del stubDomains[ domain ]
            deletedDomains += 1

    # if something is deleted, update the kube-dns
    if deletedDomains > 0:
        if len( stubDomains ) > 0:
            kube_dns['data']['stubDomains'] = json.dumps( stubDomains )
        else:
            del kube_dns['data']['stubDomains']
        update_kube_dns( kube_dns, args.dry_run ) 

def parse_args():
    """
    parse the command line arguments
    """
    parser = argparse.ArgumentParser( description = "nls DNS management tool" )
    subparsers = parser.add_subparsers( help = "sub commands" )

    dump_parser = subparsers.add_parser( "dump", help = "dump the kube-dns ConfigMap for debug purpose" )
    dump_parser.set_defaults( func = dump_kube_dns )

    list_upstream_parser = subparsers.add_parser( "list-upstream", help = "list all upstream dns servers" )
    list_upstream_parser.set_defaults( func = list_upstreams )

    add_upstream_parser = subparsers.add_parser( "add-upstream", help = "add upstream dns servers" )
    add_upstream_parser.add_argument( "upstreamServers", nargs = "+", help = "the upstream DNS servers" )
    add_upstream_parser.add_argument( "--kube-dns-cm-file", help = "the dumped kube-dns configuration file", required = False )
    add_upstream_parser.add_argument( "--dry-run", action = "store_true", help = "dry run it" )
    add_upstream_parser.set_defaults( func = add_upstreams )

    del_upstream_parser = subparsers.add_parser( "del-upstream", help = "delete upstream dns servers" )
    del_upstream_parser.add_argument( "upstreamServers", nargs = "+", help = "the upstream DNS servers" )
    del_upstream_parser.add_argument( "--kube-dns-cm-file", help = "the dumped kube-dns configuration file", required = False )
    del_upstream_parser.add_argument( "--dry-run", action = "store_true", help = "dry run it" )
    del_upstream_parser.set_defaults( func = del_upstreams )

    list_stub_domains_parser = subparsers.add_parser( "list-stub-domains", help = "list all stub-domains DNS servers" )
    list_stub_domains_parser.add_argument( "--kube-dns-cm-file", help = "the dumped kube-dns configuration file", required = False )
    list_stub_domains_parser.set_defaults( func = list_stub_domains )

    add_stub_domains_parser = subparsers.add_parser( "add-stub-domains", help = "add stub-domains DNS servers" )
    add_stub_domains_parser.add_argument( "--kube-dns-cm-file", help = "the dumped kube-dns configuration file", required = False )
    add_stub_domains_parser.add_argument( "--dry-run", action = "store_true", help = "dry run it" )
    add_stub_domains_parser.add_argument( "stubDomains", nargs = "+", help = "stub domain DNS server in format domain:dns-server-1,dns-server-2,...,dns-server-3" )
    add_stub_domains_parser.set_defaults( func = add_stub_domains )

    del_stub_domains_parser = subparsers.add_parser( "del-stub-domains", help = "delete stub-domains DNS servers" )
    del_stub_domains_parser.add_argument( "--kube-dns-cm-file", help = "the dumped kube-dns configuration file", required = False )
    del_stub_domains_parser.add_argument( "--dry-run", action = "store_true", help = "dry run it" )
    del_stub_domains_parser.add_argument( "stubDomains", nargs = "+", help = "name of stub domain" )
    del_stub_domains_parser.set_defaults( func = del_stub_domains )

    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
