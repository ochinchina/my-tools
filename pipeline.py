#!/usr/bin/python

import argparse
import os
import random
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

class Logger:
    def __init__( self, fileName ):
        self.log = open( fileName, "wb" ) if fileName is not None else None
    def write( self, data ):
        if self.log is not None: self.log.write( data )
        sys.stdout.write( data )

class Step:
    def __init__( self, global_settings, step_config, network, log = sys.stdout ):
        self.global_settings = global_settings
        self.step_config = step_config
        self.network = network
        self.log = log

    def execute( self, extra_vars, dry_run = False ):
        """
        execute the step

        Args:
            extra_vars: extra variables in dict

        Return:
            0, succeed to execute the step
            non-zero, fail to execute the step
        """
        command = DockerCommandBuilder( self, self.network ).build()
        if dry_run:
            self.log.write( "%s\n" % " ".join( command ) )
            return 0
        if not self._should_run( extra_vars ):
            if 'name' in self.step_config:
                self.log.write( TextColor.yellow( 'Ignore %s\n' % self.step_config['name'] ) )
            return 0
        if 'name' in self.step_config:
            self.log.write( TextColor.green( "Execute:%s\n" % self.step_config['name'] ) )
        p = subprocess.Popen( command, stdout = subprocess.PIPE, stderr = subprocess.STDOUT )
        while True:
            if p.poll() is not None: return p.returncode
            line = p.stdout.readline()
            self.log.write( line )

    def get_name( self ):
        return self.step_config['name'] if 'name' in self.step_config else None

    def get_network_alias( self ):
        return ""

    def get_image( self ):
        return self.step_config["image"] if "image" in self.step_config else self.global_settings.get_image()

    def in_background( self ):
        return self.step_config['background'] if 'background' in self.step_config else False

    def is_service( self ):
        return False

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


class Service( Step ):
    def __init__( self, global_settings, service_config, network, log = sys.stdout ):
        Step.__init__( self, global_settings, service_config, network, log )
        self.service_config = service_config
        self.container_id = None
        self._create_random_service_name()

    def start( self ):
        cmd = DockerCommandBuilder( self, self.network ).build()
        name = self.service_config['name'] if 'name' in self.service_config else ""
        self.log.write( "%s\n" % TextColor.green( "Start service:%s" % name ) )
        
        try:
            self.container_id = subprocess.check_output( cmd ).strip()
            return True
        except Exception as ex:
            self.log.write( "%s\n" % TextColor.red( "Fail to start service %s with exception:\n%s" % (self.get_name(), ex ) ) )
        return False

    def stop( self ):
        """
        stop the service
        """
        name = self.service_config['name'] if 'name' in self.service_config else ""
        self.log.write( "%s\n" % TextColor.green( "Stop service:%s" % name ) )
        if self.container_id is not None:
            try:
                subprocess.check_output( ["docker", "stop", self.container_id] )
                subprocess.check_output( ["docker", "rm", self.container_id] )
            except:
                pass

    def get_name( self ):
        return self.name

    def get_network_alias( self ):
        return self.service_config['name'] if 'name' in self.service_config else ""

    def in_background( self ):
        return True

    def is_service( self ):
        return True

    def _create_random_service_name( self ):
        self.name = self.service_config['name'] if 'name' in self.service_config else ""
        self.name = "%s-%d" % (self.name, random.randrange(100000, 999999 ) )

class Network:
    def __init__( self, name = None, log = sys.stdout ):
        self.name = name
        self.log = log

    def start( self ):
        """
        start the docker network

        Return: the started network name
        """

        while True:
            if self.name is None:
                self.name = self._create_network_name()
            try:
                subprocess.check_output( ["docker", "network", "create", self.name ] )
                if self._exist_network( self.name ):
                    self.log.write( "%s\n" % TextColor.green( "Succeed to start network:%s" % self.name ) )
                    return self.name
                else:
                    self.name = self._create_network_name()
            except:
                pass

    def destroy( self ):
        """
        destroy the network
        """
        try:
            subprocess.check_output( ["docker", "network", "rm", self.name] )
            self.log.write( "%s\n" % TextColor.green( "Successd to stop network:%s" % self.name ) )
        except:
            self.log.write( "%s\n" % TextColor.red( "Fail to stop network:%s" % self.name ) )

    def get_name( self ):
        """
        get the network name
        """
        return self.name

    def _list_networks( self ):
        """
        list all the networks in the local system
        """
        out = subprocess.check_output( ["docker", "network", "ls" ] )
        index = 0
        networks = []
        for line in out.split("\n" ):
            index += 1
            if index == 1: continue
            fields = line.split()
            if len( fields ) == 4:
                networks.append( {"id": fields[0], "name": fields[1], "driver": fields[2], "scope": fields[3] } )
        return networks

    def _exist_network( self, name ):
        """
        check if the network exists or not
        """
        for network in self._list_networks():
            if name == network['name']:
                return True
        return False

    def _create_network_name( self ):
        """
        create a network name
        """
        while True:
            name = "%s-%d" % ( os.path.basename( os.getcwd() ), random.randrange( 10000, 99999 ) )
            if not self._exist_network( name ):
                return name

class DockerCommandBuilder:
    def __init__( self, step, network ):
        self.step = step
        self.network = network

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
        self._add_network( command )
        self._add_network_alias( command )

        if self.step.is_service():
            command.extend( ["--name", self.step.get_name() ] )
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

    def _add_network( self, command ):
        if self.network:
            command.extend( ["--net", self.network.get_name() ] )

    def _add_network_alias( self, command ):
        """
        add network alias
        """
        alias = self.step.get_network_alias()
        if len( alias ) > 0:
            command.extend( ["--network-alias", alias ] ) 

class CommandParser:
    def __init__( self, command ):
        self.command = command

    def parse( self ):
        n = len( self.command )
        start = 0
        i = start + 1
        result = []
        while i < n:
            if self.command[ i ] == '\\': #escape char
                if i + 2 < n:
                    i += 2
                else:
                    return []
            elif self.command[start] == '\'' or self.command[start] == '"':
                if self.command[i] == self.command[start]:
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

def start_network( config, log ):
    network = Network( log = log ) if 'services' in config else None
    if network is not None: network.start()
    return network

def start_services( config, global_settings, network, log ):
    """
    start all the configured services

    Return:
        a tuple, first element is the started servies list, and second
    element is a boolean to indicate if all the services are started successfully
    """
    services = []
    if 'services' not in config:
        return

    for service_conf in config['services']:
        service = Service( global_settings, service_conf, network, log )
        if service.start():
            services.append( service )
        else:
            break

    return services, len( services ) == len( config['services'] )

def stop_services( services ):
    for service in services:
        service.stop()

def execute_steps( config, global_settings, network, extra_vars, log, dry_run ):
    if 'steps' not in config:
        return

    for step_conf in config['steps']:
        step = Step( global_settings, step_conf, network, log )
        if step.execute( extra_vars, dry_run ) != 0:
            if 'name' in step_conf:
                log.write( TextColor.red( "Fail to execute step: %s\n" % step_conf['name'] ) )
            break

def main():
    args = parse_args()
    config = load_config( args.config )
    global_settings = GlobalSettings(config['global'] if 'global' in config else {})
    extra_vars = parse_extra_vars( args.extra_vars )
    log = Logger( args.log_file )
    network = start_network( config, log = log )
    services, success = start_services( config, global_settings, network, log )
    if success:
        execute_steps( config, global_settings, network, extra_vars, log, args.dry_run )
    stop_services( services )
    if network is not None: network.destroy()


if __name__ == "__main__":
    main()
