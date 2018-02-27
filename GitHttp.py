#!/usr/bin/python

from flask import Flask
from flask import request
from flask import send_file
import os
import json
import shutil
import subprocess
import time
import logging
import argparse

class GitHttp:
    def __init__( self, directory ):
        self.directory = os.path.abspath( directory )
        if not os.path.exists( self.directory ):
            os.makedirs(self.directory)
        os.chdir( self.directory )
        if not self.__is_git():
            print subprocess.check_output( ['git', 'init'] )
        subprocess.check_output( ['git', 'config', '--global', 'user.email', 'test@example.com'])
        subprocess.check_output( ['git', 'config', '--global', 'user.name', 'test'] )


    def list( self):
        if 'dir' in request.args:
            path = os.path.abspath( "%s/%s" % (self.directory, request.args['dir']) )
            if not path.startswith( self.directory ):
                return "Not found", 404
        else:
            path = self.directory  

        # if the path is not exist
        if not os.path.exists( path ):
            return "Not found", 404

        #list the directory and return files with full path
        if os.path.isdir( path ):
            files = []
            for f in os.listdir( path ):
                if f == ".git":
                    continue
                files.append( "%s/%s" % (path, f ) )
        else:
            files = [ path ]


        # return all the files 
        result = []
        for f in files:
            if os.path.isdir( f ):
                result.append( {"dir":f[len(self.directory):]} )
            else:
                result.append( {"file":f[len(self.directory):]})
        return json.dumps( result )

    def status( self ):
        """
        get status of the git repository

        Returns:
            the output of command "git status"
        """
        return subprocess.check_output( ['git', 'status'])

    def add( self ):
        """
        add a file to the git repository

        Args:
            Parameters from client:
            - file the file to be added
        Returns:
            the output of command "git add <filename>"
        """
        if 'file' in request.args:
            return subprocess.check_output( ["git", "add", request.args['file'] ] )
        else:
            return "missing parameter file"

    def save( self):
        """
        save a file to the git server

        Args:
            Parameters from client:
            - file the file name

        """
        if 'file' not in request.args:
            return "no file name provided", 400

        try:
            filename = os.path.abspath( "%s/%s" % (self.directory, request.args['file'] ) )

            # check if the parent dir exists or not
            if not os.path.exists( os.path.dirname( filename ) ):
                os.makedirs( os.path.dirname( filename ) )

            with open( filename, "wb" ) as fp:
                shutil.copyfileobj( request.stream, fp )

            if self.__is_git():
                subprocess.check_output( ['git', 'add', filename ] )

            return "save file successfully"
        except Exception as ex:
            return "Fail to save file", 500

    def delete( self ):
        """
        delete a file from the git repository

        Args:
            Parameters from the client:
            - file the file name
        """
        try:
            filename = os.path.abspath( "%s/%s" % (self.directory, request.args['file'] ) )
            filename = filename[len( self.directory)+1:]
            if not os.path.exists( filename ):
                return "Not found", 404
            if self.__is_file_in_repository( filename ):
                logging.info( "try to remove file %s in git repository" % filename )
                return subprocess.check_output( ['git', 'rm', filename] )
            elif os.path.isdir( filename ):
                logging.info( "try to remove directory %s" % filename )
                os.removedirs( filename )
                return "Success to remove file %s" % filename
            else:
                logging.info( "try to remove file %s" % filename )
                os.remove( filename )
                return "Success to remove file %s" % filename
        except Exception as ex:
            print ex
            return ex, 500


    def download( self):
        if 'file' not in request.args:
            return "no file name provided", 400


        if 'label' in request.args and self.__is_git():
            return subprocess.check_output( ['git', 'show', '%s:%s' % (request.args['label'], request.args['file'] ) ] ), 

        filename = os.path.abspath( "%s/%s" % (self.directory, request.args['file'] ))

        if not os.path.exists( filename ):
            return "Not found", 404

        if os.path.isdir( filename ):
            return "Not a file", 400

        return send_file( filename)

    def make_branch( self ):
        if not self.__is_git():
            return "Not a git repository", 403

        if self.__is_branch_exist( request.args['branch'] ):
            return "Branch exists already", 403

        if 'branch' not in request.args:
            return "Parameter branch is not present", 400

        if 'parent' in request.args:
            return subprocess.check_output(['git', 'checkout', '-b', request.args['branch'], request.args['parent'] ] )
        else:
            return subprocess.check_output(['git', 'checkout', '-b', request.args['branch'] ] )

    def switch_branch( self ):
        """
        change to the branch

        Args:
            parameters from client:
            - branch, the branch to swith
        """
        if 'branch' not in request.args:
            return "Parameter branch is not present", 400

        branch = request.args['branch']

        if not self.__is_branch_exist( branch ):
            return "Not found", 404

        return subprocess.check_output( ["git", "checkout", branch] )

    def log( self ):
        return subprocess.check_output( ["git", "log" ] )

    def list_branch( slef ):
        """
        list all the branches

        Returns:
            all branches in the git repository in json
        """
        return subprocess.check_output( ["git", "branch" ] )

    def commit( self ):
        """
        make a commit for current modified files

        Args:
            parameters from client:
            - message(optional), the commit message

        Returns:
            the output of command "git commit -m message"
        """
        if "message" in request.args:
            message = request.args['message']
        else:
            message = "update on %s" % ( time.strftime( '%Y-%m-%d %H:%M:%S', time.localtime() ) )

        return subprocess.check_output( ['git', 'commit', '-m', message] )

    def make_tag( self ):
        """
        make a tag on current branch

        Args:
            parameters from client:
            - tag, the tag
            - message(optional), the message for the tag

        Returns:
            the output of "git tag -m message" command
        """
        if "tag" not in request.args:
            return "Parameter tag is not present", 400

        if "message" in request.args:
            return subprocess.check_output( ['git', 'tag', request.args['tag'], '-m', request.args['message'] ] )
        else:
            return subprocess.check_output( ['git', 'tag', request.args['tag'] ] )

    def switch_tag( self ):
        """
        switch to the specified tag

        Args:
            the parameters from client:
            - tag (mandatory), the tag to switch
            - branch(optional), create a branch based on the tag and swith to the branch

        Return:
            the output of "git tags/tag [-b branch]" command
        """
        if 'tag' not in request.args:
            return "Parameter tag is not present", 400

        if 'branch' in request.args:
            return subprocess.check_output( ['git', 'tags/%s' % request.args['tag'], '-b', request.args['branch'] ] )
        else:
            return subprocess.check_output( ['git', 'tags/%s' % request.args['tag'] ] )

    def list_tag( self ):
        """
        list all tags in the git repository

        Returns:
            a list of tags in json
        """
        return subprocess.check_output( ['git', 'tag'] )

    def __is_git( self ):
        return os.path.exists( os.path.abspath( "%s/%s" % ( self.directory, ".git" ) ) )

    def __is_file_in_repository( self, filename ):
        """
        check if the file is in the git repository or not
        """
        return len( subprocess.check_output( ['git', 'log', filename] ) ) > 0

    def __is_branch_exist( self, branch_name ):
        """
        check if a branch exists or not
        """
        branches = subprocess.check_output( ['git', 'branch', '--no-color'] )
        for branch in branches.split('\n'):
            words = branch.split()
            if len( words ) == 1:
                branch = words[0]
            elif len(words) > 1:
                branch = words[1]
            else:
                branch = ""

            if branch == branch_name:
                return True
        return False


