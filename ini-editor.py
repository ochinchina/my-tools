#!/usr/bin/python

import argparse
import sys

try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser


class IniEditor:
    def __init__(self, filename):
        self._filename = filename
        self._config = self._load_config(filename)

    @classmethod
    def _load_config(cls, filename):
        config = ConfigParser()
        config.optionxform = str
        config.read(filename)
        return config

    def update(self, section, key, value):
        """
        update the value of key in section if it exists otherwise create section and key
        :param section: the section name
        :param key: the key in the section
        :param value: the value
        :return: None
        """
        if not self._config.has_section(section):
            self._config.add_section(section)

        self._config.set(section, key, value)

    def delete(self, section, key):
        """
        remove key under section if both section and key are not empty,
        remove section if key is None
        :param section: the section
        :param key: the key
        :return: True if removed key or section successfully
        """
        if self._config.has_section(section):
            if key is None:
                self._config.remove_section(section)
                return True
            elif self._config.has_option(section, key):
                self._config.remove_option(section, key)
                return True
        return False

    def save(self, filename=None):
        """
        save the configuration to a filename
        :param filename:
        :return:
        """

        if filename is None:
            self._config.write(sys.stdout)
            return

        with open(filename, "w") as fp:
            self._config.write(fp)


def update_value(args):
    editor = IniEditor(args.filename)
    editor.update(args.section, args.key, args.value)
    editor.save(args.out_filename)


def delete_value(args):
    editor = IniEditor(args.filename)
    editor.delete(args.section, args.key)
    editor.save(args.out_filename)


def parse_args():
    parser = argparse.ArgumentParser(description="edit .ini file")
    subparsers = parser.add_subparsers(description="sub commands")
    update_parser = subparsers.add_parser("update", help="update the value of an item")
    update_parser.add_argument("--section", help="the section name", required=True)
    update_parser.add_argument("--key", help="the key", required=True)
    update_parser.add_argument("--value", help="the new value to be set", required=True)
    update_parser.add_argument("--filename", help="the .ini filename", required=True)
    update_parser.add_argument("--out-filename", help="the output file name", required=False)
    update_parser.set_defaults(func=update_value)

    delete_parser = subparsers.add_parser("delete", help="delete a key or section")
    delete_parser.add_argument("--section", help="the section name", required=True)
    delete_parser.add_argument("--key", help="the key in section")
    update_parser.add_argument("--filename", help="the .ini filename", required=True)
    update_parser.add_argument("--out-filename", help="the output file name", required=False)
    update_parser.set_defaults(func=delete_value)
    return parser.parse_args()


def main():
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
