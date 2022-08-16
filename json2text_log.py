#!/usr/bin/env python
import abc
import argparse
import json
import sys

"""
convert log from json format to human readable text format

the json log can be read from stdin or from a file

The text log can be written to the file or stdout
"""


class JsonLogReader:
    @abc.abstractmethod
    def read_log(self):
        """
        read one log record
        :return: a json log record or None if no more record is available
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def close(self):
        """
        close the log reader
        :return: None
        """
        raise NotImplementedError()


class TextLogWriter:
    @abc.abstractmethod
    def write_log(self, text_log):
        """
        write a text log
        :param text_log: the log in text format
        :return: None
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def close(self):
        """
        close the log writer
        :return: None
        """
        raise NotImplementedError()


class StdinJsonLogReader(JsonLogReader):

    def read_log(self):
        for log in sys.stdin:
            try:
                return json.loads(log)
            except Exception as ex:
                pass
        return None

    def close(self):
        pass


class FileJsonLogReader(JsonLogReader):

    def __init__(self, file_name):
        self._fp = open(file_name)

    def read_log(self):
        for line in self._fp:
            try:
                return json.loads(line)
            except:
                pass
        return None

    def close(self):
        self._fp.close()


class StdoutTextLogWriter(TextLogWriter):

    def write_log(self, text_log):
        sys.stdout.write(text_log)
        sys.stdout.write("\n")

    def close(self):
        pass


class FileTextLogWriter(TextLogWriter):

    def __init__(self, file_name):
        self._fp = open(file_name, "w")

    def write_log(self, text_log):
        self._fp.write(text_log)
        self._fp.write("\n")

    def close(self):
        self._fp.close()


class Json2TextLogConverter:
    def __init__(self, fields, delimiter, log_reader, log_writer):
        self._fields = fields
        self._delimiter = delimiter
        self._log_reader = log_reader
        self._log_writer = log_writer

    def run(self):
        while True:
            json_log = self._log_reader.read_log()
            if json_log is None:
                break
            values = []
            for field in self._fields:
                if field in json_log:
                    values.append(json_log[field])
            self._log_writer.write_log(self._delimiter.join(values))


def parse_args():
    parser = argparse.ArgumentParser(description="convert log from json to text format")
    parser.add_argument("--fields", nargs="+", help="the fields will be print in the text", required=True)
    parser.add_argument("--delimiter", help="the delimiter used between the fields", default=" ")
    parser.add_argument("--input-file", help="the input file, read log from stdin if it is missing")
    parser.add_argument("--output-file", help="the output file, print log to stdout if it is missing")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.input_file is None:
        log_reader = StdinJsonLogReader()
    else:
        log_reader = FileJsonLogReader(args.input_file)

    if args.output_file is None:
        log_writer = StdoutTextLogWriter()
    else:
        log_writer = FileTextLogWriter(args.output_file)

    converter = Json2TextLogConverter(args.fields, args.delimiter, log_reader, log_writer)
    converter.run()
    log_reader.close()
    log_writer.close()


if __name__ == "__main__":
    main()