def parse_args():
    parser = argparse.ArgumentParser( description = "Git repository Http interface" )
    parser.add_argument( "--git-dir", help = "git directory", required = True )
    parser.add_argument( "--host", help = "the host/ip to listen", required = False, default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the port to listen", required = False, default = "5000" )
    parser.add_argument( "--logfile", help = "the name of log file", required = False )
    parser.add_argument( "--loglevel", help = "one of following log level:CRITICAL,ERROR,WARNING,INFO,DEBUG", required = False, default = "DEBUG" )
    return parser.parse_args()

def init_logger( logfile, loglevel ):
    logging.basicConfig(filename=logfile,level=loglevel)
def main():
    args = parse_args()
    if "logfile" in args:
        init_logger( args.logfile, args.loglevel )
    git_http = GitHttp( args.git_dir )

    app = Flask(__name__)
    app.add_url_rule( "/list", "list", git_http.list, methods=['GET'])
    app.add_url_rule( "/save", "save", git_http.save, methods = ['POST', 'PUT'])
    app.add_url_rule( "/add", "add", git_http.add, methods = ['POST', 'PUT'])
    app.add_url_rule( "/delete", "delete", git_http.delete, methods=["PUT"] )
    app.add_url_rule( "/status", "status", git_http.status, methods=["GET"] )
    app.add_url_rule( "/download", "download", git_http.download, methods =  ['GET'] )
    app.add_url_rule( "/make_branch", "make_branch", git_http.make_branch, methods = ['PUT'] )
    app.add_url_rule( "/commit", "commit", git_http.commit, methods=["PUT"] )
    app.add_url_rule( "/switch_branch", "switch_branch", git_http.switch_branch, methods=["PUT"])
    app.add_url_rule( "/make_tag", "make_tag", git_http.make_tag, methods=["PUT"] )
    app.add_url_rule( "/list_tag", "list_tag", git_http.list_tag, methods=["GET"] )
    app.add_url_rule( "/list_branch", "list_branch", git_http.list_branch, methods=["GET"] )
    app.add_url_rule( "/log", "log", git_http.log, methods=["GET"] )
    app.run( host = args.host, port = int(args.port) )

if __name__ == "__main__":
    main()
