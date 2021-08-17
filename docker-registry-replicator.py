#!/usr/bin/python
import abc
import hashlib
import json
import subprocess
import sys
import threading
import time

import requests
import argparse
import socket
import logging
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("registry-replicator")


class Blob:
    def __init__(self, url, image, media_type=None, digest=None):
        """
        :param url: the base url of docker registry
        :param image: the image name
        :param digest: the digest (tar sum) of the blob
        """
        self.url = url
        self.image = image
        self.media_type = media_type
        self.digest = digest
        if not digest:
            self.sha256 = hashlib.sha256()
        self.uploaded_length = 0

    def pull(self):
        """
        download a layer content

        :return: a file object if layer is downloaded successfully
            None if fail to download the layer
        """
        r = requests.get("%s/v2/%s/blobs/%s" % (self.url, self.image, self.digest), stream=True)
        if r.status_code / 100 == 2:
            return r.raw
        else:
            return None

    def exist(self):
        """
        check if this layer exists or not

        :return: a tuple (existence, content_length), existence is true if the blob exists already
        """
        r = requests.head("%s/v2/%s/blobs/%s" % (self.url, self.image, self.digest))
        return r.status_code == 200, r.headers['content-length'] if r.status_code == 200 else 0

    def get_upload_url(self):
        """
        get the upload url for uploading a layer

        Returns:
            the location
        """
        r = requests.post("%s/v2/%s/blobs/uploads/" % (self.url, self.image))
        return r.headers['location'] if r.status_code == 202 else ""

    def upload(self, upload_url, data, last=False):
        """
        upload the blob data to the url
        :param upload_url: the uploa url from method get_upload_url()
        :param data: the blob data sent to the registry server
        :param last: True - if the data is the last chunk data
        :return: true if loaded successfully, false if fail to upload the data to registry server
        """
        if data and not self.digest:
            self.sha256.update(data)

        headers = {"Content-Length": "%d" % len(data), "Content-Type": "application/octet-stream"}
        if last:
            digest = self.digest or "sha256:%s" % self.sha256.hexdigest()
            r = requests.put(upload_url, data=data, headers=headers, params={'digest': digest})
            return r.status_code == 201
        else:
            # print upload_url
            # print headers
            r = requests.patch(upload_url, data=data, headers=headers)
            # print "status_code = %d" % r.status_code
            # print r.headers
            # update the uploaded_length field
            self.uploaded_length = self.uploaded_length + (len(data) if r.status_code == 202 else 0)
            return r.headers['Location'] if r.status_code == 202 else ""


class Manifest21:
    def __init__(self, url, image, tag, content):
        """
        construct a Manifest21 object

        :param url: the registry url
        :param image: the image name
        :param content: the manifest in json format
        """
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_blobs(self):
        """
        get all the blobs in the manifest

        :return: list of Blob object
        """
        result = []
        if 'fsLayers' in self.content:
            fsLayers = self.content['fsLayers']
            for layer in fsLayers:
                if "blobSum" in layer:
                    result.append(Blob(self.url, self.image, layer["blobSum"]))
        return result


class ManifestList:
    """
    ManifestList defined in the
    """

    def __init__(self, url, image, tag, content):
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_manifests(self):
        return self.content['manifests']


class Manifest22:
    def __init__(self, url, image, tag, content):
        self.url = url
        self.image = image
        self.tag = tag
        self.content = content

    def get_layers(self):
        """
        get a list of layers

        Returns:
            the layers element in the v2 schema 2
        """
        return self.content['layers']

    def get_blobs(self):
        """
        get all the Blob object in the manifest
        :return: a list of Blob object
        """
        result = [Blob(self.url,
                       self.image,
                       media_type=self.content['config']['mediaType'],
                       digest=self.content['config']['digest'])]
        for layer in self.content['layers']:
            blob = Blob(self.url, self.image, media_type=layer['mediaType'], digest=layer['digest'])
            result.append(blob)
        return result


