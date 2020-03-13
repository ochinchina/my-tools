#!/usr/bin/python

import argparse
import json
import os
import subprocess

"""
this script is used to manage the dependency of projects

this script will accept two configuration files:

1) the project configuration file which looks like:

{
    "dest": ".dep-projects",
    "projects": [
        {
          "name": "TEST_PROJECT",
          "repo": "TEST_PROJECT",
          "git": "nls-git.py",
          "postCommands": [
             {
                 "name": "copy scripts",
                 "command": "cp -r nls-common /java"
             },
             {
                 "name": "compile the system",
                 "command": "echo 'this is ok'\necho 'or not ok'"
             }
          ]
        }
    ]
}


2) the project version file which each line containers two words( first one is project name and second word is git tag/commit-id/branch):

TEST_PROJECT      df40b0a645dc1b0efe07e3e337bfa95db5bb3e18

"""

class Git:
    def __init__( self, path ):
        self.path = path
        self.cur_dir = os.getcwd()
        if not os.path.exists( self.path ):
            os.path.makedirs( self.path )

    def __enter__( self ):
        os.chdir( self.path )
        return self

    def __exit__( self, exc_type, exc_value, traceback ):
        os.chdir( self.cur_dir )

    def clone( self, proj ):
        return self._clone_by_nls_git( proj ) or self._clone_by_git( proj ) if self.exist_nls_git() else self._clone_by_git( proj ) or self._clone_by_nls_git( proj )

    def _clone_by_git( self, proj ):
        command = 'git clone ssh://gerrit.ext.net.nokia.com:29418/GSD_SI/SwS/NLS/%s && scp -p -P 29418 gerrit.ext.net.nokia.com:hooks/commit-msg %s/.git/hooks/' % ( proj, proj )
        return os.system( command ) == 0

    def _clone_by_nls_git( self, proj ):
        return os.system( 'nls-git.py clone %s' % proj ) == 0


    def fetch_tags( self ):
        return self._fetch_tags_by_nls_git() or self._fetch_tags_by_git() if self.exist_nls_git() else self._fetch_tags_by_git() or self._fetch_tags_by_nls_git()

    def get_commit_id( self, tag ):
        try:
            return subprocess.check_output( ['git', 'rev-list', '-n', '1', tag] ).strip()
        except Exception as ex:
            print ex
            return None

    def get_head( self ):
        try:
            return subprocess.check_output( ['git', 'rev-parse', 'HEAD'] ).strip()
        except Exception as ex:
            print ex
            return None

    def checkout( self, tag ):
        commitid = self.get_commit_id( tag )
        if commitid is None or len( commitid ) <= 0:
            self.fetch_tags()
            commitid = self.get_commit_id( tag )

        if commitid is None or len( commitid ) <= 0:
           print "Not exist tag %s" % tag
           return False
        elif self.get_head() == commitid:
           print "%s is already checked out" % commitid
           return True
        else:
            print "try to checkout %s" % commitid
            os.system( "git checkout %s" % commitid )
            return self.get_head() == commitid

    def pull( self ):
        return self._pull_by_nls_git() or self._pull_by_git() if self.exist_nls_git() else self._pull_by_git() or self._pull_by_nls_git()

    def _fetch_tags_by_git( self ):
        return os.system( 'git fetch --tags' ) == 0


    def _fetch_tags_by_nls_git( self ):
        return os.system( 'nls-git.py fetch --tags' ) == 0

    def _pull_by_git( self ):
        return os.system( 'git pull --rebase' ) == 0

    def _pull_by_nls_git( self ):
        return os.system( 'nls-git.py pull --rebase' ) == 0

    def exist_nls_git( self ):
        return self.which( 'nls-git.py' ) is not None

    def which( self, command ):
        try:
            return subprocess.check_output( ['which', command] ).strip()
        except Exception as ex:
            return None

