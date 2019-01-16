#!/usr/bin/env python

import argparse
import subprocess
import os

"""
export helm chart to current or specific directory from a running chart release with "helm get <name>"
command.

the exported helm chart can be re-deployed with "helm install --name <name> <chart>"
"""
def export_manifest( release, outDir, revision = None ):
    command = ["helm", "get", "manifest", release ]
    if revision is not None:
        command.extend( ['--revision', revision ] )
    output = subprocess.check_output( command )
    SOURCE_INDICATOR = "# Source:"
    sourceFile = None
    content = ""
    exported_files = []
    for line in output.split( "\n" ):
        if line.startswith( SOURCE_INDICATOR ):
            if len( content ) > 0 and sourceFile is not None:
                save_to_file( sourceFile, content, append = sourceFile in exported_files )
                if sourceFile not in exported_files:
                    exported_files.append( sourceFile )
            sourceFile = line[ len( SOURCE_INDICATOR ): ].strip()
            sourceFile = os.path.join( outDir, sourceFile )
            content = ""
        else:
            content = "{}\n{}".format( content, line )

    if len( content ) > 0 and sourceFile is not None:
        save_to_file( sourceFile, content, append = sourceFile in exported_files )


def export_values( release, outDir, revision = None ):
    command = ["helm", "get", "values", release ]
    if revision is not None:
        command.extend( ['--revision', revision ] )
    output = subprocess.check_output( command )
    fileName = os.path.join( outDir, release )
    fileName = os.path.join( fileName, "values.yaml" )
    save_to_file( fileName, output )

def export_chart_yaml( release, outDir, revision = None ):
    output = subprocess.check_output( ['helm', 'list'] )
    index = -1
    for line in output.split("\n"):
        index = index + 1
        if index == 0: continue
        fields = line.split()
        if release == fields[0] and ( revision is None or revision == fields[1] ):
            fileName = os.path.join( outDir, release )
            fileName = os.path.join( fileName, "Chart.yaml" )
            version = fields[-3].split("-")[-1]
            save_to_file( fileName, "apiVersion: v1\ndescription: {}\nname: {}\nappVersion: {}\nversion: {}\nengine: gotpl".format( release, release, fields[-2], version ) )
            break

def save_to_file( fileName, content, append = False ):
    dir_name = os.path.dirname( fileName )
    if not os.path.exists( dir_name ):
        os.makedirs( dir_name )
    mode = "ab" if append else "wb"
    with open( fileName, mode ) as fp:
        fp.write( content )

def parse_args():
    parser = argparse.ArgumentParser( description = "export a release of helm chart from k8s running environment" )
    parser.add_argument( "release", help = "helm release name")
    parser.add_argument( "--revision", help = "revision of helm release", required = False )
    parser.add_argument( "--out-dir", help = "output directory, default is current directory", required = False, default = "." )
    return parser.parse_args()


def main():
    args = parse_args()
    export_manifest( args.release, args.out_dir, revision = args.revision )
    export_values( args.release, args.out_dir, revision = args.revision )
    export_chart_yaml( args.release, args.out_dir, revision = args.revision )

if __name__ == "__main__":
    main()

