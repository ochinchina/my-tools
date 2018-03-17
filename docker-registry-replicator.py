#!/usr/bin/python

import json
import hashlib
import requests
import argparse

class Blob:
    def __init__( self, url, image, mediaType = None, digest = None ):
        """
        Args:
            url - the base url of docker registry
            image - the image name
            digest - the digest (tarsum) of the blob
        """
        self.url = url
        self.image = image
        self.digest = digest
        self.mediaType = mediaType
        if not digest:
            self.sha256 = hashlib.sha256()
        self.uploaded_length = 0


    def pull( self ):
        """
        download a layer content

        Returns:
            a file object if layer is downloaded successfully
            None if fail to download the layer
        """
        r = requests.get( "%s/v2/%s/blobs/%s" % ( self.url, self.image, self.digest ), stream = True )
        if r.status_code / 100 == 2:
            return r.raw
        else:
            return None

    def exist( self ):
        """
        check if this layer exists or not

        Returns:
            a tuple (existence, content_length), existence is true if the blob exists
            already
        """
        r = requests.head( "%s/v2/%s/blobs/%s" % (self.url, self.image, self.digest ) )
        return r.status_code == 200, r.headers['content-length'] if r.status_code == 200 else 0

    def get_upload_url( self ):
        """
        get the upload url for uploading a layer

        Returns:
            the location 
        """
        #headers = {"Content-Type":"application/octect-stream"}
        r = requests.post( "%s/v2/%s/blobs/uploads/" % ( self.url, self.image ))
        print r.headers
        return r.headers['location'] if r.status_code == 202 else ""
        #return "%s/v2/%s/blobs/uploads/%s" % ( self.url, self.image, r.headers['Docker-Upload-Uuid']) if r.status_code == 202 else ""

    def upload( self, upload_url, data, last = False ):
        """
        Args:
            upload_url: the uploa url from method get_upload_url()
            data: the data sent to the registry server
            last: True - if the data is the last chunk data
        Returns:
            true if loaded successfully, false if fail to upload the data to registry server
        """
        if data and not self.digest:
            self.sha256.update( data )

        headers = {"Content-Length": "%d" % len( data ), "Content-Type": "application/octet-stream"}
        #if self.mediaType:
        #    headers['Content-Type'] = self.mediaType
        # set the Content-Range if is not monolithic upload
        #if not last or self.uploaded_length > 0:
        #    headers['Content-Range'] = "%d-%d" % ( self.uploaded_length, len( data ) + self.uploaded_length - 1  )
        if last:
            digest = self.digest or "sha256:%s" % self.sha256.hexdigest()
            r = requests.put( upload_url, data = data, headers = headers, params = {'digest': digest })
            print r.headers
            return r.status_code == 201
        else:
            #print upload_url
            #print headers
            r = requests.patch( upload_url, data = data, headers = headers )
            #print "status_code = %d" % r.status_code
            #print r.headers
            #update the uploaded_length field
            self.uploaded_length = self.uploaded_length + ( len(data) if r.status_code == 202 else 0 )
            return r.headers['Location'] if r.status_code == 202 else ""


class Manifest21:
    def __init__( self, url, image, tag, content ):
        """
        construct a Manifest21 object

        Args:
            url: the registry url
            image: the image name
            content: the manifest in json format
        """
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_blobs( self ):
        """
        get all the blobs in the manifest

        Returns:
            list of Blob object
        """
        result = []
        if 'fsLayers' in self.content:
            fsLayers = self.content['fsLayers']
            for layer in fsLayers:
                if "blobSum" in layer:
                    result.append( Blob( self.url, self.image, layer["blobSum"]) )
        return result

class ManifestList:
    """
    ManifestList defined in the 
    """
    def __init__( self, url, image, tag, content ):
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_manifests( self ):
        return self.content['manifests']

class Manifest22:
    def __init__( self, url, image, tag, content ):
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_layers( self ):
        """
        get a list of layers

        Returns:
            the layers element in the v2 schema 2
        """
        return self.content['layers']

    def get_blobs( self ):
        result = []
        result.append( Blob( self.url, self.image, mediaType = self.content['config']['mediaType'], digest = self.content['config']['digest']) )
        for layer in self.content['layers']:
            blob = Blob( self.url, self.image, mediaType = layer['mediaType'], digest = layer['digest'])
            result.append( blob )
        return result

