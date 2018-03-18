#!/usr/bin/python

import argparse
import urllib2
import json

class AppManClient:
    def __init__( self, app_man_url ):
        self.app_man_url = app_man_url

    def list_apps( self ):
        """
        list all application

        Returns:
            array of applications
        """
        f = urllib2.urlopen( '%s/list/app' % self.app_man_url )
        return json.load( f )

    def start_app( self, name ):
        """
        start application
        """
        req = urllib2.Request( '%s/start/app/%s' % (self.app_man_url, name) )
        req.get_method = lambda: 'POST'
        f = urllib2.urlopen( req )
        return f.read()

    def stop_app( self, name ):
        """
        stop application
        """
        req = urllib2.Request( '%s/stop/app/%s' % (self.app_man_url, name) )
        req.get_method = lambda: 'POST'
        f = urllib2.urlopen( req )
        return f.read()

    def restart_app( self, name ):
        """
        restart an application

        Args:
            name - the application name
        """
        req = urllib2.Request( '%s/restart/app/%s' % (self.app_man_url, name) )
        req.get_method = lambda: 'POST'
        f = urllib2.urlopen( req )
        return f.read()

    def list_files( self, name ):
        """
        list application related files

        Args:
            name - the application name

        Returns:
            the array of configuration files
        """
        f = urllib2.urlopen( '%s/list/conf/%s' % ( self.app_man_url, name ) )
        return json.load( f )

    def upload_file( self, app_name, srcfile, destfile ):
        """
        upload a file to the application

        Args:
            app_name - the application name
            srfile - the local file to be loaded
            destfile - the remote file should be uploaded
        """
        with open( srcfile ) as fp:
            data = fp.read()
            f = urllib2.urlopen( '%s/upload/conf/%s/%s' % ( self.app_man_url, app_name, destfile ), data = data )
            return f.read()

        return "fail to open local file %s" % srcfile

    def delete_file( self, app_name, filename ):
        """
        delete a file of application

        Args:
            app_name - the application name
            filename - the remote file of application should be deleted
        """
        req = urllib2.Request( '%s/delete/conf/%s/%s' % ( self.app_man_url, app_name, filename ) )
        req.get_method = lambda: 'PUT'
        f = urllib2.urlopen( req )
        return f.read()

    def download_file( self, app_name, filename ):
        """
        download a file of application

        Args:
            app_name - the application name
            filename - the remote file of application
        """
        f = urllib2.urlopen( '%s/download/conf/%s/%s' % ( self.app_man_url, app_name, filename ) )
        return f.read()

def list_apps( args ):
    client = AppManClient( args.url )
    print client.list_apps()

def start_app( args ):
    client = AppManClient( args.url )
    print client.start_app( args.name )

def stop_app( args ):
    client = AppManClient( args.url )
    print client.stop_app( args.name )

def restart_app( args ):
    client = AppManClient( args.url )
    print client.restart_app( args.name )

def list_files( args ):
    client = AppManClient( args.url )
    files = client.list_files( args.name )
    print "\n".join( files )

def upload_file( args ):
    client = AppManClient( args.url )
    print client.upload_file( args.name, args.localfile, args.destfile )

def download_file( args ):
    client = AppManClient( args.url )
    content = client.download_file( args.name, args.filename )
    filename = args.destfile if args.destfile else os.path.basename( args.filename )
    with open(filename, "wb" ) as fp:
        fp.write( content )

def delete_file( args ):
    client = AppManClient( args.url )
    print client.delete_file( args.name, args.filename )

def parse_args():
    parser = argparse.ArgumentParser( description = "the client of restful application manager" )
    subparsers = parser.add_subparsers( help = "supported commands" )
    list_app_parser = subparsers.add_parser( "list-app", help = "list all the applications" )
    list_app_parser.add_argument( "url", help = "the url of application manager" )
    list_app_parser.set_defaults( func = list_apps )

    start_app_parser = subparsers.add_parser( "start-app", help = "start the application" )
    start_app_parser.add_argument( "url", help = "the url of application manager" )
    start_app_parser.add_argument( "name", help = "the application name" )
    start_app_parser.set_defaults( func = start_app )

    stop_app_parser = subparsers.add_parser( "stop-app", help = "stop the application" )
    stop_app_parser.add_argument( "url", help = "the url of application manager" )
    stop_app_parser.add_argument( "name", help = "the application name" )
    stop_app_parser.set_defaults( func = stop_app )

    restart_app_parser = subparsers.add_parser( "restart-app", help = "restart the application" )
    restart_app_parser.add_argument( "url", help = "the url of application manager" )
    restart_app_parser.add_argument( "name", help = "the application name" )
    restart_app_parser.set_defaults( func = restart_app )

    list_files_parser = subparsers.add_parser( "list-file", help = "list the application configuration files" )
    list_files_parser.add_argument( "url", help = "the url of application manager" )
    list_files_parser.add_argument( "name", help = "the application name" )
    list_files_parser.set_defaults( func = list_files )

    upload_file_parser = subparsers.add_parser( "upload-file", help = "upload the application configuration file" )
    upload_file_parser.add_argument( "url", help = "the url of application manager" )
    upload_file_parser.add_argument( "name", help = "the application name" )
    upload_file_parser.add_argument( "localfile", help = "the local file to be loaded" )
    upload_file_parser.add_argument( "destfile", help = "the remote destination file" )
    upload_file_parser.set_defaults( func = upload_file )

    download_file_parser = subparsers.add_parser( "download-file", help = "download the application configuration file" )
    download_file_parser.add_argument( "url", help = "the url of application manager" )
    download_file_parser.add_argument( "name", help = "the application name" )
    download_file_parser.add_argument( "filename", help = "the name of remote file" )
    download_file_parser.add_argument( "--destfile", help = "the local destination file" )
    download_file_parser.set_defaults( func = download_file )

    delete_file_parser = subparsers.add_parser( "delete-file", help = "delete an application configuration file" )
    delete_file_parser.add_argument( "url", help = "the url of application manager" )
    delete_file_parser.add_argument( "name", help = "the application name" )
    delete_file_parser.add_argument( "filename", help = "the name of remote file" )
    delete_file_parser.set_defaults( func = delete_file )

    args = parser.parse_args()
    args.func( args )

def main():
    parse_args()

if __name__ == "__main__":
    main()
