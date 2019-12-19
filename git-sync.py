#!/usr/bin/python

import argparse
import subprocess
import logging
import logging.handlers
import os
import time
import sys

logger = logging.getLogger( __name__ )

class GitRemoteRepo:
    def __init__( self, git_dir ):
        self.git_dir = git_dir
        os.chdir( git_dir )

    def add_remote( self, url ):
        if self.exist_remote( url ):
            logger.info( "remote repo %s already exists" % url )
        else:
            name = self._create_remote_repo_name()
            try:
                out = subprocess.check_output( ['git', 'remote', 'add', name, url ] )
                logger.info( "succeed to add remote git repository %s:%s" % ( url, out ) )
            except Exception as ex:
                logger.error( "fail to add remote git repository %s" % url, ex )

    def remove_remote( self, name ):
        """
        remove the remote repo by name
        """
        try:
            out = subprocess.check_output( ['git', 'remote', 'remove', name ] )
            logger.info( "succeed to remote the remote repository %s" % name )
        except Exception as ex:
            logger.error( "fail to remove the git repository %s" % name, ex )

    def remove_remote_url( self, url ):
        """
        remove the remote repo by url
        """
        for remote in self.list_remote():
            if remote[1] == url:
                self.remove_remote( remote[0] )

    def remove_all_remote( self ):
        """
        remove all the remote repository
        """
        try:
            remote_names = self.get_all_remote_repo_name()
            for name in remote_names:
                self.remove_remote( name )
        except Exception as ex:
            logger.error( "fail to remove all the remote repositories", ex )

    def get_all_remote_url( self ):
        """
        get all the remote url
        """
        return set( [ remote[1] for remote in self.list_remote() ] )

    def exist_remote( self, url ):
        """
        check if the repository (represent in url ) exist or not

        return: True if the remote repository exists
        """
        remotes = self.list_remote()
        for remote in remotes:
            if remote == url:
                return True
        return False

    def sync_all_remote( self, branch = 'master' ):
        for remote in self.list_remote():
            self.sync_remote( remote[0], remote[1], branch )


    def sync_remote( self, name, url, branch = 'master' ):
        """
        synchronization with the remote repository

        Args:
            name - the remote repository name
            url - the url of remote repository
        """
        try:
            out = subprocess.check_output( ['git', 'pull', name, branch ] )
            logger.info( "succeed to sync remote git repository %s:%s" % ( url, out ) )
        except Exception as ex:
            logger.error( "fail to add remote git repository %s" % url, ex )

    def _create_remote_repo_name( self):
        remote_names = self.get_all_remote_repo_name()
        i = 1
        while True:
            name = 'repo-%d' % i
            if name not in remote_names:
                return name
            i += 1

    def get_all_remote_repo_name( self ):
        remotes = self.list_remote()
        return set( [ remote[0] for remote in remotes ] )

    def list_remote( self ):
        remotes = []
        try:
            for line in subprcess.check_output( ['git', 'remote', '-v'] ).split("\n" ):
                fields = line.split()
                if len( fields ) > 0:
                    remotes.append( fields )
        except Exception as ex:
            logger.error( "fail to list remote git repositories", ex )

        return remotes

def parse_args():
    parser = argparse.ArgumentParser( description = "synchronize with remote repositories" )
    parser.add_argument( "--git-dir", help = "local git directory", required = True )
    parser.add_argument( "--sync-interval", help = "the git synchronization interval in seconds, default is 60 seconds", default = 60, type = int )
    parser.add_argument( "--remote-repo-script", help = "the script to get remote git repository, one line for one git repository", required = True )
    parser.add_argument( "--log-file", help = "the log file", required = False )
    return parser.parse_args()

def get_remote_repositories( repo_script ):
    try:
        return set( subprocess.check_output( [ repo_script ] ).split() )
    except Exception as ex:
        print ex
    return None

def init_logger( log_file ):
    if log_file is None:
        handler = logging.StreamHandler( stream = sys.stdout )
    else:
        handler = logging.handlers.RotatingFileHandler( log_file, maxBytes = 50 * 1024 *  1024, backupCount = 10 )

    logger.setLevel( logging.DEBUG )
    handler.setFormatter( logging.Formatter( "%(asctime)-15s %(message)s" ) )
    logger.addHandler( handler )

def main():
    args = parse_args()
    init_logger( args.log_file )
    git_repo = GitRemoteRepo( args.git_dir )
    while True:
        remote_repos = get_remote_repositories( args.remote_repo_script )
        if remote_repos is not None:
            exist_remote_repos = git_repo.get_all_remote_url()
            new_remote_urls = remote_repos.difference( exist_remote_repos )
            remove_urls = exist_remote_repos.difference( remote_repos )
            for url in remove_urls: git_repo.remove_remote_url( url )
            for url in new_remote_urls: git_repo.add_remote( url )
            git_repo.sync_all_remote()
        time.sleep( args.sync_interval )

if __name__ == "__main__":
    main()