class DockerRegistryClient:
    def __init__( self, url ):
        self.url = url

    def list_repositories( self ):
        """
        list all the repositories in the registry server

        Returns:
            the image name list
        """
        r = requests.get( "%s/v2/_catalog" % self.url )
        if r.status_code / 100 == 2:
            result = r.json()
            return result['repositories'] if result else []
        return []

    def list_tags( self, image_name ):
        """
        list all tags made on the image

        Args:
            image_name: the image name

        Returns:
            tags in frozenset
        """
        r = requests.get( "%s/v2/%s/tags/list" % ( self.url, image_name ) )
        if r.status_code / 100 == 2:
            result = r.json()
            return frozenset(result['tags'])
        return frozenset([])

    def create_blob( self, image_name, digest = None, mediaType = None ):
        """
        create a Blob object in the registry

        Args:
            image_name: the image name
            digest: the image digest
        """
        return Blob( self.url, image_name, digest = digest, mediaType = mediaType )

    def get_manifest( self, image_name, tag ):
        """
        get the manifest of image

        Args:
            image_name: the image name
            tag: the image tag

        Returns:
            one of following objects:
            - Manifest21, manifest v2,schema 1
            - Manifest22, manifest v2, schema 2
            - ManifestList, multi-architecture manifest
        """
        headers = {
            #'Authorization': 'Bearer %s' % (token),
            'Accept': 'application/vnd.docker.distribution.manifest.list.v2+json',
            'Accept': 'application/vnd.docker.distribution.manifest.v1+prettyjws',
            'Accept': 'application/json',
            'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
        r = requests.get( "%s/v2/%s/manifests/%s" % ( self.url, image_name, tag ), headers = headers )
        print r.content
        result = r.json()
        #only support manifest version 2 format
        if "schemaVersion" not in result:
            return None
        if result["schemaVersion"] == 1:
            return Manifest21( self.url, image_name, tag, result )
        elif result["schemaVersion"] == 2:
            if "manifests" in result:
                return ManifestList( self.url, image_name, tag, result )
            else:
                return Manifest22( self.url, image_name, tag, result )
        #other version: not support
        return None

    def put_manifest( self, image, tag, manifest ):
        if "fsLayers" in manifest:
            headers = {"Content-Type": "application/vnd.docker.distribution.manifest.v1+prettyjws"}
        else:
            headers = { "Content-Type": "application/vnd.docker.distribution.manifest.v2+json"}
        r = requests.put( "%s/v2/%s/manifests/%s" % (self.url, image, tag ), headers = headers, json = manifest )
        return r.status_code / 100 == 2

    def put_manifest_list( self, image, tag, manifest_list ):
        headers = {"Content-Type": "application/vnd.docker.distribution.manifest.list.v2+json"}
        r = requests.put( "%s/v2/%s/manifests/%s" % (self.url, image, tag ), headers = headers, json = manifest_list )
        return r.status_code / 100 == 2

    def download_blob( self, image_name, blob_digest ):
        print "%s/v2/%s/blobs/%s"%( self.url, image_name, blob_digest )
        r = requests.get("%s/v2/%s/blobs/%s"%( self.url, image_name, blob_digest ), stream = True )
        if r.status_code / 100 == 2:
            return r.raw
        return None


class DockerRegistryReplicator:
    def __init__( self, master_registry, slave_registry):
        """
        create a replicator with master & slave registry client object

        Args:
            master_registry: the master DockerRegistryClient object
            slave_registry: the slave DockerRegistryClient oject
        """
        self.master_registry = master_registry
        self.slave_registry = slave_registry

    def replicate( self ):
        """
        replicate all the images from master to slave
        """
        master_repositories = self.master_registry.list_repositories()
        slave_repositories = self.slave_registry.list_repositories()
        for image in master_repositories:
            master_tags = self.master_registry.list_tags( image )
            if image not in slave_repositories:
                slave_tags = frozenset([])
            else:
                slave_tags = self.slave_registry.list_tags( image )
            for tag in master_tags.difference( slave_tags ):
                self.replicate_image( image, tag )


    def replicate_image( self, image, tag ):
        """
        replicate a image from master to slave

        Args:
            image: the name of image should be replicated
        Returns:
            True if succeed to replicate the image
            False if fail to replicate the image
        """
        print "start to replicate image %s:%s" % (image, tag )
        manifest = self.master_registry.get_manifest( image, tag )
        print manifest
        print self.slave_registry.get_manifest( image, tag )
        if isinstance( manifest, Manifest21 ):
            self.replicate_manifest21()
        elif isinstance( manifest, Manifest22 ):
            self.replicate_manifest22( manifest )
        elif isinstance( manifest, ManifestList ):
            for item in manifest.get_manifests():
                replicate_manifest21( self.master_registry.get_manifest( image, item['digest']) )

            #put the ManifestList content to the slave
            self.slave_registry.put_manifest_list( image, tag, manifest )

    
    def replicate_manifest21( self, manifest ):
        blobs = manifest.get_blobs()
        # replicate all blocks from the master to slave
        for blob in blobs:
            print "start to push blob %s" % blob.digest
            exist, length = blob.exist()
            if exist:
                slave_blob = self.slave_registry.create_blob( blob.image, blob.digest, blob.mediaType )
                # if the blob exists already in slave, do not replicate it
                if slave_blob.exist()[0]:
                    continue
                # get the upload url
                upload_url = slave_blob.get_upload_url()
                print "upload_url=%s" % upload_url

                #pull the data from registry
                data_stream = blob.pull()
                if data_stream and upload_url:
                    while True:
                        # read a block and push it to the slave registry
                        data = data_stream.read( 1024*1024)
                        if not data:
                            break
                        upload_url = slave_blob.upload( upload_url, data, False )

                    #indicate all the blocks are uploaded
                    slave_blob.upload( upload_url, "", True )
        self.slave_registry.put_manifest( manifest.image, manifest.tag, manifest.content )

    def replicate_manifest22( self, manifest ):
        self.replicate_manifest21( manifest )



def parse_args():
    parser = argparse.ArgumentParser( description = "replicate the docker image from master to slave" )
    parser.add_argument( "--master-url", help="the url of master docker registry", required = True )
    parser.add_argument( "--slave-url", help = "the url of slave docker registry", required = True )
    return parser.parse_args()

def main():
    args = parse_args()
    master_registry = DockerRegistryClient( args.master_url )
    slave_registry = DockerRegistryClient( args.slave_url )
    replicator = DockerRegistryReplicator( master_registry, slave_registry )
    replicator.replicate()

if __name__ == "__main__":
    main()
