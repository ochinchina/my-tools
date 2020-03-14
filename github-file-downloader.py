#!/usr/bin/python

import os
import shutil
from bs4 import BeautifulSoup
import sys
import argparse
try:
    import urllib2
    import urlparse
    urlopen = urllib2.urlopen
    urlparse = urlparse.urlparse
except:
    import urllib.request, urllib.error, urllib.parse
    urlopen = urllib.request.urlopen
    urlparse = urllib.parse.urlparse

"""
this tool directly download files from the github under a specific directory
without "git clone"
"""
class GithubFileDownlder:
    def __init__( self, url, output_dir = "." ):
        self.root_url = url
        self.output_dir = output_dir

    def read_file( self, url ):
        """
        read the content of url

        Args:
            url - the url

        Returns:
            contents of the url in string
        """
        return urlopen( url ).read()


    def parse_folder( self, url ):
        """
        parse a folder in the github and return the all children urls

        Args:
            url - the folder url

        Returns:
            a list of children urls
        """
        data = self.read_file( url )
        soup = BeautifulSoup( data, "html.parser" )
        result = []
        for td in soup.find_all( "td", class_="content" ):
            for a in td.find_all( "a" ): result.append( a['href'] )
        return result


    def download_raw_file( self, url ):
        """
        download the url related raw file if url is not a folder

        Args:
            url - the file url

        Returns:
            the url
        """
        raw_file_url = self.get_raw_file_url( url )
        f = urlopen( raw_file_url )
        output_filename = self.get_output_file( url )
        output_dirname = os.path.dirname( output_filename )
        print( "save to %s" % output_filename )
        if not os.path.exists( output_dirname ):
            os.makedirs( output_dirname )
        with open( output_filename, "wb" ) as fp:
            shutil.copyfileobj( f, fp )

    def get_raw_file_url( self, url ):
        """
        data = self.read_file( url )
        soup = BeautifulSoup( data, "html.parser" )
        result = []

        for a in soup.find_all( "a", id="raw-url" ):
            result.append( a['href'] )

        if len( result ) == 1:
            return "https://github.com%s" % result[0]
        else:
            return ""
        """
        if self.is_raw_file( url ):
            return url

        r = [ p for p in self.get_url_path( url ).split( "/" ) if len( p ) > 0 ]
        if r[2] == 'blob':
            r.pop( 2 )
            return os.path.join( "https://raw.githubusercontent.com/", *r )
        else: return ""

    def get_output_file( self, file_url ):
        file_path = self.get_url_path(  file_url ).split( "/" )
        root_path = self.get_url_path( self.root_url ).split( "/" )

        return os.path.join( self.output_dir, *file_path[ len(root_path):] ) if file_path != root_path else os.path.join( self.output_dir, file_path[-1] )

    def get_url_path( self, url ):
        """
        get the path of the url
        """
        r = urlparse( url )
        return r.path

    def is_folder( self, url ):
        """
        check if the url is a folder url

        Args:
            url - the to be checked url

        Returns:
            true if the url is a folder url
        """
        path = self.get_url_path( url )
        path = [ p for p in path.split('/') if len( p ) > 0 ]
        return len( path ) <= 2 or path[2] == 'tree'

    def is_raw_file( self, url ):
        r = urlparse( url )
        return r.hostname == "raw.githubusercontent.com"

    def download( self ):
        """
        download all the files under url passed in the __init__ method
        """
        urls = [ self.root_url ]

        while len( urls ) > 0:
            url = urls.pop()
            if self.is_raw_file( url ):
                self.download_raw_file( url )
            elif self.is_folder( url ):
                for f in self.parse_folder( url ):
                    if f.startswith( "https://" ) or f.startswith( "http://" ):
                        urls.append( f )
                    else: urls.append( "https://github.com%s" % f )
            else:
                self.download_raw_file( url )

def parse_args():
    parser = argparse.ArgumentParser( description = "download file from github" )
    parser.add_argument( "-o", "--output", help = "the output directory", required = False, default="." )
    parser.add_argument( "url", help = "the url in the github website", nargs="+" )
    return parser.parse_args()

def main():
    args = parse_args()
    for url in args.url:
        downloader = GithubFileDownlder( url, args.output )
        downloader.download()

if __name__ == "__main__":
    main()