class DockerRegistryClient:
    def __init__(self, url):
        self.url = url

    def list_repositories(self):
        """
        list all the repositories in the registry server

        :return the image name list
        """
        r = requests.get("%s/v2/_catalog" % self.url)
        if r.status_code / 100 == 2:
            result = r.json()
            return result['repositories'] if result else []
        return []

    def list_tags(self, image_name):
        """
        list all tags made on the image

        :param image_name: the image name

        :return: tags in frozenset
        """
        r = requests.get("%s/v2/%s/tags/list" % (self.url, image_name))
        if r.status_code / 100 == 2:
            result = r.json()
            return frozenset(result['tags'])
        return frozenset([])

    def create_blob(self, image_name, digest=None, media_type=None):
        """
        create a Blob object in the registry

        :param media_type: media type
        :param image_name: the image name
        :param digest: the image digest
        """
        return Blob(self.url, image_name, digest=digest, media_type=media_type)

    def get_manifest(self, image_name, tag):
        """
        get the manifest of image

        :param image_name: the image name
        :param tag: the image tag

        :returns:
            one of following objects:
            - Manifest21, manifest v2,schema 1
            - Manifest22, manifest v2, schema 2
            - ManifestList, multi-architecture manifest
        """
        headers = {
            # 'Authorization': 'Bearer %s' % (token),
            'Accept': 'application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v1+prettyjws,application/json,application/vnd.docker.distribution.manifest.v2+json'
        }

        r = requests.get("%s/v2/%s/manifests/%s" % (self.url, image_name, tag), headers=headers)
        result = r.json()
        # only support manifest version 2 format
        if "schemaVersion" not in result:
            return None
        if result["schemaVersion"] == 1:
            return Manifest21(self.url, image_name, tag, result)
        elif result["schemaVersion"] == 2:
            if "manifests" in result:
                return ManifestList(self.url, image_name, tag, result)
            else:
                return Manifest22(self.url, image_name, tag, result)
        # other version: not support
        return None

    def put_manifest(self, image, tag, manifest):
        """
        put the manifest to registry
        :param image: the image name
        :param tag: the image tag
        :param manifest: the manifest dict
        :return: True if put the manifest to registry successfully
        """
        if "fsLayers" in manifest:
            headers = {"Content-Type": "application/vnd.docker.distribution.manifest.v1+prettyjws"}
        else:
            headers = {"Content-Type": "application/vnd.docker.distribution.manifest.v2+json"}
        r = requests.put("%s/v2/%s/manifests/%s" % (self.url, image, tag), headers=headers, json=manifest)
        return r.status_code / 100 == 2

    def put_manifest_list(self, image, tag, manifest_list):
        """
        put the manifest to registry
        :param image: the image name
        :param tag: the image tag
        :param manifest_list: a list of the manifest dict
        :return: True if put the manifest to registry successfully
        """
        headers = {"Content-Type": "application/vnd.docker.distribution.manifest.list.v2+json"}
        r = requests.put("%s/v2/%s/manifests/%s" % (self.url, image, tag), headers=headers, json=manifest_list)
        return r.status_code / 100 == 2

    def download_blob(self, image_name, blob_digest):
        """
        download a image blob
        :param image_name: the image name
        :param blob_digest: the blob digest
        :return: the blob data or None
        """
        r = requests.get("%s/v2/%s/blobs/%s" % (self.url, image_name, blob_digest), stream=True)
        if r.status_code / 100 == 2:
            return r.raw
        return None


class RegistryFinder(abc.ABC):
    @abc.abstractmethod
    def get_registries(self):
        """
        get all the registries
        :return: a set of registry
        """
        raise NotImplementedError()


class EmptyRegistryFinder(RegistryFinder):
    def get_registries(self):
        return []


class FixedAddrRegistryFinder(RegistryFinder):
    def __init__(self, addrs):
        self._addrs = addrs if isinstance(addrs, list) else [addrs]

    def get_registries(self):
        return self._addrs


