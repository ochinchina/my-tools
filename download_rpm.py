#!/usr/bin/python

import argparse
import functools
import os
import requests
import xml.etree.ElementTree as ET
import bz2
import zlib
import shutil

class RpmRepository:
    def __init__( self, baseurl = None ):
        self._packages = {}
        self.set_baseurl( baseurl )

    def set_baseurl( self, baseurl ):
        self._baseurl = baseurl
        if self._baseurl:
            self._download_repomd()

    def _download_repomd( self ):
        r = requests.get( "%s/repodata/repomd.xml" % self._baseurl )
        root = ET.fromstring( r.text )
        for item in root.findall( "{http://linux.duke.edu/metadata/repo}data" ):
            print "download %s" % item.attrib['type']
            loc = item.find( "{http://linux.duke.edu/metadata/repo}location").attrib['href']
            filename, content = self._download_package_desc_file( loc )
            if content and filename.endswith( ".xml" ):
                self._parse_package_desc( content )

    def _download_package_desc_file( self, loc ):
        if not self._is_xml_file( loc ):
            return (None,None)
        r = requests.get( "%s/%s" % (self._baseurl, loc ) )
        if loc.endswith( ".xml" ):
            return (loc, r.text )
        elif loc.endswith( ".bz2" ):
            filename = loc[0:-4]
            return (filename, bz2.decompress( r.content ))
        elif loc.endswith( ".gz" ):
            filename = loc[0:-3]
            return (filename, zlib.decompress( r.content, zlib.MAX_WBITS | 16 ) )
        return (None ,None)

    def _is_xml_file( self, loc ):
        """
        check if the rpm package description file is an xml file or not

        Args:
            loc - the package description file related to the baseurl
        Return:
            true - if the description file is an xml or compressed xml file
        """
        possible_suffix = [".xml", ".xml.gz", ".xml.bz2"]
        for suffix in possible_suffix:
            if loc.endswith( suffix ):
                return True
        return False

    def _parse_package_desc( self, content ):
        """
        parse the rpm package description file
        """
        root = ET.fromstring( content )
        for pkg in root.findall( "{http://linux.duke.edu/metadata/common}package"):
            name = pkg.find( "{http://linux.duke.edu/metadata/common}name").text
            version = pkg.find( "{http://linux.duke.edu/metadata/common}version").attrib['ver']
            loc = pkg.find( "{http://linux.duke.edu/metadata/common}location").attrib['href']
            if name not in self._packages:
                self._packages[name]={}
            self._packages[name][version]=loc

    def list_packages( self ):
        for pkg in self._packages:
            versions = []
            for version in self._packages[pkg]:
                versions.append( version )
            print "%s:%s" % (pkg, ",".join(versions) )

    def download_version( self, package, version = None ):
        if not version:
            version = self.get_latest_version( package )[0]
        loc = self._packages[package][version]
        print "download package %s" % os.path.basename( loc )
        r = requests.get( '%s/%s' % (self._baseurl, loc ), stream=True )
        if r.status_code / 100 == 2:
            with open( os.path.basename( loc ), "wb" ) as fp:
                shutil.copyfileobj( r.raw, fp )

    def get_latest_version( self, package ):
        latest_version = None
        if package in self._packages:
            for version in self._packages[package]:
                if latest_version is None or latest_version  < version:
                    latest_version = version
            return (latest_version, self._packages[package][latest_version])
        return None


def list_packages( args, repo ):
    repo.list_packages()

def download_package( args, repo ):
    repo.download_version( args.package, args.version )

def parseArgs( repo ):
    parser = argparse.ArgumentParser( description="rpm tool")
    subparsers = parser.add_subparsers(help="rpm tool")
    parser.add_argument( "--baseurl", required = True, help="the RPM repository base url")
    list_package_parser = subparsers.add_parser( "list")
    list_package_parser.set_defaults( func = functools.partial( list_packages, repo = repo ) )
    download_package_parser = subparsers.add_parser( "download" )
    download_package_parser.add_argument( "--package", required = True, help = "the package name" )
    download_package_parser.add_argument( "--version", required = False, help = "the package version to download, last version if it is missed")
    download_package_parser.set_defaults( func = functools.partial( download_package, repo = repo ) )
    return parser.parse_args()
def main():
    repo = RpmRepository()
    args = parseArgs( repo )
    repo.set_baseurl( args.baseurl )
    args.func( args )

if __name__ == "__main__":
    main()
