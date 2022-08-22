#!/usr/bin/env python

import argparse
import sys

import flask
import json
import logging
import logging.handlers
import mmap
import os
import re
import shutil
import subprocess
import threading
import time
import socket
from flask import request, Response
import traceback
from abc import ABCMeta, abstractmethod

try:
    from Queue import Queue
    from urllib2 import urlopen, Request
except ImportError:
    from queue import Queue
    from urllib.request import urlopen, Request

logger = logging.getLogger(__name__)


def default_program_with_error_action():
    if os.getenv("PROGRAM_BLOCK_ACTION", "null").lower() in ("restart", "exit"):
        print("Exit program with code 1")
        logger.info("Exit program with code 1")
        sys.exit(1)
    else:
        print("No action for program block error")
        logger.info("No action for program block error")


def split_path(path):
    result = []
    while True:
        head, tail = os.path.split(path)
        if len(tail) <= 0:
            break
        result.append(tail)
        path = head
    return list(reversed(result))


class EventStat:
    def __init__(self):
        self._events = {}
        self._lock = threading.Lock()

    def increase(self, event_name, count=1):
        with self._lock:
            if event_name not in self._events:
                self._events[event_name] = 0
            self._events[event_name] += count

    def clear(self, event_name):
        with self._lock:
            if event_name in self._events:
                del self._events[event_name]

    def get_count(self, event_name):
        with self._lock:
            return self._events[event_name] if event_name in self._events else 0


event_stat = EventStat()


class MonitorOperation:
    def __init__(self, name, timeout, action):
        self.name = name
        self.timeout_time = time.time() + timeout
        self.action = action

    def is_timeout(self):
        """
        :return: True if the operation is timeout
        """
        return self.timeout_time < time.time()

    def get_name(self):
        return self.name

    def run_action(self):
        try:
            self.action()
        except Exception as ex:
            logger.error("Fail to run the action with error:{}".format(ex))


class OperationMonitor:
    def __init__(self, operation_check_interval=5):
        self._operations = {}
        self._operation_check_interval = operation_check_interval
        self._lock = threading.Lock()
        th = threading.Thread(target=self._check_operation_timeout)
        th.daemon = True
        th.start()

    def add_operation(self, name, timeout, action=default_program_with_error_action):
        with self._lock:
            self._operations[name] = MonitorOperation(name, timeout, action)

    def remove_operation(self, name):
        with self._lock:
            if name in self._operations:
                del self._operations[name]

    def has_timeout_operation(self):
        """
        check if there has any timeout operations
        :return: True if some operations are timeout
        """
        tmp = self._clone_operations()

        for name in tmp:
            op = tmp[name]
            if op.is_timeout():
                logger.info("The operation {} is timeout".format(name))
                return True
        return False

    def _check_operation_timeout(self):
        while True:
            tmp = self._clone_operations()
            for name in tmp:
                op = tmp[name]
                if op.is_timeout():
                    logger.info("The operation {} is timeout".format(name))
                    op.run_action()
            time.sleep(self._operation_check_interval)

    def _clone_operations(self):
        tmp = {}
        with self._lock:
            tmp.update(self._operations)
        return tmp


operation_monitor = OperationMonitor()


def is_modified_before(filename, modified_before):
    """
    check if the file is modified before modified_before seconds
    :param filename: the file name
    :param modified_before: in seconds
    :return: True if the file is modified before modified_before seconds
    """
    if not os.path.exists(filename):
        return False
    return os.path.getmtime(filename) + modified_before < time.time()


