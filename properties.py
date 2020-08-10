class Properties:
    def __init__( self, props ):
        self.props = props

    @classmethod
    def from_file( clss, filename ):
        with open( filename ) as fp:
            return clss.from_string( fp.read() )

    @classmethod
    def from_string( clss, s ):
        props = {}
        for line in s.split( "\n" ):
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
                value = clss._escape_value( line[pos+1:].strip() )
                props[ name ] = value
        return Properties( props )

    def has_property( self, name ):
        return name in self.props

    def get_property( self, name ):
        return self.props[ name ] if name in self.props else None

    @classmethod
    def _escape_value( clss, value ):
        start = 0
        new_value = ""
        n = len( value )
        escape_table = {'r': '\r', 'n': '\n', 't': '\t', '\\': '\\' }
        while start < n:
            pos = value.find( '\\', start )
            if pos == -1 or pos + 1 >= n:
                return value if start == 0 else "{}{}".format( new_value, value[start:] )
            new_value = "{}{}".format( new_value, value[start:pos] )
            if value[pos+1] in escape_table:
                new_value = "{}{}".format( new_value, escape_table[ value[pos+1] ])
            else:
                new_value = "{}{}".format( new_value, value[pos+1] )
            start = pos + 2
