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
import logging.handlers
import argparse
import fileencrypt
import tempfile
import sys

logger = logging.getLogger( "git-http" )

def to_boolean( s ):
    return s.lower() in ( "yes", "y", "t", "true", "1" )

class Git:
    def __init__( self ):
        pass

    def init( self ):
        return subprocess.check_output( ['git', 'init'] )

    def set_user_email( self, email ):
        if os.system( "git config --get user.email" ) != 0:
            logger.info( "set the git user.email" )
            subprocess.check_output( ['git', 'config', '--local', 'user.email', email ] )

    def set_user_name( self, name ):
        if os.system( "git config --get user.name" ) != 0:
            logger.info( "set the git user.name" )
            subprocess.check_output( ['git', 'config', '--local', 'user.name', name] )

    def add( self, filename ):
        return subprocess.check_output( ["git", "add", filename ] )

    def remove( self, filename ):
        logger.info( "try to remove file %s" % filename )
        return subprocess.check_output( ['git', 'rm', filename ] )

    def log( self ):
        return subprocess.check_output( ["git", "log" ] )

    def status( self ):
        return subprocess.check_output( ['git', 'status'])

    def add_modified_files( self ):
        n = 0
        for line in subprocess.check_output( ['git', 'status', '-s'] ).split("\n"):
            fields = line.split()
            if len( fields ) > 0 and fields[0] == 'M':
                filename = " ".join( fields[1:] )
                logger.info( "add the modified file %s to git" % filename )
                n += 1
                self.add( filename )
        return n

    def commit_all_modified( self, msg = None ):
        if self.add_modified_files() > 0:
            return self.commit( msg )

    def commit( self, msg = None ):
        if msg is None:
            msg = "update on %s" % ( time.strftime( '%Y-%m-%d %H:%M:%S', time.localtime() ) )

        logger.info( "commit the files with message:%s" % msg )
        return subprocess.check_output( ['git', 'commit', '-m', msg ] )

    def has_uncommited_files( self ):
        out = subprocess.check_output( ['git', "diff", "--cached"] ).strip()
        return len( out ) > 0

    def get_branches( self ):
        branches = []
        for line in subprocess.check_output( ['git', 'branch', '--no-color']).split("\n"):
            fields = line.split()
            if len( fields ) == 1:
                branches.append( fields[0] )
            elif len( fields ) == 2 and fields[0] == '*':
                branches.append( fields[1] )
        return branches

    def exist_branch( self, branch_name ):
        """
        check if the branch exists or not

         return: true if the branch exist
        """
        return branch_name in self.get_branches()

    def list_branch( slef ):
        """
        list all the branches

        Returns:
            all branches in the git repository in json
        """
        return subprocess.check_output( ["git", "branch" ] )

    def checkout( self, branch, parent = None ):
        if branch in self.get_branches():
            return subprocess.check_output(['git', 'checkout', branch ] )
        if parent is not None:
            logger.info( "create branch %s from %s" % (branch, parent) )
            return subprocess.check_output(['git', 'checkout', '-b', branch, parent ] )
        else:
            logger.info( "create branch %s" % branch )
            return subprocess.check_output(['git', 'checkout', '-b', branch ] )

    def make_tag( self, tag, message = None ):
        if message is not None:
            return subprocess.check_output( ['git', 'tag', tag, '-m', message ] )
        else:
            return subprocess.check_output( ['git', 'tag', tag ] )

    def switch_tag( self, tag, branch = None ):
        if branch is not None:
            return subprocess.check_output( ['git', 'checkout', 'tags/%s' % tag, '-b', branch ] )
        else:
            return subprocess.check_output( ['git', 'checkout', 'tags/%s' % tag ] )

    def list_tag( self ):
        """
        list all the tags
        """
        return subprocess.check_output( ['git', 'tag'] )

    def in_repository( self, filename ):
        """
        check if the file is in the git repository or not
        """
        return len( subprocess.check_output( ['git', 'log', filename] ) ) > 0