class ModuleFiles:
    """
    manage all the files in one module
    """

    def __init__(self,
                 module_name,
                 path,
                 recursive,
                 backup_path,
                 include_patterns,
                 exclude_patterns,
                 modified_before,
                 update_interval):
        self.module_name = module_name
        self.path = os.path.abspath(path)
        self.recursive = recursive
        self.backup_path = os.path.abspath(backup_path) if backup_path is not None else None
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.update_interval = 300 if update_interval is None else update_interval
        self.modified_before = modified_before
        self.next_update_time = 0
        self.files = {'files': {}, 'backups': {}}
        self._lock = threading.Lock()

    def update_files(self, force=False):
        """
        update the local files

        :param force: force to update the files immediately even if the update time does not meet
        :return: the updated files
        """
        op_name = "update_files_of_{}".format(self.module_name)
        operation_monitor.add_operation(op_name, 600)
        files = self._update_files(force)
        operation_monitor.remove_operation(op_name)
        return files

    def _update_files(self, force=False):
        """
        update the files
        """
        with self._lock:
            if not force and self.next_update_time > time.time():
                return self.files.copy()
            self.next_update_time = time.time() + self.update_interval

        all_files, ex = self._get_files(self.path)
        if self.backup_path is None:
            all_backup_files, backup_ex = {}, None
        else:
            all_backup_files, backup_ex = self._get_files(self.backup_path)

        with self._lock:
            if ex is None:
                event_stat.clear("file_read_failure")
                self.files['files'] = all_files
            else:
                event_stat.increase("file_read_failure")
            if backup_ex is None:
                event_stat.clear("backup_file_read_failure")
                self.files['backups'] = all_backup_files
            else:
                event_stat.increase("backup_file_read_failure")
            return self.files

    def _get_files(self, path):
        """
        get all the files under path
        :param path: the file path
        :return: a dict like:
        {
            "file1": (file_size, file_change_time),
            "file2": (file_size, file_change_time)
        }
        """
        try:
            logger.info("start to update files under path {}".format(path))
            if os.path.isfile(path):
                name = os.path.join("/", self.module_name, os.path.basename(path))
                stat = os.stat(path)
                return {name: [stat.st_size, stat.st_mtime]}, None

            tmp_files = []
            for root, dirs, names in os.walk(path):
                if self.recursive or os.path.samefile(root, path):
                    for name in names:
                        if not self._match_file_item(name):
                            continue
                        filename = os.path.join(root, name)
                        if is_modified_before(filename, self.modified_before):
                            tmp_files.append(filename)
            all_files = {}
            for f in tmp_files:
                if os.path.isfile(f):
                    name = os.path.join("/", self.module_name, f[len(path) + 1:])
                    stat = os.stat(f)
                    all_files[name] = [stat.st_size, stat.st_mtime]
            logger.info("{} files are founded under {}".format(len(all_files), path))
            return all_files, None
        except Exception as ex:
            logger.error("fail to update files in path {} with error {}s".format(self.path, ex))
            traceback.print_exc()
            return {}, ex

    def file_added(self, name):
        """
        a file is added
        """
        filename = self.get_abspath(name)
        size = -1
        last_change_time = time.time()
        if os.path.exists(filename):
            stat = os.stat(filename)
            size = stat.st_size
            last_change_time = stat.st_mtime
        with self._lock:
            self.files['files'][name] = [size, last_change_time]

    def get_size(self, name, backup=False):
        """
        get the size of file
        :param name: the file name
        :param backup: True the file is a backup file
        :return: the size of file or None if the file does not exist
        """
        with self._lock:
            if backup:
                return self.files['backups'][name][0] if name in self.files['backups'] else None
            else:
                return self.files['files'][name][0] if name in self.files['files'] else None

    def get_module_name(self):
        return self.module_name

    def get_abspath(self, name, backup=False):
        """
        get the download file path
        :param name: the file name with module
        :param backup: True to get the file in backup path
        """
        prefix = os.path.join("/", self.module_name)
        if name.startswith(prefix):
            if backup:
                if self.backup_path is None:
                    return None
                if os.path.isfile(self.backup_path) and name[len(prefix) + 1:] == os.path.basename(self.backup_path):
                    return self.backup_path
                else:
                    return os.path.join(self.backup_path, name[len(prefix) + 1:])
            else:
                if os.path.isfile(self.path) and name[len(prefix) + 1:] == os.path.basename(self.path):
                    return self.path
                else:
                    return os.path.join(self.path, name[len(prefix) + 1:])
        return None

    @classmethod
    def _match_pattern(cls, name, pattern):
        """
        check if the file basename matches the pattern or not
        """
        return re.match(pattern, name) is not None

    def _match_any_patterns(self, name, patterns):
        for pattern in patterns:
            if self._match_pattern(name, pattern):
                return True
        return False

    def _match_file_item(self, name):
        # check if the name matches any one of 'include-patterns'
        if self.include_patterns is not None and len(self.include_patterns) > 0:
            if not self._match_any_patterns(name, self.include_patterns):
                return False

        # check if the name matches any one of 'exclude-patterns'
        if self.exclude_patterns is not None and len(self.exclude_patterns) > 0:
            if self._match_any_patterns(name, self.exclude_patterns):
                return False
        return True


class AsyncPush:
    def __init__(self, push_thread_num=4, max_pending_requests=10000):
        self._push_requests = Queue()
        self._max_pending_requests = max_pending_requests
        for _ in range(push_thread_num):
            th = threading.Thread(target=self._start_push_thread)
            th.daemon = True
            th.start()

    def add_requests(self, push_requests):
        """
        add a list of push request
        :param push_requests: a list of push request
        :return: True if add to the pending queue, otherwise return False
        """
        if self._push_requests.qsize() + len(push_requests) > self._max_pending_requests:
            return False
        for push_request in push_requests:
            self._push_requests.put(push_request)
        return True

    def _start_push_thread(self):
        while True:
            push_request = self._push_requests.get()
            logger.info("push file {} to url {}".format(push_request['filename'], push_request['url']))
            op_name = "push_file_{}".format(push_request['filename'])
            operation_monitor.add_operation(op_name, 600)
            self._push_file(push_request['filename'], push_request['url'])
            operation_monitor.remove_operation(op_name)

    @classmethod
    def _push_file(cls, filename, url):
        try:
            if filename is None or not os.path.exists(filename):
                req = Request(url, data="".encode(), headers={"FileNotExist": "true"})
                urlopen(req, timeout=300)
            elif os.path.getsize(filename) <= 0:
                urlopen(url, data="".encode(), timeout=300)
            else:
                stat_info = os.stat(filename)
                with open(filename) as fp:
                    headers = {"FileLastAccessTime": str(stat_info.st_atime),
                               "FileLastModifiedTime": str(stat_info.st_mtime)}
                    mmapped_file_as_string = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
                    req = Request(url, data=mmapped_file_as_string, headers=headers)
                    urlopen(req, timeout=300)
            event_stat.clear("push_file_failure")
        except Exception as ex:
            event_stat.increase("push_file_failure")
            logger.error("fail to push file {} with error:{}".format(filename, ex))


