#!/usr/bin/python

import urllib2
import argparse
import time
import threading
import traceback
import sys
import logging
import logging.handlers

logger = logging.getLogger( "benchmark" )
class RequestManager:
    def __init__( self, total ):
        self.total = total
        self._lock = threading.Lock()
        self.finished = 0
        self._failed = 0
        self._success = 0
        self._print_num = self._get_print_num()
        self._success_status = {}
        self._failed_status = {}


    def success( self, millis ):
        with self._lock:
            self._success += 1
            if millis not in self._success_status:
                self._success_status[ millis ] = 0
            self._success_status[ millis ] += 1

    def failed( self, millis ):
        with self._lock:
            self._failed += 1
            if millis not in self._failed_status:
                self._failed_status[ millis ] = 0
            self._failed_status[ millis ] += 1


    def nextRequest( self ):
        with self._lock:
            if self.finished >= self.total:
                return False, False, 0
            else:
               self.finished += 1
               return True, self.finished % self._print_num == 0 if self._print_num > 0 else False, self.finished

    def print_summary( self, total_time ):
        for n in self._success_status:
            print "%%%.2f in %d ms" % ( self._success_status[n] * 100.0 / self.total, n )
        print "success=%d, failed=%d, total time=%.2fs" % ( self._success, self._failed, total_time )

    def _get_print_num( self ):
        possible_nums = ( 1000, 100, 10 )
        for n in possible_nums:
            if self.total >= 5 * n:
                return n
        return 0

def parse_args():
    parser = argparse.ArgumentParser( description = "http request like apache bench tool" )
    parser.add_argument( "-H", help = "headers", nargs = "+", required = False )
    parser.add_argument( "-c", help = "concurrency requests, default 1", default = 1, type = int )
    parser.add_argument( "-n", help = "amount of requests, default 100", default = 100, type = int )
    parser.add_argument( "-d", "--data", help = "the data to be sent", required = False )
    parser.add_argument( "--log-file", help = "the log file", required = False )
    parser.add_argument( "url", help = "the url" )
    return parser.parse_args()


def do_request( req_mgr, url, headers, data ):
    while True:
        ok, print_info, num = req_mgr.nextRequest()
        if not ok: break
        start = time.time()
        try:
            req = urllib2.Request( url, data = data )
            for header in headers: req.add_header( header, headers[header] )
            resp = urllib2.urlopen( req )
            total = int( (time.time() - start ) * 1000 )
            if resp.getcode() / 100 == 2:
               req_mgr.success( total )
            else:
                req_mgr.failed( total )
        except Exception as ex:
            traceback.print_exc(file=logger)
            total = int( (time.time() - start ) * 1000 )
            req_mgr.failed( total )

        if print_info:
            print "request finished %d" % num

def parseHeaders( headers ):
    r = {}
    if headers is None: return r
    for header in headers:
        pos = header.find( ':' )
        if pos == -1:
            print "Invalid header %s" % header
        else:
            r[ header[0:pos] ] = header[pos+1].strip()
    return r

def loadData( data ):
    if data is not None and data.startswith( "@" ):
        with open( data[1:] ) as fp:
            return fp.read()
    else:
        return data

def init_logger( log_file ):
    if log_file is None:
        handler = loggging.StreamHandler( sys.stdout )
    else:
        handler = logging.handlers.RotatingFileHandler( log_file, maxBytes = 50 * 1024 * 1024, backupCount = 5 )
    handler.setLevel( logging.DEBUG )
    handler.setFormat( logging.Formatter( '%(asctime)s %(name)s - %(message)s' ) )
    logger.addHandler( handler )
def main():
    args = parse_args()
    req_mgr = RequestManager( args.n )
    threads = []
    headers = parseHeaders( args.H )
    data = loadData( args.data )
    start = time.time()
    for i in xrange( args.c ):
        th = threading.Thread( target = do_request, args = ( req_mgr, args.url, headers, data ) )
        th.start()
        threads.append( th )

    for th in threads:
        th.join()
    req_mgr.print_summary( time.time() - start )
if __name__ == "__main__":
    main()