class GitHttp:
    def __init__( self, directory, enable_git, encryptor = None ):
        self.directory = os.path.abspath( directory )
        self.git = Git()
        self.encryptor = encryptor
        if not os.path.exists( self.directory ):
            os.makedirs(self.directory)
        os.chdir( self.directory )
        self._encrypt_files()

        # init repository if it is not initialized
        if enable_git and not self.__is_git():
            logger.info( "initialize the repository under directory %s" % self.directory )
            self.git.init()

        # set the user name & password
        if enable_git and self.__is_git():
            if os.path.exists( ".git/index.lock" ):
                logger.info( "remove the .git/index.lock" )
                os.remove( ".git/index.lock" )

            self.git.set_user_email( 'test@example.com' )
            self.git.set_user_name( 'test' )

        # commit all the modified files
        self.git.commit_all_modified()


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
        return self.git.status()

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
            return self.git.add( request.args['file'] )
        else:
            return "missing parameter file"

    def upload( self):
        """
        upload a file to the git server

        Args:
            Parameters from client:
            - file the file name

        """
        if 'file' not in request.args:
            return "no file name provided", 400

        commit = to_boolean( request.args['commit'] ) if 'commit' in request.args else True

        try:
            filename = os.path.abspath( "%s/%s" % (self.directory, request.args['file'] ) )

            # check if the parent dir exists or not
            if not os.path.exists( os.path.dirname( filename ) ):
                os.makedirs( os.path.dirname( filename ) )

            with open( filename, "wb" ) as fp:
                shutil.copyfileobj( request.stream, fp )

            if self.encryptor is not None:
                self.encryptor.encrypt_file( filename )

            if self.__is_git():
                self.git.add( self._git_filename( filename ) )
                if commit: self.git.commit()

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
            logger.info( "try to remove file %s" % filename )
            commit = to_boolean( request.args['commit'] ) if 'commit' in request.args else True
            if not os.path.exists( filename ):
                return "Not found", 404
            if self.git.in_repository( filename ):
                logging.info( "try to remove file %s in git repository" % filename )
                self.git.remove( self._git_filename( filename ) )
                if commit: self.git.commit()
                return "remove the file successfully"
            elif os.path.isdir( filename ):
                logging.info( "try to remove directory %s" % filename )
                shutil.rmtree( filename )
                return "Success to remove file %s" % filename
            else:
                logging.info( "try to remove file %s" % filename )
                os.remove( filename )
                return "Success to remove file %s" % filename
        except Exception as ex:
            logger.error( "fail to remove the file" )
            return "%s" % ex, 500


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


        if self.encryptor is not None:
            tmp_file = self._create_temp_file()
            self.encryptor.decrypt_file( filename, tmp_file )
            rv = send_file( tmp_file )
            os.remove( tmp_file )
        else:
            rv = send_file( filename )
        return rv

    def make_branch( self ):
        if not self.__is_git():
            return "Not a git repository", 403

        if self.git.exist_branch( request.args['branch'] ):
            return "Branch exists already", 403

        if 'branch' not in request.args:
            return "Parameter branch is not present", 400

        return self.git.checkout( request.args['branch'], request.args['parent'] if 'parent' in request.args else None )

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

        if not self.git.exist_branch( branch ):
            return "Not found", 404

        return self.git.checkout( branch )

    def log( self ):
        return self.git.log()

    def list_branch( self ):
        """
        list all the branches

        Returns:
            all branches in the git repository in json
        """
        return self.git.list_branch()

    def commit( self ):
        """
        make a commit for current modified files

        Args:
            parameters from client:
            - message(optional), the commit message

        Returns:
            the output of command "git commit -m message"
        """
        if not self.__is_git(): return "not a git repository"
        if not self.git.has_uncommited_files(): return "no uncommit files"
        return self.git.commit(request.args['message'] if "message" in request.args else None )

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

        return self.git.make_tag( request.args['tag'], request.args['message'] if 'message' in request.args else None )

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

        return self.git.switch_tag( request.args['tag'],  request.args['branch'] if 'branch' in request.args else None )

    def list_tag( self ):
        """
        list all tags in the git repository

        Returns:
            a list of tags in json
        """
        return self.git.list_tag()

    def __is_git( self ):
        return os.path.exists( os.path.abspath( "%s/%s" % ( self.directory, ".git" ) ) )

    def _git_filename( self, filename ):
        return filename[len( self.directory )+ 1: ] if filename.startswith( self.directory ) else None

    def _encrypt_files( self ):
        if self.encryptor is None: return

        files = []
        os.path.walk( self.directory, lambda arg, dirname, names: files.extend( [ os.path.join( dirname, name) for name in names] ), None )
        for f in files:
            if os.path.isfile( f ) and not f.startswith( "%s/" % os.path.join( self.directory, ".git" ) ):
                logger.info( "encrypt file %s" % f )
                self.encryptor.encrypt_file( f )

    def _create_temp_file( self ):
        f, filename = tempfile.mkstemp()
        os.close( f )
        return filename