def check_health():
    if operation_monitor.has_timeout_operation():
        return 500, "operation blocked"
    failure_ops = ["file_read_failure",
                   "backup_file_read_failure",
                   "push_file_failure",
                   "send_file_failure",
                   "save_file_failure"]
    for op in failure_ops:
        if event_stat.get_count(op) >= 5:
            logger.error("operation {} is failed".format(op))
            return 500, "disk operation failed"
    return "OK"


class ReplicateServer:
    def __init__(self, file_config):
        self.module_files = {}
        self._create_module_files(file_config)
        self.files = {}
        self._lock = threading.Lock()
        self.async_push = AsyncPush()
        self._retrieve_files()
        th = threading.Thread(target=self._start_file_retrieve)
        th.daemon = True
        th.start()

    def _create_module_files(self, file_config):
        for item in file_config:
            inc_patterns = item['include-patterns'] if 'include-patterns' in item else None
            exc_patterns = item['exclude-patterns'] if 'exclude-patterns' in item else None
            update_interval = item['update-interval'] if 'update-interval' in item else 300
            backup_dir = item['backup-dir'] if 'backup-dir' in item else None
            recursive = item['recursive'] if 'recursive' in item else False
            modified_before = item['modified-before'] if 'modified-before' in item else 120
            self.module_files[item['name']] = ModuleFiles(item['name'],
                                                          item['dir'],
                                                          recursive,
                                                          backup_dir,
                                                          inc_patterns,
                                                          exc_patterns,
                                                          modified_before,
                                                          update_interval)

    def get_files(self):
        """
        process /list files operation from http client

        :return: a flask Response object with the files(in json format) in the module, the json looks like:
        {
            "files": { "/module/file-1":[file-size, file-last-modified-time],
                       "/module/file-2":[file-size, file-last-modified-time],
                       "/module/file-3":[file-size, file-last-modified-time] },
            "backups": {"/module/backup-1":[file-size, file-last-modified-time],
                        "/module/backup-2":[file-size, file-last-modified-time]}
        }
        """
        time_within = int(request.args['within']) if 'within' in request.args else 0
        module_name = request.args['module'] if 'module' in request.args else None
        logger.info("get all files for all modules")
        with self._lock:
            all_files = self._get_module_files_within(module_name, time_within)
            return Response(json.dumps(all_files), status=200, mimetype='application/json')

    def update_files(self):
        """
        update the local times
        :return: a tuple
        """
        logger.info("force to reload the local files")
        th = threading.Thread(target=self._retrieve_files, kwargs={"force": True})
        th.daemon = True
        th.start()
        return "reload the files", 200

    def _get_module_files_within(self, module_name, time_within):
        """
        get all the files within the time
        :param module_name: the name of module
        :param time_within: the time in seconds
        :return: a dict whose file last modified time are within the time_within seconds
        """
        all_files = {}
        min_change_time = time.time() - time_within
        for tmp_module_name in self.files:
            if module_name is not None and tmp_module_name != module_name:
                continue
            if time_within <= 0:
                logger.info("get all files of module:{}".format(tmp_module_name))
                all_files.update(self.files[tmp_module_name])
            else:
                time_format = '%Y-%m-%d %H:%M:%S'
                logger.info("get files of module {} whose time is greater than {}".format(tmp_module_name,
                                                                                          time.strftime(time_format,
                                                                                                        time.localtime(
                                                                                                            min_change_time))))
                if 'files' in self.files[tmp_module_name]:
                    module_files = self.files[tmp_module_name]['files']
                    all_files['files'] = dict([item for item in module_files.items() if item[1][1] > min_change_time])
                if 'backups' in self.files[tmp_module_name]:
                    module_files = self.files[tmp_module_name]['backups']
                    all_files['backups'] = dict([item for item in module_files.items() if item[1][1] > min_change_time])

        return all_files

    def download_file(self):
        """
        process download file request from http client

        :return: the file content response object
        """
        if 'file' not in request.args:
            return "Missing file parameter", 404
        name = request.args['file']
        filename = self._get_download_file_abspath(name)
        if filename is None or not os.path.exists(filename):
            return "Not found", 404
        try:
            r = flask.send_file(filename)
            event_stat.clear("send_file_failure")
            return r
        except Exception as ex:
            logger.error("Fail to send file {} with error {}".format(filename, ex))
            event_stat.increase("send_file_failure")
            raise ex

    def async_push_file(self):
        """
        process the async push request from http client

        the async push request will not push the required files to the client immediately. The request
        will be put to a queue and then the server will get the push request from the queue and finally
        send the file content to the client
        """
        files = json.loads(request.data)
        logger.info("{} files are asked to push".format(len(files)))
        push_requests = []
        for item in files:
            url = item['url']
            filename = item['file']
            push_request = {"filename": self._get_download_file_abspath(filename),
                            "url": '{}?file={}'.format(url, filename)}
            push_requests.append(push_request)
        if self.async_push.add_requests(push_requests):
            return "schedule for push", 200
        else:
            return "the pending queue is full", 500

    def _get_download_file_abspath(self, name):
        """
        get the absolute path of the name
        """
        for module_name in self.module_files:
            path = self.module_files[module_name].get_abspath(name)
            if path is not None:
                return path
        return None

    def _start_file_retrieve(self):
        while True:
            self._retrieve_files()
            time.sleep(10)

    def _retrieve_files(self, force=False):
        """
        start to retrieve the files according to the configuration

        :param force: True to update the files immediately
        """
        files = {}
        for module_name in self.module_files:
            files[module_name] = self.module_files[module_name].update_files(force)

        with self._lock:
            self.files = files


