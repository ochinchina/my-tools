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
    dep_charts = []
    for line in output.split( "\n" ):
        if line.startswith( SOURCE_INDICATOR ):
            if len( content ) > 0 and sourceFile is not None:
                save_to_file( sourceFile, content, append = sourceFile in exported_files )
                if sourceFile not in exported_files:
                    exported_files.append( sourceFile )
                chart_name = find_chart( sourceFile )
                if chart_name is not None and chart_name not in dep_charts:
                    dep_charts.append( chart_name )
            sourceFile = line[ len( SOURCE_INDICATOR ): ].strip()
            sourceFile = os.path.join( outDir, sourceFile )
            content = ""
        else:
            content = "{}\n{}".format( content, line )

    # save the last content
    if len( content ) > 0 and sourceFile is not None:
        save_to_file( sourceFile, content, append = sourceFile in exported_files )

    for dep_chart in dep_charts:
        export_dep_chart_yaml( release, dep_chart, outDir )

def get_dep_chart_filename( dep_chart, outDir ):
    fileName = outDir;
    for chart in dep_chart.split("/"):
        fileName = os.path.join( fileName, 'charts' )
        fileName = os.path.join( fileName, chart )
    return os.path.join( fileName, "Chart.yaml" )

def find_chart( fileName ):
    path_array = split_path_to_array( fileName ) 
    i = 1
    chart_name = ""
    while i < len( path_array ):
        if path_array[i] == 'charts' and i + 2 < len( path_array ) and path_array[i+2] == 'templates':
            chart_name = "{}/{}".format( chart_name, path_array[i+1] ) if len( chart_name ) > 0 else path_array[i+1]
        i += 1
    return chart_name if len( chart_name ) > 0 else None
    
def export_values( release, outDir, revision = None ):
    command = ["helm", "get", "values", release ]
    if revision is not None:
        command.extend( ['--revision', revision ] )
    output = subprocess.check_output( command )
    fileName = os.path.join( outDir, release )
    fileName = os.path.join( fileName, "values.yaml" )
    save_to_file( fileName, output )

def export_chart_yaml( release, outDir, revision = None ):
    chart_version, app_version = get_app_version( release, revision )
    if chart_version is not None:
        fileName = os.path.join( outDir, release )
        fileName = os.path.join( fileName, "Chart.yaml" )
        save_to_file( fileName, "apiVersion: v1\ndescription: {}\nname: {}\nappVersion: {}\nversion: {}\nengine: gotpl".format( release, release, app_version, chart_version ) )

def get_app_version( release, revision ):
    output = subprocess.check_output( ['helm', 'list'] )
    index = -1
    for line in output.split("\n"):
        index = index + 1
        if index == 0: continue
        fields = line.split()
        if release == fields[0] and ( revision is None or revision == fields[1] ):
            chart_version = fields[-3].split("-")[-1]
            app_version = fields[-2]
            return chart_version, app_version
    return None

def export_dep_chart_yaml( release, dep_chart, outDir, revision = None ):
    chart_version, app_version = get_app_version( release, revision )
    fileName = get_dep_chart_filename( dep_chart, os.path.join( outDir, release ) )
    save_to_file( fileName, "apiVersion: v1\ndescription: {}\nname: {}\nappVersion: {}\nversion: {}\nengine: gotpl".format( release, release, app_version, chart_version ) )


def save_to_file( fileName, content, append = False ):
    dir_name = os.path.dirname( fileName )
    if not os.path.exists( dir_name ):
        os.makedirs( dir_name )
    mode = "ab" if append else "wb"
    with open( fileName, mode ) as fp:
        fp.write( content )

def split_path_to_array( path ):
    """
    split a path "this/is/a/path" to array ["this","is","a","path"]
    """
    result = []
    while True:
        basename = os.path.basename( path )
        if len( basename ) <= 0: break
        result.append( basename )
        path = os.path.dirname( path )
        if len( path ) <= 0: break
    return list( reversed( result ) )

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