class ServiceRegistryFinder(RegistryFinder):
    def __init__(self, service_name):
        self._service_name = service_name

    def get_registries(self):
        result = set()
        try:
            addrs = socket.getaddrinfo(self._service_name, 80)
            for addr in addrs:
                ip = addr[-1][0]
                result.add(ip)
        except Exception as ex:
            logger.error("fail to get ip address from service {} with error:{}".format(self._service_name, ex))
        return result


class ScriptRegistryFinder(RegistryFinder):
    def __init__(self, script):
        self._script = script

    def get_registries(self):
        result = set()
        try:
            out = subprocess.check_output([self._script]).decode()
            for line in out.split("\n"):
                line = line.strip()
                if line != "":
                    result.add(line)
        except Exception as ex:
            logger.error("fail to get ip address from script {} with error:{}".format(self._script, ex))
        return result


class TextFileRegistryFinder(RegistryFinder):
    def __init__(self, filename):
        self._filename = filename

    def get_registries(self):
        result = set()
        try:
            with open(self._filename) as fp:
                for line in fp:
                    line = line.strip()
                    if line != "":
                        result.add(line)
        except Exception as ex:
            logger.error("fail to get ip address from file {} with error:{}".format(self._filename, ex))
        return result


class RefreshableRegistryFinder(RegistryFinder):
    def __init__(self, registry_finder: RegistryFinder, refresh_interval):
        self._registry_finder = registry_finder
        self._refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._registries = set()
        th = threading.Thread(target=self._find_registries)
        th.setDaemon(True)
        th.start()

    def get_registries(self):
        with self._lock:
            return self._registries.copy()

    def _find_registries(self):
        while True:
            registries = self._registry_finder.get_registries()
            with self._lock:
                self._registries = registries
            time.sleep(self._refresh_interval)


class ExcludeRegistryFinder(RegistryFinder):
    def __init__(self, registry_finder: RegistryFinder, exclude_ips):
        self._registry_finder = registry_finder
        self._exclude_ips = set(exclude_ips)

    def get_registries(self):
        ips = self._registry_finder.get_registries()
        return ips - self._exclude_ips


class DockerRegistryReplicator:
    def __init__(self, master_registry, local_registry):
        """
        create a replicator with master & slave registry client object

        :param master_registry: the master DockerRegistryClient object
        :param local_registry: the local DockerRegistryClient oject
        """
        self._master_registry = master_registry
        self._local_registry = local_registry

    def replicate(self):
        """
        replicate all the images from master to slave
        """
        master_repositories = self._master_registry.list_repositories()
        slave_repositories = self._local_registry.list_repositories()
        for image in master_repositories:
            master_tags = self._master_registry.list_tags(image)
            if image not in slave_repositories:
                slave_tags = frozenset([])
            else:
                slave_tags = self._local_registry.list_tags(image)
            for tag in master_tags.difference(slave_tags):
                self.replicate_image(image, tag)

    def replicate_image(self, image, tag):
        """
        replicate a image from master to slave

        :param image: the name of image should be replicated
        :param tag: the image tag
        :return True if succeed to replicate the image, False if fail to replicate the image
        """
        logger.info("start to replicate image {}:{}".format(image, tag))
        manifest = self._master_registry.get_manifest(image, tag)
        if isinstance(manifest, Manifest21):
            return self.replicate_manifest21(manifest)
        elif isinstance(manifest, Manifest22):
            return self.replicate_manifest22(manifest)
        elif isinstance(manifest, ManifestList):
            for item in manifest.get_manifests():
                self.replicate_manifest21(self._master_registry.get_manifest(image, item['digest']))

            # put the ManifestList content to the slave
            return self._local_registry.put_manifest_list(image, tag, manifest)

    def replicate_manifest21(self, manifest):
        """
        replicate the manifest21
        :param manifest: the Manifest21 object
        :return: True if replicate the manifest successfully
        """
        blobs = manifest.get_blobs()
        # replicate all blocks from the master to slave
        for blob in blobs:
            logger.info("start to push blob %s" % blob.digest)
            exist, length = blob.exist()
            if exist:
                slave_blob = self._local_registry.create_blob(blob.image, blob.digest, blob.media_type)
                # if the blob exists already in slave, do not replicate it
                if slave_blob.exist()[0]:
                    continue
                # get the upload url
                upload_url = slave_blob.get_upload_url()
                logger.info("upload_url=%s" % upload_url)

                # pull the data from registry
                data_stream = blob.pull()
                if data_stream and upload_url:
                    while True:
                        # read a block and push it to the slave registry
                        data = data_stream.read(1024 * 1024)
                        if not data:
                            break
                        upload_url = slave_blob.upload(upload_url, data, False)

                    # indicate all the blocks are uploaded
                    slave_blob.upload(upload_url, "", True)
        return self._local_registry.put_manifest(manifest.image, manifest.tag, manifest.content)

    def replicate_manifest22(self, manifest):
        return self.replicate_manifest21(manifest)


