#!/usr/bin/python

import argparse
import os
import subprocess
import sys
import yaml

class TextColor:
    @staticmethod
    def red( text ):
        return '\033[0;31m%s\033[0m' % text

    @staticmethod
    def green( text ):
        return '\033[0;32m%s\033[0m' % text

    @staticmethod
    def yellow( text ):
        return '\033[0;33m%s\033[0m' % text

class GlobalSettings:
    def __init__( self, global_settings ):
        self.global_settings = global_settings

    def get_workspace( self ):
        return self.global_settings["workspace"] if "workspace" in self.global_settings else None

    def get_image( self ):
        return self.global_settings["image"] if "image" in self.global_settings else None

    def get_env( self ):
        return self.global_settings["env"] if "env" in self.global_settings else None

    def get_extra_hosts( self ):
        return self.global_settings["extra_hosts"] if "extra_hosts" in self.global_settings else None

    def get_volumes( self ):
        return self.global_settings["volumes"] if "volumes" in self.global_settings else None

class Step:
    def __init__( self, global_settings, step_config, log = sys.stdout ):
        self.global_settings = global_settings
        self.step_config = step_config
        self.log = log

    def execute( self, extra_vars, dry_run = False ):
        command = DockerCommandBuilder( self ).build()
        if dry_run:
            print( " ".join( command ) )
            return
        if not self._should_run( extra_vars ):
            if 'name' in self.step_config:
                print( TextColor.yellow( 'Ignore %s' % self.step_config['name'] ) )
            return
        if 'name' in self.step_config:
            print( TextColor.green( "Execute:%s" % self.step_config['name'] ) )
        p = subprocess.Popen( command, stdout = subprocess.PIPE, stderr = subprocess.STDOUT )
        while True:
            if p.poll() is not None: break
            line = p.stdout.readline()
            self.log.write( line )
            if self.log != sys.stdout: sys.stdout.write( line )

    def get_image( self ):
        return self.step_config["image"] if "image" in self.step_config else self.global_settings.get_image()

    def in_background( self ):
        return self.step_config['background'] if 'background' in self.step_config else False

    def is_local_action( self ):
        return self.step_config['local_action'] if 'local_action' in self.step_config else False

    def get_extra_hosts( self ):
        extra_hosts = []
        global_extra_hosts = self.global_settings.get_extra_hosts()
        if global_extra_hosts is not None:
            extra_hosts.extend( global_extra_hosts )
        extra_hosts.extend( self.step_config['extra_hosts'] if 'extra_hosts' in self.step_config else [] )

        return extra_hosts if len( extra_hosts ) > 0 else None

    def get_volumes( self ):
        volumes = []
        global_volumes = self.global_settings.get_volumes()
        if global_volumes is not None:
            volumes.extend( global_volumes )
        volumes.extend( self.step_config['volumes'] if 'volumes' in self.step_config else [] )
        return volumes if len( volumes ) > 0 else None

    def get_env( self ):
        env = []
        global_env = self.global_settings.get_env()
        env.extend( global_env if global_env is not None else [] )
        env.extend( self.step_config['env'] if 'env' in self.step_config else [] )
        return env if len( env ) > 0 else None

    def get_exec_command( self ):
        return self.step_config['command'] if 'command' in self.step_config else None

    def get_args( self ):
        return self.step_config['args'] if 'args' in self.step_config else None

    def _should_run( self, extra_vars ):
        if "when" in self.step_config:
            try:
                return eval( self.step_config['when'], extra_vars )
            except:
                return False
        else:
            return True


