class PropLineReader:
    def __init__( self, s ):
        self.lines = s.split( "\n" )
        self.line_count = len( self.lines )
        self.next_line = 0

    def read_line( self ):
        if self.next_line >= self.line_count:
            return None
        r = ""
        while True:
            line = self.lines[self.next_line].strip()
            print( "line={}".format( line ) )
            self.next_line += 1
            if line.endswith( "\\" ):
                r = "{}{}".format( r, line[0:-1] )
            elif len( r ) <= 0:
                return line
            else:
                return "{}{}".format( r, line )

class Properties:
    """
    this class reads the .properties from file or from a string and provides
    APIs for the value access by key
    """
    escape_table = {'r': '\r', 'n': '\n', 't': '\t', '\\': '\\' }
    escape_rev_table = {'\r': 'r', '\n': 'n', '\t': 't', '\\': '\\' }
    def __init__( self, props ):
        self.props = props

    @classmethod
    def from_file( clss, filename ):
        """
        load .properties file
        """
        with open( filename ) as fp:
            return clss.from_string( fp.read() )

    @classmethod
    def from_string( clss, s ):
        """
        load .properties from string
        """
        line_reader = PropLineReader( s )
        props = {}
        while True:
            line = line_reader.read_line()
            if line is None:
                break
            line = line.strip()
            if line.startswith( '#' ):
                continue
            pos1 = line.find( '=' )
            pos2 = line.find( ':' )
            if pos1 == -1:
                pos = pos2
            else:
                pos = pos1 if pos2 == -1 or pos1 < pos2 else pos2

            if pos != -1:
                name = line[0:pos].strip()
                value = clss._remove_escape( line[pos+1:].strip() )
                props[ name ] = value
        return Properties( props )

    def has_property( self, name ):
        """
        return True if the specified properties exists or not
        """
        return name in self.props

    def get_property( self, name ):
        """
        get the properties by name
        """
        return self.props[ name ] if name in self.props else None

    def set_property( self, name, value ):
        """
        set the property with its name and value
        """
        self.props[ name ] = value

    def __repr__( self ):
        r = ""
        for name, value in self.props.iteritems():
            if len( r ) > 0:
                r = "{}\n".format( r )
            r = "{}{}={}".format( r, name, self._add_escape( value ) )
        return r

    def _add_escape( self, s ):
        new_values = []
        for ch in s:
            if ch in Properties.escape_rev_table:
                new_values.extend( ["\\", Properties.escape_rev_table[ch] ] )
            else:
                new_values.append( ch )
        return "".join( new_values )

    @classmethod
    def _remove_escape( clss, value ):
        start = 0
        new_value = ""
        n = len( value )
        while start < n:
            pos = value.find( '\\', start )
            if pos == -1 or pos + 1 >= n:
                return value if start == 0 else "{}{}".format( new_value, value[start:] )
            new_value = "{}{}".format( new_value, value[start:pos] )
            if value[pos+1] in clss.escape_table:
                new_value = "{}{}".format( new_value, clss.escape_table[ value[pos+1] ])
            else:
                new_value = "{}{}".format( new_value, value[pos+1] )
            start = pos + 2