def load_server_file_config(filename):
    """
    load the file configuration in following .json format

    [
      {
        "name": "the module name",
        "dir": "the file directory",
        "backup-dir": "/test-backup",
        "recursive": true,
        "modified-before": 120,
        "include-patterns": [ ".+\\.txt"],
        "exclude-patterns": [ ".+\\.tmp"],
        "update-interval": 300
      },
      {
        "name": "the module name",
        "dir": "the file directory",
        "backup-dir": "/test-backup",
        "recursive": true,
        "modified-before": 120,
        "include-patterns": [ ".+\\.txt"],
        "exclude-patterns": [ ".+\\.tmp"],
        "update-interval": 300
      }
    ]
    """
    with open(filename) as fp:
        return json.load(fp)


def run_server(args):
    replicate_server = ReplicateServer(load_server_file_config(args.file_config))
    app = flask.Flask(__name__)
    app.add_url_rule("/list", "list", replicate_server.get_files, methods=['GET'])
    app.add_url_rule("/update", "update", replicate_server.update_files, methods=["PUT", "POST"])
    app.add_url_rule("/download", "download", replicate_server.download_file, methods=['GET'])
    app.add_url_rule("/async_push", "async_push", replicate_server.async_push_file, methods=['POST'])
    app.add_url_rule("/healthz", "healthz", check_health, methods=["GET"])
    app.run(host=args.host, port=int(args.port), threaded=True, debug=True, use_reloader=False)


def load_push_config(filename):
    """
    load the push configuration in following .json format:

    [
      { "name": "the module name",
        "dir": "/test",
        "recursive": true,
        "backup-dir": "/backup",
        "unremovable-dirs": [ "/test/test1"]
      },
      { "name": "the module name",
        "dir": "the file directory",
        "recursive": false,
        "backup-dir": "/backup",
        "unremovable-dirs": [ "/test/test1"]
      }
    ]
    """
    with open(filename) as fp:
        return json.load(fp)


class PushServer:
    """
    A push server will be started in the client side to accept the file push operation from the server side
    """

    def __init__(self, push_host, push_port, module_files, notifier):
        """
        create a push server
        :param push_host: the listening host/ip
        :param push_port: the listening port
        :param notifier:
        """
        self.push_host = push_host
        self.push_port = push_port
        self.module_files = module_files
        self.notifier = notifier

    def start(self):
        app = flask.Flask(__name__)
        app.add_url_rule("/save", "save", self._save_file, methods=['POST'])
        app.add_url_rule("/healthz", "healthz", check_health, methods=['GET'])
        app.run(host=self.push_host, port=self.push_port, threaded=True, debug=True, use_reloader=False)

    def _save_file(self):
        """
        process the file save request from the server side
        :return: save the file to local disk
        """
        if 'file' not in request.args:
            return "Missing file parameter", 404

        filename = request.args['file']
        filename = self._get_save_file(filename)

        if filename is None:
            return "Fail to save file %s" % request.args['file'], 404

        if request.headers.get('FileNotExist') is not None:
            logger.error("find FileNotExist header for {}".format(filename))
            self._notify_file_saved(request.args['file'])
            return "succeed"

        last_access_time = float(request.headers.get("FileLastAccessTime"))
        last_modified_time = float(request.headers.get("FileLastModifiedTime"))
        op_name = "save_file_{}".format(filename)
        operation_monitor.add_operation(op_name, 600)
        save_success = self._save_request_stream_to_file(request.stream, filename, last_access_time, last_modified_time)
        operation_monitor.remove_operation(op_name)

        self._notify_file_saved(request.args['file'])
        if save_success:
            event_stat.clear("save_file_failure")
            return "succeed to save file"
        else:
            event_stat.increase("save_file_failure")
            return 500, "Fail to save file"

    def _get_save_file(self, filename):
        """
        get the saved file name
        :param filename: the filename like "/module/file" format
        :return: the real local file name
        """
        elements = split_path(filename)
        if len(elements) > 0:
            module_name = elements[0]
            if module_name in self.module_files:
                return self.module_files[module_name].get_abspath(filename)
        return None

    @classmethod
    def _save_request_stream_to_file(cls, stream, filename, last_access_time, last_modified_time):
        """
        save the data in the request to local file
        :param stream: the stream contains the file data
        :param filename: the local file name
        :param last_access_time: the file last access time
        :param last_modified_time: the file last modified time
        :return: True if save the request data to file successfully
        """
        dirname = os.path.dirname(filename)
        try:
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            with open(filename, "wb") as fp:
                shutil.copyfileobj(stream, fp)

            os.utime(filename, (last_access_time, last_modified_time))

            logger.info("succeed to save module file %s to real file %s" % (request.args['file'], filename))
            return True
        except Exception as ex:
            logger.error("Fail to save to file {} with error:{}".format(filename, ex))
        return False

    def _notify_file_saved(self, filename):
        if self.notifier is not None:
            self.notifier(filename)