def parse_args():
    parser = argparse.ArgumentParser( description = "Git repository Http interface" )
    parser.add_argument( "--dir", help = "directory", required = True )
    parser.add_argument( "--without-git", help = "git flag", action = "store_true", default = False )
    parser.add_argument( "--host", help = "the host/ip to listen", required = False, default = "127.0.0.1" )
    parser.add_argument( "--port", help = "the port to listen", required = False, default = "5000" )
    parser.add_argument( "--aes-key", help = "16 bytes AES key", required = False )
    parser.add_argument( "--aes-file", help = "the file which contains 16 bytes AES key", required = False )
    parser.add_argument( "--logfile", help = "the name of log file", required = False )
    parser.add_argument( "--loglevel", help = "one of following log level:CRITICAL,ERROR,WARNING,INFO,DEBUG", required = False, default = "DEBUG" )
    return parser.parse_args()

def init_logger( loglevel, logfile = None ):
    if logfile is None:
        handler = logging.StreamHandler( stream = sys.stdout )
    else:
        handler = logging.handlers.RotatingFileHandler( logfile, maxBytes=50*1024*1024, backupCount=10)
    handler.setLevel( loglevel )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter( formatter )
    logger.setLevel( loglevel )
    logger.addHandler( handler )

def heartbeat():
    return "OK", 200

def get_aes_key( args ):
    if args.aes_key is not None:
        return args.aes_key

    if args.aes_file is not None and os.path.exists( args.aes_file ):
        with open( args.aes_file ) as fp:
            return fp.read()
    return None
def main():
    args = parse_args()
    if "logfile" in args:
        init_logger( args.loglevel, args.logfile )
    aes_key = get_aes_key( args )
    encryptor = fileencrypt.AESFileEncryptor( aes_key ) if aes_key is not None else None
    git_http = GitHttp( args.dir, not args.without_git, encryptor = encryptor )

    app = Flask(__name__)
    app.add_url_rule( "/heartbeat", "heartbeat", heartbeat, methods = ['GET'] )
    app.add_url_rule( "/list", "list", git_http.list, methods=['GET'])
    app.add_url_rule( "/upload", "upload", git_http.upload, methods = ['POST', 'PUT'])
    app.add_url_rule( "/add", "add", git_http.add, methods = ['POST', 'PUT'])
    app.add_url_rule( "/delete", "delete", git_http.delete, methods=["PUT"] )
    app.add_url_rule( "/status", "status", git_http.status, methods=["GET"] )
    app.add_url_rule( "/download", "download", git_http.download, methods =  ['GET'] )
    app.add_url_rule( "/make_branch", "make_branch", git_http.make_branch, methods = ['PUT'] )
    app.add_url_rule( "/commit", "commit", git_http.commit, methods=["PUT"] )
    app.add_url_rule( "/switch_branch", "switch_branch", git_http.switch_branch, methods=["PUT"])
    app.add_url_rule( "/make_tag", "make_tag", git_http.make_tag, methods=["PUT"] )
    app.add_url_rule( "/list_tag", "list_tag", git_http.list_tag, methods=["GET"] )
    app.add_url_rule( "/switch_tag", "switch_tag", git_http.switch_tag, methods=["PUT"] )
    app.add_url_rule( "/list_branch", "list_branch", git_http.list_branch, methods=["GET"] )
    app.add_url_rule( "/log", "log", git_http.log, methods=["GET"] )
    app.run( host = args.host, port = int(args.port), threaded = True )

if __name__ == "__main__":
    main()
