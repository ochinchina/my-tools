"""
Migrate the maven libraries from one repository to another based on the maven plugin deploy:deploy-file

Except for the tool maven and its plugin deploy:deploy-fule, this script requires following python3 modules:
- requests
- bs4
- lxml

"""
import argparse
import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Union, Dict

import requests
from bs4 import BeautifulSoup
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("maven-migrate")


def version_cmp(version_1: Union[str, dict], version_2: Union[str, dict]):
    if isinstance(version_1, dict):
        version_1 = version_1['text']
    if isinstance(version_2, dict):
        version_2 = version_2['text']

    version_1 = version_1.split(".")
    version_2 = version_2.split(".")
    n = min(len(version_1), len(version_2))
    for i in range(n):
        if version_1[i] == version_2[i]:
            continue
        if version_1[i].isdigit() and version_2[i].isdigit():
            return int(version_1[i]) - int(version_2[i])
        return -1 if version_1[i] < version_2[i] else 1
    if len(version_1) == len(version_2):
        return 0
    elif len(version_1) < len(version_2):
        return -1
    else:
        return 1


class LibVersionMgr:
    def __init__(self):
        self._versions = {}

    def add_versions(self, groupId: str, artifactId: str, versions: List[Dict]):
        """
        add versions to the manager
        :param groupId: the groupId
        :param artifactId: the artifactId
        :param versions: the versions is a list like:
        [
            {"version": "1.0.0", "url": "http://test.com/com/test/my-lib/1.0.0"},
            {"version": "1.0.1", "url": "http://test.com/com/test/my-lib/1.0.1"}
        ]
        :return:
        """
        if groupId not in self._versions:
            self._versions[groupId] = {}
        self._versions[groupId][artifactId] = versions

    def get_groups(self) -> List[str]:
        return [groupId for groupId in self._versions]

    def get_artifacts(self, groupId: str) -> List[str]:
        return [artifactId for artifactId in self._versions[groupId]] if groupId in self._versions else []

    def get_versions(self, groupId: str, artifactId: str) -> List[Dict]:
        if groupId not in self._versions:
            return []
        if artifactId not in self._versions[groupId]:
            return []
        return self._versions[groupId][artifactId]

    def get_version(self, groupId: str, artifactId: str, version: str) -> Dict[str, str]:
        versions = self.get_versions(groupId, artifactId)
        r = [item for item in versions if item['version'] == version]
        return r[0] if len(r) == 1 else {}

    def exist_version(self, groupId: str, artifactId: str, version: str) -> bool:
        """
        check if the version exist
        :param groupId: the groupId
        :param artifactId: the artifactId
        :param version: the version
        :return: True if the version exists already
        """
        versions = self.get_versions(groupId, artifactId)
        return len([item for item in versions if item['version'] == version]) > 0

    def __repr__(self):
        return json.dumps(self._versions)


class MavenSettings:
    def __init__(self, setting_xml_file="settings.xml"):
        self._setting_xml_file = setting_xml_file
        self._repo_ids = []

    @classmethod
    def _escape(cls, s):
        s = s.replace("&", "&amp;")
        s = s.replace("<", "&lt;")
        s = s.replace(">", "&gt;")
        s = s.replace("\"", "&quot;")
        return s

    def add_repo_id(self, repoId, username, password):
        self._repo_ids.append({"repoId": self._escape(repoId),
                               "username": self._escape(username),
                               "password": self._escape(password)})

    def create(self):
        content = ['<?xml version="1.0"?>',
                   '<settings>',
                   '\t<servers>'
                   ]

        for item in self._repo_ids:
            repoId, username, password = item['repoId'], item['username'], item['password']
            content.extend(['\t\t<server>',
                            '\t\t\t<id>{}</id>'.format(repoId),
                            '\t\t\t<username>{}</username>'.format(username),
                            '\t\t\t<password>{}</password>'.format(password),
                            '\t\t</server>'])

        content.extend(['\t</servers>',
                        '</settings>'])
        with open(self._setting_xml_file, "w") as fp:
            fp.write("\n".join(content))


