#!/usr/bin/python


import argparse
import json
import cStringIO

def load_property_file( prop_file ):
    result = {}
    with open( prop_file ) as fp:
        for line in fp:
            line = line.strip()
            if line.startswith( "#" ): continue
            pos = line.find( '=' )
            if pos <= 0: continue
            result[ line[0:pos].strip() ] = line[pos+1:].strip()
    return result 

def to_layers( props ):
    """
    convert the properties to layer represent.
    the property key is divided with charactor '.'
    """
    layers = {}

    for prop in props:
        words = prop.split("." )
        cur_layer = layers
        propValue = props[ prop ]
        for i, word in enumerate( words ):
            if word not in cur_layer:
                if i == len( words ) - 1:
                    cur_layer[ word ] = propValue
                else:
                    cur_layer[ word ] = {}
                    cur_layer = cur_layer[ word ]
            else:
                cur_layer = cur_layer[ word ]
    return layers

def print_level( out, indent, level ):
    for i in range( level * indent ):
        out.write( " ")
def to_yaml( layers, out, indent, level ):
    """
    convert the layers to .yaml format
    """ 
    for k, v in layers.iteritems():
        print_level( out, indent, level )
        out.write( k )
        if isinstance( v, str ):
            out.write( ": %s\n" % v )
        else:
            out.write( ":\n" )
            to_yaml( v, out, indent, level + 1 )
def parse_args():
    parser = argparse.ArgumentParser( description = "convert the .properties file to .yaml file" )
    parser.add_argument( "--prop-file", help = "the .properties file name", required = True )
    parser.add_argument( "--yaml-file", help = "the .yaml file name", required = True )
    parser.add_argument( "--indent", help = "the yaml indent space, default is 2", type = int, default = 2 )
    return parser.parse_args()

def main():
    args = parse_args()
    props = load_property_file( args.prop_file )
    out = cStringIO.StringIO()
    to_yaml( to_layers( props ), out, args.indent, 0  )
    content = out.getvalue()
    out.close()
    with open( args.yaml_file, "w" ) as fp: fp.write( content )


if __name__ == "__main__":
    main()
