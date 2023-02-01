#!/usr/bin/python

import argparse
import docx2txt


class TextReader:
    def __init__(self, filename):
        self._text = self._read_all_text(filename)
        print(self._text)
        self._lines = len(self._text)

    @classmethod
    def _read_all_text(cls, filename):
        if filename.endswith(".docx"):
            return docx2txt.process(filename).split("\n")

        with open(filename) as fp:
            return fp.read().split("\n")

    def __iter__(self):
        self._index = 0
        return self

    def __next__(self):
        if self._index < self._lines:
            line = self._text[self._index]
            self._index += 1
            return line
        raise StopIteration


class Asn1Extractor:
    ASN1_START_LINE = "-- ASN1START"
    ASN1_STOP_LINE = "-- ASN1STOP"

    @classmethod
    def extract_asn1(cls, input_filename: str, output_buffer: list):
        text_reader = TextReader(input_filename)
        in_asn1_block = False
        for line in text_reader:
            print(line)
            if line.strip() == cls.ASN1_START_LINE:
                in_asn1_block = True
            elif line.strip() == cls.ASN1_STOP_LINE:
                in_asn1_block = False
            elif in_asn1_block:
                if len(line.strip()) > 0:
                    output_buffer.append(line.rstrip())


def parse_args():
    parser = argparse.ArgumentParser(description="extract ASN.1 from 3GPP document")
    parser.add_argument("--input-file", help="the input file name", required=True)
    parser.add_argument("--output-file", help="the output file name", default="-")
    return parser.parse_args()


def main():
    args = parse_args()
    output = []
    Asn1Extractor.extract_asn1(args.input_file, output)
    if args.output_file is None or args.output_file in ('-', '/dev/stdout'):
        print("\n".join(output))
    with open(args.output_file, "w") as fp:
        fp.write("\n".join(output))

if __name__ == "__main__":
    main()