class ReplicateServersDiscover:
    __metaclass__ = ABCMeta

    @abstractmethod
    def get_servers(self):
        """
        :return: a list of (ip, port) tuples
        """
        raise NotImplementedError()


class ScriptReplicateServersDiscover(ReplicateServersDiscover):
    def __init__(self, script=None):
        self.script = script

    def get_servers(self):
        """
        get the server names by running the script.

        the script should output servers with following json format:

        [
          [ "server-1": "port-1"],
          [ "server-2": "port-2"],
          [ "server-3": "port-3"]
        ]
        Return:
            list of (ip,port) tuples
        """
        try:
            output = subprocess.check_output([self.script], stderr=subprocess.STDOUT).decode()
            return json.loads(output)
        except Exception as ex:
            logger.error("fail to run the script {} to find server with error:{}".format(self.script, ex))
        return []


class ServiceReplicateServersDiscover(ReplicateServersDiscover):
    """
        find servers by Service name
    """

    def __init__(self, service_name, port):
        self.service_name = service_name
        self.port = port

    def get_servers(self):
        """
        get the list of addresses
        :return: a list of (ip,port) tuples
        """
        try:
            addresses = set()
            for info in socket.getaddrinfo(self.service_name, 0):
                addresses.add((info[-1][0], self.port))
            return list(addresses)
        except Exception as ex:
            logger.error("Fail to get the address by service name {} with error:{}".format(self.service_name, ex))
        return []


class ConfigFileReplicateServersDiscover(ReplicateServersDiscover):
    """
        find servers from configuration file
    """

    def __init__(self, config_file):
        self.config_file = config_file

    def get_servers(self):
        """
        get the list of addresses from the configuration file

        :return: a list of (ip, port) tuples
        """
        try:
            with open(self.config_file) as fp:
                return json.load(fp)
        except Exception as ex:
            logger.error("Fail to get servers from file {} with error:{}".format(self.config_file, ex))
            return []


class FixedHostServersDiscover(ReplicateServersDiscover):
    """
        find servers from configuration file
    """

    def __init__(self, hosts):
        self._hosts = []
        for host_port in hosts.split(","):
            pos = host_port.rfind(':')
            if pos != -1:
                self._hosts.append((host_port[0:pos], int(host_port[pos + 1:])))

    def get_servers(self):
        """
        get the list of addresses from the configuration file

        :return: a list of (ip, port) tuples
        """
        return self._hosts


class ExcludeReplicateServersDiscover(ReplicateServersDiscover):
    def __init__(self, server_discover, exclude_ips):
        self._server_discover = server_discover or []
        self._exclude_ips = exclude_ips or []

    def get_servers(self):
        """
        :return: a list of (ip, port) tuples which exclude the ip in self._exclude_ips
        """
        servers = self._server_discover.get_servers()

        return [server for server in servers if server[0] not in self._exclude_ips]


class EmptyReplicateServersDiscover(ReplicateServersDiscover):
    def get_servers(self):
        """
        :return: a empty list of tuples
        """
        return []


class BackupFiles:
    def __init__(self, backup_files, only_base_compare):
        self._only_base_compare = only_base_compare
        self._backup_files = {}
        self.add_files(backup_files)

    def add_files(self, backup_files):
        for f in backup_files:
            if self._only_base_compare:
                self._backup_files[os.path.basename(f)] = backup_files[f]
            else:
                self._backup_files[f] = backup_files[f]

    def exist(self, file):
        if self._only_base_compare:
            return os.path.basename(file) in self._backup_files
        else:
            return file in self._backup_files

    def __len__(self):
        return len(self._backup_files)


