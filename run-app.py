#!/usr/bin/python

import argparse
import os
import signal
import sys
import subprocess
import threading
import time
import urllib2
import logging
import BaseHTTPServer
import SocketServer

app_pid = None
graceful_shutdown_signal = None
graceful_shutdown_url = None
graceful_shutdown_script = None
grace_terminate_delay = 0

# init the logger
logger = logging.getLogger( __name__ )
logger.setLevel( logging.DEBUG )
log_handler = logging.StreamHandler( stream = sys.stdout )
log_handler.setFormatter( logging.Formatter( "%(asctime)-15s %(message)s" ) )
logger.addHandler( log_handler )

class ReadyCheckHandler( BaseHTTPServer.BaseHTTPRequestHandler ):
    def do_GET( self ):
        self.send_response( 200 )
        self.send_header("Content-Type", "text" )
        self.end_headers()
        self.wfile.write( "ready" )

def dump_crash_file( binary, crash_file ):
    out = subprocess.check_output( ["gdb", "--batch", "--ex", "thread apply all bt full", binary, crash_file ] )
    with open( "%s.text" % crash_file, "wb" ) as fp:
        fp.write( out )

def find_crash_files( binary, crash_dir = "/var/crash" ):
    result = []
    os.path.walk( crash_dir, lambda arg, dirname, names: result.extend( [ os.path.join( dirname, name ) for name in names if name.find( os.path.basename( binary )
) >= 0 and name.endswith( ".core") ] ), None )
    return result

def remove_crash_files( crash_files ):
    """
    remove the crash files except the last one
    """
    if len( crash_files ) <= 0: return

    crash_files = map( lambda f: ( f, os.path.getmtime( f ) ), crash_files )
    crash_files = sorted( crash_files, key = lambda f: f[1] )
    crash_files = crash_files[0:-1]
    for f in crash_files:
        logger.info( "remove the crash file:%s" % f[0] )
        os.remove( f[0] )


def do_graceful_shutdown( signum, frame ):
    """
    send graceful shutdown signal to process
    """
    if grace_terminate_delay > 0:
        logger.info( "send terminate sinal to application after %d seconds" % grace_terminate_delay )
        timer = threading.Timer( grace_terminate_delay, send_graceful_shutdown_signal )
        timer.start()
    else:
        send_graceful_shutdown_signal()

def send_graceful_shutdown_signal():
    """
    send graceful shutdown signal to process
    """
    logger.info( "send terminate signal to application" )
    if graceful_shutdown_signal is not None and app_pid is not None:
        os.kill( app_pid, graceful_shutdown_signal )
    elif graceful_shutdown_url is not None and app_pid is not None:
        try:
            urllib2.urlopen( graceful_shutdown_url, timeout = 2 )
        except Exception as ex:
            logger.error( "fail to send graceful shutdown signal to url %s with error %s" % ( graceful_shutdown_url, ex ) )
    elif graceful_shutdown_script is not None and app_pid is not None:
        os.system( graceful_shutdown_script )

def wait_program_exit( pid ):
    while True:
        try:
            os.waitpid( pid, 0 )
            break
        except OSError as ose:
            time.sleep( 1 )

def run_program( args ):
    """
    run the application
    """
    global app_pid
    app_pid = os.fork()
    if app_pid == 0:
        params = [os.path.basename( args[0] )]
        params.extend( args[1:] )
        os.execvp( args[0], params )
    else:
        wait_program_exit( app_pid )
        crash_files = find_crash_files( args[0] )
        for crash_file in crash_files:
            dump_crash_file( args[0], crash_file )
        remove_crash_files( crash_files )

def to_signal( signal_name ):
    """
    convert the signal name to the signal

    Args:
        signal_name - the signal name
    Return:
        the signal
    """
    if type( signal_name ) == int: return signal_name
    if signal_name.isdigit(): return int( signal_name )

    for k, v in signal.__dict__.items():
        try:
            if k.startswith( "SIG" ) and k == signal_name:
                return v
        except:
            pass
    return None

def disable_all_signal():
    for i in [x for x in dir(signal) if x.startswith("SIG") and not x.startswith( "SIG_")]:
        try:
            signum = getattr(signal,i)
            if signum != signal.SIGCHLD:
                signal.signal(signum, signal.SIG_IGN)
        except (OSError, RuntimeError) as m: #OSError for Python3, RuntimeError for 2
            pass

def print_help():
    parser = argparse.ArgumentParser( description = "wrapper for start the C++ application")
    parser.add_argument( "--child-grace-signal", help = "child process graceful shutdown signal", required = False )
    parser.add_argument( "--grace-signal", help = "graceful shutdown signal", required = False, default = "SIGTERM")
    parser.add_argument( "--child-grace-url", help = "the graceful shutdown url", required = False )
    parser.add_argument( "--child-grace-script", help = "the graceful shutdown script", required = False )
    parser.add_argument( "--zombie-reap-threads", help = "the number of zombie reap thread", required = False, type = int, default = 2 )
    parser.add_argument( "--ready-check-port", help = "the ready check port number", required = False, type = int)
    parser.add_argument( "--ready-check-addr", help = "the raedy check address", required = False, default = "127.0.0.1" )
    parser.add_argument( "--grace-terminate-delay", help = "the grace terminate delay in seconds", required = False, default = 0 )
    parser.add_argument( "app_with_args", nargs = "+", help = "application with arguments" )
    parser.print_help()
    #ereturn parser.parse_args()