def load_config(config_file):
    """
    load the configuration from .json config_file. The configuration file look like:
    {
        "service": "my-registry-name",
        "script": "/all-registry.sh",
        "file": "/tmp/all-registy.txt",
        "addrs": ["10.0.0.2", "10.0.0.3"]
        "local-addr": "10.0.0.1",
        "registry-port": 5000
    }

    :param config_file: the configuration file name
    :return:
    """
    with open(config_file) as fp:
        return json.load(fp)


def create_registry_finder_from_config(config):
    if 'service' in config:
        return ServiceRegistryFinder(config['service'])
    elif 'script' in config:
        return ScriptRegistryFinder(config['script'])
    elif 'file' in config:
        return TextFileRegistryFinder(config['file'])
    elif 'addrs' in config:
        return FixedAddrRegistryFinder(config['addrs'])
    return EmptyRegistryFinder()


def create_registry_finder(registry_addr):
    if registry_addr.startswith("service:"):
        service_name = registry_addr[len("service:"):]
        return ServiceRegistryFinder(service_name)
    elif registry_addr.startswith("script:"):
        script = registry_addr[len("script:"):]
        return ScriptRegistryFinder(script)
    elif registry_addr.startswith("file:"):
        file_name = registry_addr[len("file:"):]
        return TextFileRegistryFinder(file_name)
    else:
        return FixedAddrRegistryFinder(registry_addr)


def init_logger(log_file, log_level):
    if log_file is None:
        handler = StreamHandler(stream=sys.stdout)
    else:
        handler = RotatingFileHandler(log_file, maxBytes=50 * 1024 * 1024, backupCount=10)

    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.setLevel(log_level)
    logger.addHandler(handler)


def parse_args():
    parser = argparse.ArgumentParser(description="replicate the docker image from master to slave")
    parser.add_argument("--registry-addr", help="the registry address", required=True)
    parser.add_argument("--local-addr", help="the local registry address", required=True)
    parser.add_argument("--registry-port", help="the registry port number, default is 5000", type=int, default=5000)
    parser.add_argument("--replicate-interval", help="the registry replicate interval, default is 30 seconds", type=int,
                        default=30)
    parser.add_argument("--http-scheme", help="the http scheme", choices=["http", "https"], default="http")
    parser.add_argument("--log-file", help="the log file name")
    parser.add_argument("--log-level", help="the log level", default="DEBUG")
    return parser.parse_args()


def main():
    args = parse_args()
    init_logger(args.log_file, args.log_level)
    registry_finder = RefreshableRegistryFinder(
        ExcludeRegistryFinder(create_registry_finder(args.registry_addr), args.local_addr), 10)
    local_url = "{}://{}:{}".format(args.scheme, args.local_addr, args.registry_port)
    while True:
        registries = registry_finder.get_registries()
        for registry in registries:
            registry_url = "{}://{}:{}".format(args.scheme, registry, args.registry_port)
            master_registry = DockerRegistryClient(registry_url)
            slave_registry = DockerRegistryClient(local_url)
            replicator = DockerRegistryReplicator(master_registry, slave_registry)
            replicator.replicate()
        time.sleep(args.replicate_interval)


if __name__ == "__main__":
    main()