class MavenLibBrowser:
    def __init__(self, url: str, groupId: str):
        self._url = url
        self._groupId = groupId

    def get_all_libraries(self) -> LibVersionMgr:
        urls = [self._url]
        result = LibVersionMgr()
        while len(urls) > 0:
            url = urls.pop(0)
            if not url.endswith('/'):
                url = "{}/".format(url)

            try:
                resp = requests.get(url)
                soup = BeautifulSoup(resp.text, "lxml")
                # extact all files under this URL
                files = self._extract_files(url, soup)
                maven_metadata_xml_info = self._find_maven_metadata_xml(files)
                if maven_metadata_xml_info is None:
                    urls.extend([item['url'] for item in files])
                else:
                    artifactId = [item for item in url.split('/') if len(item) != 0][-1]
                    versions = []
                    for f in files:
                        if not f['text'].startswith('maven-metadata.xml'):
                            versions.append({"version": f['text'], 'url': f['url']})
                    result.add_versions(self._groupId, artifactId, versions)
            except Exception as ex:
                logger.error("fail to get maven libraries under {} with error {}".format(url, ex))
        return result

    def get_url(self) -> str:
        return self._url

    @classmethod
    def download_lib_files(cls, url):
        files = cls.get_lib_files(url)
        if len(files) == 0:
            return []

        result = []
        d = tempfile.mkdtemp()
        for f in files:
            filename = os.path.join(d, f['text'])
            if not cls._download_file(f['url'], filename):
                logger.error("fail to download file from {} to {}".format(f['url'], filename))
                return []
            else:
                logger.info("succeed to download file from {} to {}".format(f['url'], filename))
                result.append(filename)
        return result

    @classmethod
    def get_lib_files(cls, url):
        result = []
        packagings = [".jar", ".war", ".pom", ".zip"]

        try:
            resp = requests.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            # extact all files under this URL
            files = cls._extract_files(url, soup)
            for f in files:
                text = f['text']
                for name in packagings:
                    if text.endswith(name):
                        result.append(f)
        except Exception as ex:
            logger.error("fail to get lib files from {} with error:{}".format(url, ex))

        return result

    @classmethod
    def _download_file(cls, url, filename):
        """
        download a file from url and write its content to filename
        :param url: the url to download the file content
        :param filename: the local file name
        :return: True if download is successful
        """

        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(filename, "wb") as fp:
                    for chunk in r.iter_content(chunk_size=8192):
                        fp.write(chunk)
                return True
        except Exception as ex:
            logger.error("fail to download from {} to local file {} with error:{}".format(url, filename, ex))
        return False

    @classmethod
    def _extract_files(cls, url: str, soup: BeautifulSoup):
        files = []
        for link in soup.find_all('a'):
            # remove last '/' from the text
            text = link.get_text()
            if text.endswith("/"):
                text = text[0:-1]
            href = link.get('href')
            if text != '..' and href.find('..') == -1:
                files.append({"text": text, "url": "{}{}".format(url, href)})
        return cls._sort_files(files)

    @classmethod
    def _find_maven_metadata_xml(cls, files):
        maven_metadata_files = [item for item in files if item['text'] == 'maven-metadata.xml']
        return maven_metadata_files[0] if len(maven_metadata_files) == 1 else None

    @classmethod
    def _sort_files(cls, files):
        folders = [item for item in files if "url" in item]
        r = list(sorted(folders, key=functools.cmp_to_key(version_cmp)))
        return r