def parse_args():
    args = argparse.Namespace()
    i = 1
    n = len( sys.argv )
    app_with_args = []
    setattr( args, "grace_signal", None )
    setattr( args, "child_grace_signal", None )
    setattr( args, "child_grace_url", None )
    setattr( args, "child_grace_script", None )
    setattr( args, "zombie_reap_threads", 2 )
    setattr( args, "ready_check_port", None )
    setattr( args, "ready_check_addr", "127.0.0.1" )
    setattr( args, "grace_terminate_delay", 0 )
    while i < n:
        if sys.argv[i] == "--grace-signal" and i + 1 < n:
            setattr( args, "grace_signal", sys.argv[i+1] )
            i += 2
        elif sys.argv[i] == "--child-grace-signal" and i + 1 < n:
            setattr( args, "child_grace_signal", sys.argv[i+1] )
            i += 2
        elif sys.argv[i] == "--child-grace-url" and i + 1 < n:
            setattr( args, "child_grace_url", sys.argv[i+1] )
            i += 2
        elif sys.argv[i] == "--child-grace-script" and i + 1 < n:
            setattr( args, "child_grace_script", sys.argv[i+1] )
            i += 2
        elif sys.argv[i] == "--zombie-reap-threads" and i + 1 < n:
            setattr( args, "zombie_reap_threads", int( sys.argv[i+1] ) )
            i += 2
        elif sys.argv[i] == "--ready-check-port" and i + 1 < n:
            setattr( args, "ready_check_port", int( sys.argv[i+1] ) )
            i += 2
        elif sys.argv[i] == "--ready-check-addr" and i + 1 < n:
            setattr( args, "ready_check_addr", sys.argv[i+1] )
            i += 2
        elif sys.argv[i] == "--grace-terminate-delay" and i + 1 < n:
            setattr( args, "grace_terminate_delay", int( sys.argv[i+1] ) )
            i += 2
        elif sys.argv[i] == "-h" or sys.argv[i] == "--help":
            print_help()
            sys.exit(0)
        else:
            app_with_args.append( sys.argv[i] )
            i += 1
    setattr( args, "app_with_args", app_with_args )
    return args

def reap_zombie( index, threads ):
    while True:
        if reap_zombie_once( index, threads ) <= 0:
            time.sleep( 30 )

def wait_zombie_exit( pid, process_name):
    try:
        logger.info( "start to reap the zombie process %s" % process_name )
        os.waitpid( pid, 0)
        logger.info( "succeed to reap the zombie process %s" % process_name )
    except Exception as ex:
        logger.exception( ex )

def reap_zombie_once( index, threads ):
    """
    reap the zombie process

    Args:
        index - the zombie process reaper index
        threads - the total number of zombie reaper threads

    Return:
        the number of reapped  zombie process
    """
    # get the ppid, pid and program name
    out = subprocess.check_output( ['ps', '-eo', 'ppid,pid,comm'])
    reapped_threads = 0
    for line in out.split("\n"):
        fields = line.split()
        # check if it is a zombie process
        if len( fields) == 4 and fields[-1] == "<defunct>":
            ppid = int( fields[0] )
            pid = int( fields[1] )
            # if I'm the parent of the zombie process
            if pid % threads != index or ppid != os.getpid(): continue
            process_name = fields[-2]
            logger.info( "find zombie process %s with pid %d" % ( process_name, pid ) )
            wait_zombie_exit( pid, process_name )
            reapped_threads += 1
    return reapped_threads

def start_http_server( addr, port ):
    """
    start a ready http server
    """
    s = None
    try:
        s = SocketServer.TCPServer((addr, port ), ReadyCheckHandler )
        s.serve_forever()
    except Exception as ex:
        if s is not None: s.server_close()
        print ex

def main():
    args = parse_args()
    print args
    if args.child_grace_signal or args.child_grace_url or args.child_grace_script:
        if not args.grace_signal: setattr( args, "grace_signal", "SIGTERM" )
        disable_all_signal()
        if args.child_grace_signal:
            global graceful_shutdown_signal
            graceful_shutdown_signal = to_signal( args.child_grace_signal )
        elif args.child_grace_url:
            global graceful_shutdown_url
            graceful_shutdown_url = args.child_grace_url
        elif args.child_grace_script:
            global graceful_shutdown_script
            graceful_shutdown_script = args.child_grace_script

    global grace_terminate_delay
    grace_terminate_delay = args.grace_terminate_delay

    if args.grace_signal and (args.child_grace_signal or args.child_grace_url or args.child_grace_script ):
        signal.signal( to_signal( args.grace_signal ), do_graceful_shutdown )

    for i in range( args.zombie_reap_threads ):
        th = threading.Thread( target = reap_zombie, args = ( i,args.zombie_reap_threads ) )
        th.setDaemon( True )
        th.start()

    app_params = args.app_with_args
    if args.ready_check_port:
        logger.debug( "start ready check http server with address %s port %d" % ( args.ready_check_addr, args.ready_check_port ) )
        th = threading.Thread( target = start_http_server, args = ( args.ready_check_addr, args.ready_check_port ) )
        th.setDaemon( True )
        th.start()
    logger.debug( "start program: %s" % ( " ".join( app_params ) ) )
    run_program( app_params )

if __name__ == "__main__":
    main()