class DockerCommandBuilder:
    def __init__( self, step ):
        self.step = step

    def build( self ):
        if self.step.is_local_action():
            return self._create_local_command()
        else:
            return self._create_docker_command()

    def _create_local_command( self ):
        command = []
        exec_command = self.step.get_exec_command()

        if exec_command is not None:
            if type( exec_command ) == str:
                command.extend( CommandParser(exec_command).parse( ) )
            else:
                command.extend( exec_command )

        args = self.step.get_args()
        command.extend( args if args is not None else [] )
        return command

    def _create_docker_command( self ):
        command = ["docker", "run"]
        if self.step.in_background():
            command.append( "-d" )
        else:
            command.extend( ["-it", "--rm"] )
        self._add_extra_hosts( command )
        self._add_volumes( command )
        self._add_env( command )
        command.append( self.step.get_image() )
        command.extend( self._create_local_command() )
        return command

    def _add_extra_hosts( self, command ):
        extra_hosts = self.step.get_extra_hosts()
        if extra_hosts is not None:
            for extra_host in extra_hosts:
                command.extend( ["--add-host", extra_host ] )

    def _add_volumes( self, command ):
        volumes = self.step.get_volumes()
        if volumes is not None:
            for vol in volumes:
                index = vol.find( ':' )
                src = vol[0:index]
                dest = vol[index+1:]
                src = os.path.abspath( os.path.expandvars( os.path.expanduser( src ) ) )
                dest = os.path.expandvars( dest )
                command.extend( ["-v", "%s:%s" % (src, dest) ] )

    def _add_env( self, command ):
        env = self.step.get_env()
        if env is not None:
            for e in env:
                command.extend( ["-e", e ] )

class CommandParser:

    def __init__( self, command ):
        self.command = command
        print command

    def parse( self ):
        n = len( self.command )
        start = 0
        i = start + 1
        result = []
        while i < n:
            if self.command[ i ] == '\\': #escape char
                print( "find escape, i = %d" % i )
                if i + 2 < n:
                    i += 2
                else:
                    return []
            elif self.command[start] == '\'' or self.command[start] == '"':
                if self.command[i] == self.command[start]:
                    print( "find match" )
                    result.append( self._remove_escape( self.command[start + 1: i] ).strip() )
                    start = i + 1
                    i = start + 1
                else:
                    i += 1
            elif self.command[i].isspace():
                if self.command[start].isspace():
                    i += 1
                else: # skip space
                    result.append( self._remove_escape( self.command[ start : i ] ).strip() )
                    start = i
                    i = start + 1
            else:
                if self.command[start].isspace():
                    start = i
                    i = start + 1
                else:
                    i += 1

        if start < n: result.append( self._remove_escape( self.command[ start:] ).strip() )
        return result
    def _remove_escape( self, s ):
        r = ""
        i = 0
        n = len( s )
        while i < n:
            if s[i] == '\\' and i + 1 < n:
                r = "%s%s" % ( r, s[i+1])
                i += 2
            else:
                r = "%s%s" % (r, s[i] )
                i += 1
        return r
        



def parse_args():
    parser = argparse.ArgumentParser( description = "docker pipeline tool" )
    parser.add_argument( "-c", "--config", help = "the pipeline .yaml file, default is pipeline.yaml", required = False, default = "pipeline.yaml")
    parser.add_argument( "-e", "--extra-vars", help = "the extra variables in key=value format", required = False )
    parser.add_argument( "--log-file", help = "the log file", default = "pipeline.log", required = False )
    parser.add_argument( "--dry-run", action = "store_true", help = "dry run the command", required = False )
    return parser.parse_args()

def load_config( config_file ):
    with open( config_file ) as fp:
        return yaml.load( fp.read() )

def parse_extra_vars( extra_vars ):
    r = {}
    if extra_vars is None: return r
    for field in extra_vars.split():
        pos = field.find( '=' )
        if pos == -1:
            continue
        key = field[0:pos]
        value = field[pos+1:]
        r[key] = value
    return r

def main():
    args = parse_args()
    config = load_config( args.config )
    global_settings = GlobalSettings(config['global'] if 'global' in config else {})
    f = open( args.log_file, "wb" ) if args.log_file else sys.stdout
    extra_vars = parse_extra_vars( args.extra_vars )
    for step_conf in config['steps']:
        step = Step( global_settings, step_conf, f )
        step.execute( extra_vars, args.dry_run )

if __name__ == "__main__":
    main()
