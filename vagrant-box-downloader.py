#!/usr/bin/python

import json
import os
import requests
import argparse
import subprocess

def which( command ):
    try:
        return subprocess.check_output( ['which', command ] ).strip()
    except Exception as ex:
        print ex
        return None

class Box:
    def __init__( self, name ):
        self.name = name
        self.metadata = self._load_metadata()

    def list_versions( self ):
        return ( item['version'] for item in self.metadata['versions'] )

    def list_providers( self, version ):
        for item in self.metadata['versions']:
            if item['version'] == version:
                return [ provider['name'] for provider in item['providers'] ]
        return None

    def get_download_link( self, version, provider_name ):
        for item in self.metadata['versions']:
            if item['version'] == version:
                for provider in item['providers']:
                    if provider['name'] == provider_name:
                        return provider['url']
        return None

    def download( self, version, provider_name, directory = "." ):
        url = self.get_download_link( version, provider_name )
        if url is not None:
            filename = self._get_save_filename( version, provider_name, directory )
            print "download box %s to file %s" % ( url, filename )
            wget = which( "wget" )
            if wget is not None:
                print "download with wget"
                os.system( "%s %s -O %s" % ( wget, url, filename ) )
            else:
                r = requests.get( url, stream =True)
                r.raise_for_status()
                with open( filename, "wb" ) as fp:
                    for chunk in r.iter_content(chunk_size=8192):
                        fp.write( chunk )

    def _get_save_filename( self, version, provider_name, directory = "." ):
        fields = self.name.split( '/' )
        return os.path.join( directory, "%s-%s-%s-%s.box" % ( fields[0], fields[1], version, provider_name ) )

    def _load_metadata( self ):
        try:
            url = self._get_meta_url()
            resp = requests.get( url )
            return json.loads( resp.text )
        except Exception as ex:
            print ex

    def _get_meta_url( self ):
        fields = self.name.split( '/' )
        if len( fields ) != 2:
            return None
        return "https://app.vagrantup.com/%s/boxes/%s" % ( fields[0], fields[1] )

def list_box( args ):
    box = Box( args.box )
    for version in box.list_versions():
        for provider in box.list_providers( version ):
            print "%s   %s" % ( version, ",".join( box.list_providers( version ) ) )

def download_box( args ):
    box = Box( args.box )
    box.download( args.version, args.provider, args.output )

def parse_args():
    parser = argparse.ArgumentParser( description = "download vagrant box from vagrant cloud" )
    subparsers = parser.add_subparsers( help = "sub commands" )
    list_parser = subparsers.add_parser( "list", help = "list the versions" )
    list_parser.add_argument( "box", help = "the box name, such as centos/7" )
    list_parser.set_defaults( func = list_box )

    download_parser = subparsers.add_parser( "download", help = "download box" )
    download_parser.add_argument( "box", help = "the box name" )
    download_parser.add_argument( "version", help = "the version" )
    download_parser.add_argument( "provider", help = "the provider name")
    download_parser.add_argument( "--output", help = "the output directory", default = "." )
    download_parser.set_defaults( func = download_box )
    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
