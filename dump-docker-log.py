#!/usr/bin/env python
import abc
import argparse
import json
import os
import subprocess
import sys


class DockerLog:
    def __init__(self, container_dir='/var/lib/docker/containers'):
        self._container_dir = container_dir

    def get_all_containers(self):
        for root, dirs, files in os.walk(self._container_dir):
            if os.path.samefile(root, self._container_dir):
                return dirs
        return []

    def get_container_log_files(self, container_id):
        r = []
        for root, dirs, files in os.walk(self._container_dir):
            for f in files:
                if f.startswith(container_id):
                    r.append(os.path.join(root, f))
        return list(sorted(r, reverse=True))

    def extract_container_log(self, container_id, output_file):
        if output_file is None:
            out = sys.stdout
        else:
            out = open(output_file, "w")
        try:
            for f in self.get_container_log_files(container_id):
                self._extract_log_from_file(f, out)
        except Exception as ex:
            pass

        out.close()

    @classmethod
    def _extract_log_from_file(cls, filename, out):
        with open(filename) as fp:
            for line in fp:
                out.write(json.loads(line)['log'])


class ContainerIdFinder:
    @abc.abstractmethod
    def find_container_id(self):
        raise NotImplementedError()


class K8SContainerIdFinder(ContainerIdFinder):
    def __init__(self, namespace, pod_name, container_name):
        self._namespace = namespace
        self._pod_name = pod_name
        self._container_name = container_name

    def find_container_id(self):
        try:
            out = subprocess.check_output(
                ["kubectl", "get", "pod", self._pod_name, "-n", self._namespace, "-o", "json"])
            if not isinstance(out, str):
                out = out.decode()
            item = json.loads(out)
            containers = item['spec']['containers']
            container_statuses = item['status']['containerStatuses']
            for container in containers:
                container_name = container['name']
                if container_name != self._container_name:
                    continue
                for container_status in container_statuses:
                    if container_status['name'] == container_name:
                        container_id = container_status['containerID']
                        if container_id.startswith("docker://"):
                            container_id = container_id[len("docker://"):].strip()
                        return container_id
        except Exception as ex:
            print(ex)

        return None


class DockerContainerIdFinder(ContainerIdFinder):
    def __init__(self, container_name):
        self._container_name = container_name

    def find_container_id(self):
        try:
            out = subprocess.check_output(["docker", "ps"])
            if not isinstance(out, str):
                out = out.decode()
            lines = out.split("\n")
            for line in lines[1:]:
                fields = line.split()
                if self._container_name in (fields[0], fields[-1]):
                    return fields[0]
        except Exception as ex:
            print(ex)
        return None


class DirContainerIdFinder(ContainerIdFinder):
    def __init__(self, container_name, directory='/var/lib/docker/containers'):
        self._container_name = container_name
        self._directory = directory

    def find_container_id(self):
        for root, dirs, files in os.walk(self._directory):
            for d in dirs:
                if os.path.samefile(root, self._directory) and d.startswith(self._container_name):
                    return d
        return None

class FallbackContainerIdFinder(ContainerIdFinder):
    def __init__(self, finders):
        self._finders = finders

    def find_container_id(self):
        for finder in self._finders:
            container_id = finder.find_container_id()
            if container_id is not None:
                return container_id
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="dump docker container log")
    parser.add_argument("--output_file", "-o", help="the log output file")
    parser.add_argument("--namespace", "-n", help="the kubernetes namespace", default="default")
    parser.add_argument("--pod-name", "-p", help="the pod name")
    parser.add_argument("--container-name", "-c", help="the container name or id", required=True)
    return parser.parse_args()


def create_container_finder(args):
    if args.pod_name is not None:
        return K8SContainerIdFinder(args.namespace, args.pod_name, args.container_name)
    else:
        finders = [DirContainerIdFinder(args.container_name), DockerContainerIdFinder(args.container_name)]
        return FallbackContainerIdFinder(finders)


def main():
    args = parse_args()
    container_id_finder = create_container_finder(args)
    container_id = container_id_finder.find_container_id()
    if container_id is None:
        print("fail to find the specific container")
    else:
        docker_log = DockerLog()
        docker_log.extract_container_log(container_id, args.output_file)


if __name__ == "__main__":
    main()
