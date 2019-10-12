#!/usr/bin/python
import json
import socket
import os
import redis

__init__ = ["RuntimeApi", "Stat" ]
class Csv:
    def __init__( self, content, delimiter = "," ):
        """
        parse the csv format content. If the first line starts with '#', it will be parsed
        as header
        """
        self.header = {}
        self.rows = []

        self._parse( content, delimiter )

    def row_number( self ):
        """
        return number of rows
        """
        return len( self.rows )

    def get( self, row, col ):
        """
        get the cell value by row and col.
        Args:
           row - integer, the row number
           col - integer or name of colum if first line is header

        Return:
           the cell value at (row, col)
        """
        if row < 0 or row >= len( self.rows ):
            return None

        if isinstance( col, str ) or isinstance( col, unicode ):
            col = self.header[ col ] if col in self.header else -1
        if col < 0 or col >= len( self.header ):
            return None
        return self.rows[ row ][ col ]

    def to_dict( self ):
        """
        convert the cells to dict format.

        Returns:
            If header is available, return a list of rows. A row is a dict whose key is
            column name and whose value if cell value

            If header is not available, return a lst of row( in list format)
        """
        if len( self.header ) < 0:
            return self.rows
        else:
            result = []
            for i in xrange( len( self.rows ) ):
                row = {}
                for name in self.header:
                    index = self.header[name]
                    if index < len( self.rows[i] ):
                        row[name] = self.rows[i][index]
                result.append( row )
            return result

    def _parse( self, content, delimiter ):
        first_line = True
        for line in content.split( "\n" ):
            if first_line and line.startswith( '#' ):
                fields = line[1:].split( delimiter )
                for i in xrange( len( fields ) ):
                    name = fields[i].strip()
                    if len( name ) > 0: self.header[ name ] = i
            else:
                fields = line.split( delimiter )
                if len( self.header ) <= 0 or len( fields ) >= len( self.header ):
                    row = {}
                    for i in xrange( len( fields ) ):
                        row[i] = fields[i]
                    self.rows.append( row )
            first_line = False

class Stat:
    def __init__( self, stat ):
        """
        Args:
            stat - a list of server stat (dict)
        """
        self.stat = stat
        self.cookie_index = {}
        self._create_cookie_index()

    def get_backend_server_cookie( self, backend_name, server_name, address):
        """
        get the cookie by address
        """
        server_stat = self.get_server_stat( backend_name, server_name, address )

        return server_stat['cookie'] if server_stat is not None and 'cookie' in server_stat else None

    def get_backend_servers( self, backend_name = None ):
        """
        get all the backend servers in the backend
        """
        return self.find_backend_servers( lambda item: (backend_name is None or item['pxname'] == backend_name) and item['svname'] != 'BACKEND' )

    def get_backend_servers_with_status( self, backend_name, status ):
        """
        get the backend server with status
        """
        servers = self.get_backend_servers( backend_name = backend_name )
        return [ item for item in servers if item['status'] == status ]

    def find_backend_servers( self, filter_func ):
        """
        find all the backend servers by the filter function

        the filter function accepts a server stat item ( a dict ) and return boolean
        to indicate if it should be in return list

        return: list of server stat
        """
        return [ item for item in self.stat if filter_func( item ) ]
    def get_backend_server_stat( self, backend_name, server_name = None, address  = None ):
        """
        get the stat for a specific server by server_name or address
        """
        for item in self.stat:
            if item['pxname'] == backend_name and (item['svname'] == server_name or item['addr'] == address ):
                return item
        return None

    def get_backends( self ):
        """
        get name of all backends

        return: list of backend nam
        """
        return [ item['pxname'] for item in self.stat if item['svname'] == 'BACKEND' ]

    def load_cookie_from_redis( self, redis, hname ):
        return redis.hgetall( hname )

    def save_cookie_to_redis( self, redis, backend, hname ):
        """
        save the cookie to redis

        Args:
            redis - the redis.Redis object
            backend - the backend name
            hname - the name of hash
        """
        servers = self.get_backend_servers( backend )
        cookies = {}
        for server in servers:
            if len( server['cookie'] ) > 0:
                cookies[ server['addr'] ] = server['cookie']
        if len( cookies ) > 0: redis.hmset( hname, cookies )

    def _create_cookie_index( self ):
        """
        create the cookie index
        """
        for item in self.stat:
            if 'addr' in item and 'cookie' in item:
                pos = item['addr'].rfind( ':' )
                self.cookie_index[ item['addr'] ] = item['cookie']
                if pos != -1:
                    self.cookie_index[ item['addr'][0:pos] ] = item['cookie']




class RuntimeApi:
    def __init__( self, address ):
        self.address = address

    def show_stat( self ):
        """
        execute command "show stat"

        Returns:
            stat object
        """
        csv = Csv( self.exec_command("show stat") )
        return Stat( csv.to_dict() )

    def set_server_address( self, backend_name, server_name, address, port = None ):
        if port is None:
            pos = address.rfind( ':' )
            if pos == -1: return False
            port = address[ pos + 1:]
            address = address[0:pos]
        self.exec_command( "set server %s/%s addr %s port %s" % ( backend_name, server_name, address, port ) )
        return True

    def set_server_state( self, backend_name, server_name, state ):
        """
        set state of a server in backend

        Args:
            backend_name - the name of backend
            server_name - the server in the backend in ip:port format
            state - must be one of: ready | drain | maint
        """
        self.exec_command( "set server %s/%s state %s" % ( backend_name, server_name, state ) )

    def save_server_state( self, filename ):
        with open( filename, "w" ) as fp:
            fp.write( self.exec_command( "show servers state" ) )

    def save_cookie_to_redis( self, redis, backend, hname ):
        """
        save the backend server cookies to redis hash table

        Args:
            redis - redis.Redis object or redis url like redis://host:port/0
            backend - the backend name
            hname - the hash name
        """
        self.show_stat().save_cookie_to_redis( redis, backend, hname )

    def exec_command( self, command ):
        """
        execute a runtime api command
        """
        try:
           sock = self._create_socket( self.address )
           if not command.endswith( "\n" ): command += "\n"
           sock.send( command )
           result = ""
           while True:
               data = sock.recv(1024)
               if data:
                  result += data
               else:
                  break
           sock.close()
           print "Succeed to execute command:%s" % command
           return result
        except Exception as ex:
            print "Fail to execute command:%s" % command
        return None
    def _create_socket( self, address ):
        if os.path.exists( address ):
            sock = socket.socket( socket.AF_UNIX, socket.SOCK_STREAM )
            sock.settimeout( 10 )
            if sock == 0: return None
            sock.connect( address )
            return sock
        else:
            sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
            sock.settimeout( 10 )
            index = address.rfind( ":" )
            if index == -1:
                sock.close()
                return None
            sock.connect( (address[0:index], int( address[index+1:] ) ) )
            return sock
