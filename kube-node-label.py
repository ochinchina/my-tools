#!/usr/bin/python


import os
import subprocess
import sys

def get_nodes():
    result = []
    out = subprocess.check_output( ['kubectl', 'get', 'node'] )
    for index, line in enumerate( out.split("\n") ):
        if index != 0:
            words = line.split()
            if len( words ) >= 5:
                result.append( words[0] )
    return result

def make_node_label( node, label ):
    command = "kubectl label node %s %s" % (node, label)
    print command
    os.system( command )

def list_node_labels( node ):
    out = subprocess.check_output( ['kubectl', 'describe', 'node', node ] )
    label_flag = False
    labels = []
    for line in out.split( "\n" ):
        if line.startswith( "Labels:"):
            label_flag = True
            labels.append( line[ len( "Labels:" ):].strip() )
        elif len( line ) > 0 and line[0].isspace() and label_flag:
            labels.append( line.strip() )
        elif len( line ) > 0 and label_flag and not line[0].isspace():
            break

    for label in labels:
        print label

def main():
    if len( sys.argv ) < 3:
        print "Usage:%s node|- label1 label2..." % sys.argv[0]
        sys.exit(1)

    if sys.argv[1] == '-':
        nodes = get_nodes()
    else:
        nodes = [ sys.argv[1] ]
    labels = sys.argv[2:]
    
    for node in nodes:
        for label in labels:
            make_node_label( node, label )

if __name__ == "__main__":
    main()