class Maven:
    def __init__(self, repo_url, repo_id):
        self._repo_url = repo_url
        self._repo_id = repo_id

    def deploy(self, files: List[str]):
        """
        deploy the files to the maven repo
        :param files:
        :return:
        """

        groupId, artifactId, version, packaging, pom_file, package_files, source_file, java_doc_file = self._create_deploy_params(
            files)
        package_file = self._get_package_file(package_files, artifactId, version, packaging)
        if groupId is None:
            return

        command = ["mvn",
                   "deploy:deploy-file",
                   "-Durl={}".format(self._repo_url),
                   "-DrepositoryId={}".format(self._repo_id),
                   "-DgroupId={}".format(groupId),
                   "-DartifactId={}".format(artifactId),
                   "-Dversion={}".format(version),
                   "-DpomFile={}".format(pom_file),
                   "-Dfile={}".format(package_file),
                   "-Dpackaging={}".format(packaging)]

        files, classifiers = self._get_package_with_classifiers(package_files, artifactId, version)
        if len(files) > 0 and len(classifiers) > 0:
            command.extend(["-Dfiles={}".format(files), "-Dclassifiers={}".format(classifiers)])

        command.extend(["--settings", "settings.xml"])

        if source_file is not None:
            command.append("-Dsources={}".format(source_file))
        if java_doc_file is not None:
            command.append("-Djavadoc={}".format(java_doc_file))

        logger.info("try to run:{}".format(" ".join(command)))
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT).decode()
            logger.info(output)
        except subprocess.CalledProcessError as ex:
            logger.error(ex.output)
            logger.error("fail to run command {} with error:{}".format(" ".join(command), ex))

    @classmethod
    def _get_package_file(cls, package_files, artifact_id, version, packaging):
        for package_file in package_files:
            if os.path.basename(package_file) == "{}-{}.{}".format(artifact_id, version, packaging):
                return package_file
        return None

    @classmethod
    def _get_package_with_classifiers(cls, package_files, artifact_id, version):
        files = []
        classifiers = []

        for package_file in package_files:
            base_name = os.path.basename(package_file)
            packaging = base_name.split(".")[-1]
            t = "{}-{}".format(artifact_id, version)
            if base_name != "{}.{}".format(t, packaging) and base_name.startswith("{}-".format(t)):
                classifiers.append(base_name[len(t) + 1:-1 * len(packaging) - 1])
                files.append(package_file)
        return ",".join(files), ",".join(classifiers)

    @classmethod
    def _create_deploy_params(cls, files):
        java_doc_file = None
        source_file = None
        pom_file = None
        packaging = "jar"
        package_files = []
        groupId = None
        artifactId = None
        version = None
        packaging_map = {
            "jar": ".jar",
            "war": ".war",
            "zip": ".zip"
        }

        pom_files = [item for item in files if item.endswith(".pom")]
        if len(pom_files) == 1:
            pom_file = pom_files[0]
            groupId, artifactId, version = cls._parse_pom(pom_file)

        for filename in files:
            if filename.endswith("-sources.jar"):
                source_file = filename
            elif filename.endswith("-javadoc.jar"):
                java_doc_file = filename
            else:
                for name in packaging_map:
                    if filename.endswith(packaging_map[name]):
                        packaging = name
                        package_files.append(filename)
                        break

        if groupId is None or artifactId is None or version is None or len(package_files) <= 0 or pom_file is None:
            logger.error("not a valid maven deploy directory with groupId={},artifactId={},version={},package_file={}"
                         ",pom_file={},packaging={}".format(groupId,
                                                            artifactId,
                                                            version,
                                                            package_files,
                                                            pom_file,
                                                            packaging))
            return None, None, None, None, None, None, None, None

        return groupId, artifactId, version, packaging, pom_file, package_files, source_file, java_doc_file

    @classmethod
    def _parse_pom(cls, pom_file):
        with open(pom_file) as fp:
            soup = BeautifulSoup(fp.read(), "xml")
            return soup.find("groupId").get_text(), soup.find("artifactId").get_text(), soup.find("version").get_text()


