#!/usr/bin/python

import array
import optparse
import os
import sys
import base64

def gen_random_key( fileName ):
  os.system("openssl rand -base64 -out %s 16" % fileName )

def encrypt(inputFileName, keyFile, outputFileName):
  with open(keyFile) as f:
    b = base64.standard_b64decode( f.read() )
  os.system("openssl enc -aes-128-ecb -a -in %s -K %s -out %s" % ( inputFileName, to_hex(b), outputFileName))

def to_hex( s ):
  return ''.join(format(ord(x),"02x") for x in list(s) )

def decrypt( inputFileName, keyFile, outputFileName):
  split_input_file( inputFileName )
  with open(keyFile) as f:
    b = base64.standard_b64decode( f.read() )
  os.system("openssl enc -d -aes-128-ecb -a -in %s -K %s -out %s" % ( inputFileName, to_hex(b), outputFileName))

def split_input_file( inputFileName ):
    lines = ""
    with open( inputFileName ) as f:
        s = f.read()
        if len( s ) <= 64:
            return
        while len( s ) > 64:
            if len( lines ) > 0:
                lines = "%s\r\n" % lines
            lines = "%s%s" % ( lines, s[0:64] )
            s = s[64:]
        if len( lines ) > 0:
            lines = "%s\r\n" % lines
        lines = "%s%s" % ( lines, s )
    with open( inputFileName, "w" ) as f:
        f.write( lines )

def main():
  usage="Usage: %prog [options] enc|dec|key-gen"
  parser = optparse.OptionParser(usage)
  parser.add_option( "-i", "--input", dest="inputFile", help="the name of to-be encrypted/descrypted file" )
  parser.add_option( "-o", "--output", dest="outputFile", help="the name of encrypted/descrypted output file" )
  parser.add_option( "-k", "--key", dest="keyFile", help="the key file for the encryption/descryption")
  (options, args) = parser.parse_args()
  if len( args ) <= 0:
    parser.print_help()
  elif args[0] == "key-gen":
    if not options.outputFile:
      print "please provide option --output"
    else:
      gen_random_key( options.outputFile )
  elif args[0] == "enc":
    if options.inputFile and options.keyFile and options.outputFile:
      encrypt( options.inputFile, options.keyFile, options.outputFile )
    else:
      print "please provide following options:--input, --output and --key"
  elif args[0] == "dec":
    if options.inputFile and options.keyFile and options.outputFile:
      decrypt( options.inputFile, options.keyFile, options.outputFile )
    else:
      print "please provide following options:--input, --output and --key"
  else:
    print "invalid command %s" % args[1]

if __name__ == "__main__":
    main()