class ReplicateClient:
    def __init__(self,
                 replicate_servers_discover,
                 push_host,
                 push_port,
                 module_files,
                 unremovable_dirs,
                 backup_only_base_compare,
                 time_within):
        """
        init a ReplicateClient with parameters

        Args:
        replicate_servers_discover - find replication servers
        push_host - the listening ip address used to receive the files pushed from master
        push_port - the listening port number
        module_files - the modules will be replicated to this node from master
        backup_only_base_compare - true if compare the basename part for backup files
        """
        self.replicate_servers_discover = replicate_servers_discover
        self.push_host = push_host
        self.push_port = push_port
        self.module_files = module_files
        self.unremovable_dirs = unremovable_dirs or []
        self.backup_only_base_compare = backup_only_base_compare
        self.time_within = time_within

    def start_replicate(self):
        """
        start to do the replication from all the servers
        """
        while True:
            sleep_seconds = []
            servers = self.replicate_servers_discover.get_servers()

            if servers is None or len(servers) <= 0:
                logger.info("No replicate server is available")
                time.sleep(10)
                continue
            for server in servers:
                server_name = server[0]
                server_port = server[1]
                for module_name in self.module_files:
                    try:
                        if self._replicate_module(server_name, server_port, module_name) <= 0:
                            sleep_seconds.append(10)
                        else:
                            sleep_seconds.append(0)
                    except Exception as ex:
                        logger.error(
                            "Fail to replicate files from server {}:{} to local with error:{} in module {}".format(
                                server_name, server_port, ex, module_name))
                        sleep_seconds.append(10)

            time.sleep(min(sleep_seconds))

    def _replicate_module(self, server, server_port, module_name):
        """
        replicate modules files from remote server
        :param server: the server
        :param server_port: the server port
        :param module_name: the module name
        :return: number of replicated files
        """

        op_name = "download_files_from_{}".format(module_name)
        operation_monitor.add_operation(op_name, 600)
        remote_files = self._download_module_files(server, server_port, module_name)
        operation_monitor.remove_operation(op_name)
        # don't do anything if fail to download the remote module files
        if remote_files is None:
            logger.info("no remote files downloaded from server {}:{}".format(server, server_port))
            return 0
        else:
            logger.info(
                "in module {}, \n\tnumber of remote files is {}, "
                "\n\tnumber of remote backup files is {}".format(module_name,
                                                                 len(remote_files['files']),
                                                                 len(remote_files['backups'])))
            local_files = self.module_files[module_name].update_files()
            logger.info(
                "in module {}, \n\tnumber of local files is {}, \n\tnumber of local backup files is {}".format(
                    module_name, len(
                        local_files['files']), len(local_files['backups'])))
            backup_files = BackupFiles(remote_files['backups'], self.backup_only_base_compare)
            local_backup_files = BackupFiles(local_files['backups'], self.backup_only_base_compare)

            new_files = {}
            remote_in_local_backups = 0
            remote_in_remote_backups = 0
            existing_in_local = 0
            for f in remote_files['files']:
                # if the remote file is in the deleted path, don't replicate it
                if local_backup_files.exist(f):
                    remote_in_local_backups += 1
                    logger.debug(
                        "the remote file {} is in local backup directory already, no download is needed".format(f))
                    continue
                if backup_files.exist(f):
                    remote_in_remote_backups += 1
                    logger.debug(
                        "the remote file {} is in remote backup directory already, no download is needed".format(f))
                    continue

                # if the remote file exists in the local directory
                if f in local_files['files'] and local_files["files"][f][0] >= remote_files["files"][f][0]:
                    existing_in_local += 1
                    logger.debug("the remote file {} is in local directory already, no download is needed".format(f))
                else:
                    new_files[f] = remote_files['files'][f]
                    if f not in local_files["files"]:
                        logger.info("the remote file {} is not in local directory, download it".format(f))
                    else:
                        logger.info("the size of file {} in remote is bigger than in local, "
                                    "local size is {}, remote size is {}".format(f,
                                                                                 local_files["files"][f][0],
                                                                                 remote_files["files"][f][0]))

            logger.info(
                "in module {}, \n\tnumber of remote files is {}, \n\tnumber of local files is {}, \n\tnumber of remote files in "
                "local backups is {}, \n\tnumber of remote files in remote backups is {}, \n\tnumber of remote files in local "
                "is {}, \n\tnumber of new files is {}, \n\t"
                "number of remote backup files is {}".format(
                    module_name, len(remote_files['files']), len(local_files['files']), remote_in_local_backups,
                    remote_in_remote_backups, existing_in_local, len(new_files), len(backup_files)))
            self._delete_files(local_backup_files, local_files['files'])
            self._delete_files(backup_files, local_files['files'])
            op_name = "download_files_from_{}".format(server)
            operation_monitor.add_operation(op_name, 3600)
            downloaded_files = self._download_files(server, server_port, new_files)
            operation_monitor.remove_operation(op_name)
            if downloaded_files > 0:
                logger.info("totally download {} files in module {} to local".format(downloaded_files, module_name))
            return downloaded_files

    def _delete_files(self, backup_files, local_files):
        """
        delete the backup files from local
        :param backup_files: the backup_files files
        :param local_files: the local files
        :return:
        """
        dirs = set()
        for f in local_files:
            if backup_files.exist(f):
                try:
                    module_name = self._get_module_name(f)
                    filename = self.module_files[module_name].get_abspath(f)
                    dirs.add(os.path.dirname(filename))
                    if os.path.exists(filename):
                        logger.info("remove local file {} because it is already backup".format(filename))
                        os.remove(filename)
                except Exception as ex:
                    logger.error("Fail to remove file {} with error:{}".format(f, ex))
        for f in dirs:
            try:
                if not os.path.isdir(f):
                    logger.info("directory {} is already deleted".format(f))
                    continue
                if f in self.unremovable_dirs:
                    logger.info("{} is unremovable dir".format(f))
                    continue
                if not os.listdir(f):
                    os.rmdir(f)
                    logger.info("remove the directory {} successfully because it is empty".format(f))
            except Exception as ex:
                logger.error("Fail to check if directory {} is empty with error ".format(f, ex))

    def _download_files(self, server, server_port, files):
        """
        download the remote files to local
        """
        url = "http://{}:{}/save".format(self.push_host, self.push_port)
        pushed_files = []
        pushed_files_info = {}
        for file in files:
            pushed_files.append({"url": url, "file": file})
            pushed_files_info[file] = files[file]
            if len(pushed_files) == 1000:
                break
        try:
            req = Request("http://{}:{}/async_push".format(server, server_port),
                          data=json.dumps(pushed_files).encode(),
                          headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=600)
            if resp.getcode() / 100 not in (2, 3):
                logger.error("fail to download files with status code {}".format(resp.getcode()))
                return 0
        except Exception as ex:
            logger.error("Fail to download files with error {}".format(ex))
            return 0

        downloaded_files = 0

        for f in pushed_files_info:
            try:
                if self._wait_file_downloaded(f, pushed_files_info[f][0], 300):
                    downloaded_files += 1
            except Exception as ex:
                logger.error("Fail to wait file {} download with error {}".format(f, ex))

        return downloaded_files

    @classmethod
    def _touch_file(cls, filename):
        """
        touch a file
        """
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filename, "a"):
            pass

    def _wait_file_downloaded(self, name, size, timeout):
        """
        wait the file download

        :param name: the file name
        :param size: the file size
        :param timeout: the wait timeout in seconds

        :return: True if the file is downloaded successfully
        """
        timeout_time = time.time() + timeout
        while timeout_time > time.time():
            if self._is_file_downloaded(name, size):
                return True
            time.sleep(0.01)
        return False

    def _is_file_downloaded(self, name, size):
        """

        :param name: the file to be downloaded
        :param size: the file size
        :return: True if the file is downloaded
        """
        module_name = self._get_module_name(name)
        downloaded_file_size = self.module_files[module_name].get_size(name)

        # if get FileNotExist(downloaded_file_size<0) response
        # or the downloaded size is not less than expectation
        return downloaded_file_size < 0 or downloaded_file_size >= size

    def _get_real_filename(self, filename):
        """
        get the real filename
        """
        elements = split_path(filename)
        if len(elements) > 0:
            for module_name in self.module_files:
                item = self.module_files[module_name]
                if elements[0] == item.get_module_name():
                    return os.path.join(item.path, *elements[1:])
        return None

    def _download_module_files(self, server, server_port, module_name):
        """
        downlolad all files in one module

        :param server: the replication server name or ip
        :param server_port: the replication server port number
        :param module_name: the module name
        """
        if self.time_within is None or self.time_within <= 0:
            url = "http://{}:{}/list?module={}".format(server, server_port, module_name)
        else:
            url = "http://{}:{}/list?module={}&within={}".format(server, server_port, module_name, self.time_within)
        try:
            logger.info("start to download module files from {}".format(url))
            resp = urlopen(url, timeout=300)
            if resp.getcode() / 100 in (2, 3):
                data = resp.read()
                return json.loads(data)
        except Exception as ex:
            logger.error("fail to download files from {} in module {}:{}".format(url, module_name, ex))
        return None

    @classmethod
    def _get_module_name(cls, name):
        """
        get the module name
        """
        return split_path(name)[0]

    def file_pushed(self, name):
        """
        a file is pushed to local system
        """
        module_name = self._get_module_name(name)
        if module_name in self.module_files:
            module_file = self.module_files[module_name]
            module_file.file_added(name)

    def is_unremovable_dir(self, path):
        return os.path.abspath(path) in self.unremovable_dirs


