#!/usr/bin/env python3

import argparse
import hashlib
import os.path
import shutil
import subprocess
import sys
from typing import List


class CommitLog:
    def __init__(self, commit_lines):
        self._commit_id = ""
        self._author = ""
        self._date = ""
        self._change_id = ""
        self._files = []
        self._comments = ""
        self._parse_commit_lines(commit_lines)

    def get_commit_id(self):
        return self._commit_id

    def get_changed_files(self):
        return self._files

    def _parse_commit_lines(self, commit_lines: List[str]):
        for line in commit_lines:
            if line.startswith("commit"):
                self._commit_id = line[len("commit"):].strip()
            elif line.startswith("Author:"):
                self._author = line[len("Author:"):].strip()
            elif line.startswith("Date:"):
                self._date = line[len("Date:"):].strip()
            elif line.startswith(":"):
                self._files.append(line.split()[-1].strip())
            else:
                line = line.strip()
                if line.startswith("Change-Id:"):
                    self._change_id = line[len("Change-Id:"):].strip()
                elif len(line) > 0:
                    if len(self._comments) <= 0:
                        self._comments = line
                    else:
                        self._comments = "{}\n{}".format(self._comments, line)


class GitTool:
    @classmethod
    def get_commit_log(cls, filename=None):
        command = ["git", "log", "--raw"]
        if filename is not None:
            command.append(filename)

        out = subprocess.check_output(command).decode()

        result = []
        commit_lines = []
        for line in out.split("\n"):
            if line.startswith("commit"):
                if len(commit_lines) > 0:
                    result.append(CommitLog(commit_lines))
                commit_lines = []
            commit_lines.append(line)
        return result

    @classmethod
    def find_commit(cls, filename, changed_text):
        result = []
        for commit_log in cls.get_commit_log(filename):
            commit_id = commit_log.get_commit_id()
            command = ['git', 'show', commit_id, filename]
            out = subprocess.check_output(command).decode()
            if out.find(changed_text) != -1:
                result.append(commit_id)
        return result

    @classmethod
    def get_current_branch(cls):
        command = ["git", "branch", "-v"]
        out = subprocess.check_output(command).decode()
        for line in out.split("\n"):
            fields = line.split()
            if len(fields) >= 3 and fields[0] == '*':
                return fields[1]
        return None

    @classmethod
    def checkout(cls, branch_name):
        subprocess.check_output(["git", "checkout", branch_name])


def compute_file_md5(filename):
    md5_object = hashlib.md5()
    block_size = 128 * md5_object.block_size
    with open(filename, "rb") as fp:
        chunk = fp.read(block_size)
        while chunk:
            md5_object.update(chunk)
            chunk = fp.read(block_size)
    return md5_object.hexdigest()


def copy_file(src_file, dest_file=None):
    if dest_file is None:
        with open(src_file, "r") as fp:
            shutil.copyfileobj(fp, sys.stdout)
    else:
        with open(src_file, "rb") as fp:
            with open(dest_file, "wb") as fp2:
                shutil.copyfileobj(fp, fp2)


def find_commit(args):
    print(GitTool.find_commit(args.file, args.text))


def find_changed_files(args):
    for commit_log in GitTool.get_commit_log():
        if commit_log.get_commit_id() == args.commit_id:
            print("\n".join(commit_log.get_changed_files()))


def get_file(args):
    current_branch = GitTool.get_current_branch()
    for commit_log in GitTool.get_commit_log(args.file):
        if commit_log.get_commit_id() == args.commit_id:
            GitTool.checkout(commit_log.get_commit_id())
            if os.path.isfile(args.file):
                copy_file(args.file, args.dest)
    GitTool.checkout(current_branch)


def find_commit_by_file_md5(args):
    filename = args.file
    file_md5 = args.md5
    result = []
    current_branch = GitTool.get_current_branch()
    for commit_log in GitTool.get_commit_log(filename):
        GitTool.checkout(commit_log.get_commit_id())
        if compute_file_md5(filename) == file_md5:
            result.append(commit_log.get_commit_id())
    GitTool.checkout(current_branch)

    print(result)


def parse_args():
    parser = argparse.ArgumentParser(description="git useful tools")

    subparsers = parser.add_subparsers(title="sub commands")
    find_commit_parser = subparsers.add_parser("find-commit")
    find_commit_parser.add_argument("--file", help="the file name")
    find_commit_parser.add_argument("--text", help="the text in the changes", required=True)
    find_commit_parser.set_defaults(func=find_commit)

    find_changed_files_parser = subparsers.add_parser("find-changed-files")
    find_changed_files_parser.add_argument("--commit-id", help="the commit id", required=True)
    find_changed_files_parser.set_defaults(func=find_changed_files)

    get_file_parser = subparsers.add_parser("get-file")
    get_file_parser.add_argument("--commit-id", help="the commit id", required=True)
    get_file_parser.add_argument("--file", help="the file name", required=True)
    get_file_parser.add_argument("--dest", help="the destination file to save")
    get_file_parser.set_defaults(func=get_file)

    find_commit_by_file_md5_parser = subparsers.add_parser("find-commit-by-file-md5")
    find_commit_by_file_md5_parser.add_argument("--file", help="the file name", required=True)
    find_commit_by_file_md5_parser.add_argument("--md5", help="the file md5", required=True)
    find_commit_by_file_md5_parser.set_defaults(func=find_commit_by_file_md5)
    return parser.parse_args()


def main():
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