class MavenLibMigrate:
    def __init__(self, config):
        self._config = config

    def _create_from_lib_browser(self):
        from_config = self._config['from']

        return MavenLibBrowser(from_config['url'], from_config['groupId'])

    def _create_to_lib_browser(self):
        to_config = self._config['to']
        return MavenLibBrowser(to_config['url'], to_config['groupId'])

    def _create_maven_settings(self):
        to_config = self._config['to']
        maven_settings = MavenSettings("settings.xml")
        repoId, user, password = to_config['repoId'], to_config['user'], to_config['password']
        maven_settings.add_repo_id(repoId, user, password)
        maven_settings.create()

    def _create_maven(self):
        to_config = self._config['to']
        return Maven(to_config['url'], to_config['repoId'])

    def compare(self):
        from_lib_browser = self._create_from_lib_browser()
        to_lib_browser = self._create_to_lib_browser()

        logger.info(
            "start to compare the libs between {} and {}".format(from_lib_browser.get_url(), to_lib_browser.get_url()))

        from_lib_versions = from_lib_browser.get_all_libraries()
        to_lib_versions = to_lib_browser.get_all_libraries()
        different_number = 0
        missing_number = 0
        for groupId in from_lib_versions.get_groups():
            for artifactId in from_lib_versions.get_artifacts(groupId):
                for version in from_lib_versions.get_versions(groupId, artifactId):
                    from_lib_files = from_lib_browser.get_lib_files(version['url'])
                    if to_lib_versions.exist_version(groupId, artifactId, version['version']):
                        to_version_info = to_lib_versions.get_version(groupId, artifactId, version['version'])
                        to_lib_files = to_lib_browser.get_lib_files(to_version_info['url'])
                        if len(from_lib_files) != len(to_lib_files):
                            logger.info("different library {}:{}:{}".format(groupId, artifactId, version['version']))
                            different_number += 1
                    else:
                        logger.info("missing library {}:{}:{}".format(groupId, artifactId, version['version']))
                        missing_number += 1
        if different_number == 0 and missing_number == 0:
            logger.info("totally same between the two repositories")

        logger.info("finish to compare two repositories")

    def migrate(self):
        maven = self._create_maven()
        self._create_maven_settings()

        from_lib_browser = self._create_from_lib_browser()
        to_lib_browser = self._create_to_lib_browser()

        from_lib_versions = from_lib_browser.get_all_libraries()
        to_lib_versions = to_lib_browser.get_all_libraries()

        for groupId in from_lib_versions.get_groups():
            for artifactId in from_lib_versions.get_artifacts(groupId):
                for version in from_lib_versions.get_versions(groupId, artifactId):
                    lib = "{}:{}:{}".format(groupId, artifactId, version['version'])
                    if to_lib_versions.exist_version(groupId, artifactId, version['version']):
                        logger.info("don't migrate {} because it exists already".format(lib))
                    else:
                        logger.info("start to migrate {}".format(lib))
                        files = from_lib_browser.download_lib_files(version['url'])
                        if len(files) > 0:
                            maven.deploy(files)
                            shutil.rmtree(os.path.dirname(files[0]))
        logger.info("finish to migrate all the libraries")


def init_logger(log_file):
    if log_file is None:
        handler = logging.StreamHandler(stream=sys.stdout)
    else:
        handler = RotatingFileHandler(log_file, maxBytes=50 * 1024 * 1024, backupCount=10)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    handler.setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def load_config(config_file):
    """
    load the configuration from the file
    :param config_file: the file name. The file content looks like:
    [{
        "from": {
            "url": "archiva url",
            "groupId": "example.com"
        },
        "to": {
            "url": "the url",
            "user": "the user",
            "password": "the password",
            "repoId": "the repository id",
            "groupId": "example.com"
        }
    }]
    :return: the configuration in dict
    """
    with open(config_file) as fp:
        return json.load(fp)


def migrate_lib(args):
    config = load_config(args.config)
    if isinstance(config, dict):
        MavenLibMigrate(config).migrate()
    elif isinstance(config, list):
        for item in config:
            MavenLibMigrate(item).migrate()


def compare_lib(args):
    config = load_config(args.config)
    if isinstance(config, dict):
        MavenLibMigrate(config).compare()
    elif isinstance(config, list):
        for item in config:
            MavenLibMigrate(item).compare()


def parse_args():
    parser = argparse.ArgumentParser(description="migrate archiva to jfrog")
    subparsers = parser.add_subparsers(description="sub commands")

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--config", help="the configuration file", required=True)
    migrate_parser.add_argument("--log-file", help="the log file name")
    migrate_parser.set_defaults(func=migrate_lib)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--config", help="the configuration file", required=True)
    compare_parser.add_argument("--log-file", help="the log file name")
    compare_parser.set_defaults(func=compare_lib)

    return parser.parse_args()


def main():
    args = parse_args()
    init_logger(args.log_file)
    args.func(args)


if __name__ == "__main__":
    main()