def create_module_files_from_push_config(push_config):
    """
    create the module files from the push configuration
    :param push_config:
    :return:
    """
    module_files = {}
    for item in push_config:
        name = item['name']
        recursive = item['recursive'] if 'recursive' in item else False
        backup_dir = item['backup-dir'] if 'backup-dir' in item else None
        module_files[name] = ModuleFiles(name, item['dir'], recursive, backup_dir, None, None, 0, 0)
    return module_files


def create_replicate_server_discovery(server_discovery):
    """
    create a ReplicateServersDiscover object
    :param server_discovery: with one of following formats:
    - service:<service-name>:<port>
    - script:<script-name>
    - file:<config-file>
    - host: host1:port1,host2:port2
    :return: a specific ReplicateServersDiscover instance
    """
    if server_discovery.startswith("service:"):
        s = server_discovery[len("service:"):]
        pos = s.rfind(':')
        port = int(s[pos + 1:])
        service_name = s[0:pos]
        return ServiceReplicateServersDiscover(service_name, port)
    elif server_discovery.startswith("script:"):
        script = server_discovery[len("script:"):]
        return ScriptReplicateServersDiscover(script)
    elif server_discovery.startswith("file:"):
        config_file = server_discovery[len("file:"):]
        return ConfigFileReplicateServersDiscover(config_file)
    elif server_discovery.startswith("host:"):
        hosts = server_discovery[len("host:"):]
        return FixedHostServersDiscover(hosts)
    else:
        logger.error("Unknown server discovery string:{}".format(server_discovery))
    return EmptyReplicateServersDiscover()


