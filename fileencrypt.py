#!/usr/bin/python

import argparse
import os
import random
import struct
import tempfile
from Crypto.Cipher import AES

__init__ = ["AESFileEncryptor"]

class AESFileEncryptor:
    magic = "MyAESEncrypt"
    def __init__( self, key, blockSize = 4096 ):
        self.key = key
        self.blockSize = blockSize

    def encrypt_data( self, iv, data ):
        return self._encrypt_data( self._create_aes( iv ), data )

    def encrypt_file( self, filename, out_file = None ):
        """
        encrypt the file
        """
        if self.is_file_encrypted( filename ):
            return True

        iv = self.create_init_vector()
        aes = self._create_aes( iv )
        tmp_filename = self._create_temp_file() if out_file is None or os.path.abspath( filename ) == os.path.abspath( out_file ) else out_file
        size = os.path.getsize( filename )
        with open( tmp_filename, "wb" ) as fout:
            # write magic
            fout.write( AESFileEncryptor.magic )
            # write size
            fout.write( struct.pack('<Q', size) )
            # write iv
            fout.write( iv )
            # encrypt block by block
            with open( filename ) as fin:
                while True:
                    data = fin.read( self.blockSize )
                    if len(data) == 0: break
                    data = self.encrypt_data( iv, data )
                    fout.write( data )
        if out_file is None or os.path.abspath( filename ) == os.path.abspath( out_file ):
            os.rename( tmp_filename, filename )
        return True

    def decrypt_data( self, iv, data ):
        return self._decrypt_data( self._create_aes( iv ), data )

    def decrypt_file( self, filename, out_file = None ):
        """
        decrypt the file

        return: None or the name of decrypted file
        """
        tmp_filename = self._create_temp_file() if out_file is None else out_file
        with open( filename ) as fin:
            # check the magic
            m = fin.read( len( AESFileEncryptor.magic ) )
            if m != AESFileEncryptor.magic: return None
            # read size
            size = struct.unpack('<Q', fin.read(struct.calcsize('<Q')))[0]
            # read iv
            iv = fin.read( 16 )
            if len( iv ) != 16: return None

            # read and descrypt file
            with open( tmp_filename, "wb" ) as fout:
                while size > 0:
                    data = fin.read( self.blockSize )
                    if len( data ) == 0: break
                    data = self.decrypt_data( iv, data )
                    if len( data ) > size:
                        fout.write( data[0:size] )
                        size = 0
                    else:
                        fout.write( data )
                        size -= len( data )
        return tmp_filename


    def is_file_encrypted( self, filename ):
        with open( filename ) as fp:
            data = fp.read()
            return True if data[0:len( AESFileEncryptor.magic )] == AESFileEncryptor.magic else False

    def _encrypt_data( self, aes, data ):
        return aes.encrypt( data ) if len( data ) % 16 == 0  else aes.encrypt( data + ' ' * ( 16 - len( data ) % 16 ) )

    def _decrypt_data( self, aes, data ):
        return aes.decrypt( data )

    def _create_aes( self, iv ):
        return AES.new(self.key, AES.MODE_CBC, iv )

    def _create_temp_file( self ):
        f, name = tempfile.mkstemp()
        os.close(f)
        return name

    def create_init_vector( self ):
        """
        create 16 bytes initialization vector
        """
        return ''.join([chr(random.randint(0, 0xFF)) for i in range(16)])

def encrypt_file( args ):
    encryptor = AESFileEncryptor( args.key )
    encryptor.encrypt_file( args.file, args.out )

def decrypt_file( args ):
    encryptor = AESFileEncryptor( args.key )
    encryptor.decrypt_file( args.file, args.out )

def parse_args():
    parser = argparse.ArgumentParser( description = "encrypt/descrypt data/file with AES algorithm" )
    parser.add_argument( "--key", help = "the 16 bytes encrypt/descrypt key", required = True )
    subparsers = parser.add_subparsers( help = "sub commands")
    encrypt_parser = subparsers.add_parser( "encrypt", help = "encrypt file" )
    encrypt_parser.add_argument( "--file", help = "the encrypt file name", required = True )
    encrypt_parser.add_argument( "--out", help = "the output filename", required = True )
    encrypt_parser.set_defaults( func = encrypt_file )
    decrypt_parser = subparsers.add_parser( "decrypt", help = "decrypt file" )
    decrypt_parser.add_argument( "--file", help = "the decrypt file name", required = True )
    decrypt_parser.add_argument(  "--out", help = "the output filename", required = True )
    decrypt_parser.set_defaults( func = decrypt_file )
    return parser.parse_args()

def main():
    args = parse_args()
    args.func( args )


if __name__ == "__main__":
    main()