class Project:
    def __init__( self, proj_config, parent_dir ):
        self.proj_config = proj_config
        self.parent_dir = parent_dir

    def get_name( self ):
        return self.proj_config[ 'name' ]

    def get_dir( self ):
        return os.path.join( self.parent_dir, self.get_name() )

    def checkout( self, tag ):
        with Git( self.get_dir() ) as git:
            return git.checkout( tag )

    def clone( self ):
        """
        clone the project if it is not cloned
        """
        if not os.path.exists( self.get_dir() ):
            with Git( self.parent_dir ) as git:
                git.clone( self.get_name() )

    def pull( self ):
        with Git( self.get_dir() ) as git:
            git.pull()

    def execute_post_commands( self ):
        if 'postCommands' in self.proj_config:
            for postCmd in self.proj_config['postCommands']:
                print postCmd['name']
                with Git( self.get_dir() ) as git:
                    os.system( postCmd['command'] )



class DepProjects:
    def __init__( self, config ):
        self.config = config if isinstance( config, dict ) else load_config( config )
        self.dest = os.path.abspath( self.config['dest'] if 'dest' in self.config else '.dep-projects' )
        self.projects = [ Project( proj_conf, self.dest ) for proj_conf in self.config['projects'] ]
        create_dir( self.dest )

    def get_dest( self ):
        return self.dest

    def get_projects( self ):
        """
        get all the projects
        """
        return self.projects

    def get_project( self, name ):
        """
        get project by name
        """
        for proj in self.projects:
            if proj.get_name() == name:
                return proj
        return None

    def __iter__( self ):
        return iter( self.projects )

def load_config( config_file ):
    """
    load a json configuration file
    """
    with open( config_file ) as fp:
        return json.load( fp )

def load_project_dep_version( dep_version_file ):
    """
    load the dependency project version information

    Return: a dict with key:project name and value:git tag or commit-id
    """
    proj_version = {}
    with open( dep_version_file ) as fp:
        for line in fp:
            fields = line.split()
            if len( fields ) == 2:
                proj_version[ fields[0] ] = fields[1]
    return proj_version

def parse_args():
    parser = argparse.ArgumentParser( description = "dependency projects management" )
    parser.add_argument( "--dep-projects", help = "the dependency projects configuration in .json format, default is dep-projects.json", default = "dep-projects.json", required = False)
    parser.add_argument( "--dep-version", help = "the dependency project version, default is dep-proj-version", default = "dep-proj-version.conf" )
    subparsers = parser.add_subparsers( help = "sub commands" )
    list_proj_parser = subparsers.add_parser( "list-proj", help = "list all projects" )
    list_proj_parser.set_defaults( func = list_projects )
    proj_dir_parser = subparsers.add_parser( "proj-dir", help = "get the dependency project dir" )
    proj_dir_parser.set_defaults( func = print_project_dir )
    proj_dir_parser.add_argument( "project", help = "the project name" )
    checkout_parser = subparsers.add_parser( "checkout", help = "checkout all projects to dependency version" )
    checkout_parser.add_argument( "project_name", help = "the project name", nargs = "?" )
    checkout_parser.set_defaults( func = checkout_projects )
    return parser.parse_args()

def create_dir( dest ):
    """
    create the directory if it is not created
    """
    if not os.path.exists( dest ):
        os.makedirs( dest )

def list_projects( args ):
    dep_projects = DepProjects( args.dep_projects)
    for proj in dep_projects:
        print( proj.get_name() )

def print_project_dir( args ):
    dep_projects = DepProjects( args.dep_projects)
    for proj in dep_projects:
        if args.project == proj.get_name():
            print proj.get_dir()
            break

def checkout_projects( args ):
    os.environ['PARENT_PROJ_DIR'] = os.getcwd()
    dep_projects = DepProjects( args.dep_projects )
    dep_proj_version = load_project_dep_version( args.dep_version )
    for proj in dep_projects:
        if args.project_name is not None and proj.get_name() != args.project_name:
            break
        proj.clone()
        if proj.get_name() in dep_proj_version:
            succeed_checkout = False
            if proj.checkout( dep_proj_version[ proj.get_name() ] ):
                succeed_checkout = True
            else:
                proj.pull()
                succeed_checkout = proj.checkout( dep_proj_version[ proj.get_name() ] )
            if succeed_checkout: proj.execute_post_commands()

def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