def get_unremovable_dirs_from_push_config(push_config):
    unremovable_dirs = []
    for item in push_config:
        if 'unremovable-dirs' in item:
            for f in item['unremovable-dirs']:
                unremovable_dirs.append(os.path.abspath(f))
    return unremovable_dirs


def to_seconds(s):
    n = int(len(s))
    if s.endswith('d'):
        return int(s[0:n - 1]) * 24 * 3600
    elif s.endswith('h'):
        return int(s[0:n - 1]) * 3600
    elif s.endswith('w'):
        return int(s[0:n - 1]) * 7 * 24 * 3600
    elif s.endswith('m'):
        return int(s[0:n - 1]) * 60
    elif s.endswith("s"):
        return int(s[0:n - 1])
    else:
        return int(s)


def run_client(args):
    """
    load as client
    """
    push_config = load_push_config(args.push_config)
    module_files = create_module_files_from_push_config(push_config)
    unremovable_dirs = get_unremovable_dirs_from_push_config(push_config)
    time_within = to_seconds(args.replicate_within) if args.replicate_within is not None else 0

    time.sleep(2)
    replicate_server_discover = create_replicate_server_discovery(args.server_discovery)
    replicate_server_discover = ExcludeReplicateServersDiscover(replicate_server_discover, args.exclude_server)

    replicate_client = ReplicateClient(replicate_server_discover,
                                       args.push_host,
                                       args.push_port,
                                       module_files,
                                       unremovable_dirs,
                                       args.backup_only_base_compare,
                                       time_within)
    push_server = PushServer(args.push_host,
                             args.push_port,
                             module_files,
                             replicate_client.file_pushed)
    th = threading.Thread(target=replicate_client.start_replicate)
    th.daemon = True
    th.start()
    push_server.start()


def parse_args():
    """
    parse the command line arguments
    :return: the parsed arguments
    """
    parser = argparse.ArgumentParser(description="replicate files between the nodes")
    subparsers = parser.add_subparsers(help="sub-commands")

    server_parser = subparsers.add_parser("server",
                                          help="run as a server")
    server_parser.add_argument("--host",
                               help="the host/ip address to listen, default is 0.0.0.0",
                               default="0.0.0.0",
                               required=False)
    server_parser.add_argument("--port",
                               help="the listening port number, default is 5000",
                               default=5000,
                               type=int,
                               required=False)
    server_parser.add_argument("--file-config",
                               help="the file configuration in .json format",
                               required=True)
    server_parser.add_argument("--log-file",
                               help="the log filename",
                               required=False)
    server_parser.add_argument("--log-level",
                               help="the log level, default is INFO",
                               choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                               default="INFO")
    server_parser.add_argument("--log-format",
                               help="the log format",
                               choices=["text", "json"],
                               default="text")
    server_parser.set_defaults(func=run_server)

    client_parser = subparsers.add_parser("client", help="run as a client")
    client_parser.add_argument("--push-host",
                               help="async push host name or ip address, default is 0.0.0.0",
                               required=False,
                               default="0.0.0.0")
    client_parser.add_argument("--push-port",
                               help="async push port number, default is 5000",
                               required=False,
                               type=int,
                               default=5000)
    client_parser.add_argument("--push-config",
                               help="the push configuration in .json format",
                               required=True)
    client_parser.add_argument("--backup-only-base-compare",
                               help="only compare the basename for the backup",
                               default=True,
                               type=bool)
    client_parser.add_argument("--server-discovery",
                               help="the server discovery",
                               required=True)
    client_parser.add_argument("--exclude-server",
                               help="the excluded server IP address",
                               nargs="*")
    client_parser.add_argument("--replicate-within",
                               help="replicate all files within 1d/1h/1m/10")
    client_parser.add_argument("--log-file",
                               help="the log filename",
                               required=False)
    client_parser.add_argument("--log-level",
                               help="the log level, default is INFO",
                               choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                               default="INFO")
    client_parser.add_argument("--log-format",
                               help="the log format",
                               choices=["text", "json"],
                               default="text")
    client_parser.set_defaults(func=run_client)

    return parser.parse_args()


def init_logger(log_file, log_level, log_format):
    if log_file is None:
        handler = logging.StreamHandler(stream=sys.stdout)
    else:
        handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=50 * 1024 * 1024, backupCount=10)

    if log_format == "json":
        try:
            from pythonjsonlogger import jsonlogger
            formatter = jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s", timestamp=True)
        except Exception as ex:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.setLevel(log_level)
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    flask_logger = logging.getLogger('werkzeug')
    flask_logger.setLevel(logging.DEBUG)
    flask_logger.addHandler(handler)


def disable_flask_banner():
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None


def main():
    args = parse_args()
    disable_flask_banner()
    init_logger(args.log_file, args.log_level, args.log_format)
    args.func(args)


if __name__ == "__main__":
    main()
