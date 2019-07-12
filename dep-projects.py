#!/usr/bin/python

import argparse
import json
import os

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
                 "command": "cp -r nls-common $PARENT_PROJ_DIR/java"
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

class Project:
    def __init__( self, proj_config, parent_dir ):
        self.proj_config = proj_config
        self.parent_dir = parent_dir

    def get_name( self ):
        return self.proj_config[ 'name' ]

    def get_repo( self ):
        return self.proj_config['repo']

    def get_dir( self ):
        return os.path.join( self.parent_dir, self.get_name() )

    def get_git_command( self ):
        return self.proj_config['git'] if 'git' in self.proj_config else 'git'

    def checkout( self, tag ):
        os.chdir( self.get_dir() )
        os.system( "git checkout %s" % tag )

    def clone( self ):
        """
        clone the project if it is not cloned
        """
        if not os.path.exists( self.get_dir() ):
            os.chdir( self.parent_dir )
            os.system( "%s clone %s" % ( self.get_git_command(), self.get_repo() ) )

    def pull( self ):
        os.chdir( self.get_dir() )
        os.system( "%s pull --rebase" % self.get_git_command() )

    def execute_post_commands( self ):
        if 'postCommands' in self.proj_config:
            for postCmd in self.proj_config['postCommands']:
                print postCmd['name']
                os.chdir( self.get_dir() )
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
    parser = argparse.ArgumentParser( description = "checkout dependency projects" )
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
            proj.checkout( dep_proj_version[ proj.get_name() ] )
            proj.execute_post_commands()

def main():
    args = parse_args()
    args.func( args )

if __name__ == "__main__":
    main()
