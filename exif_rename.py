#!/usr/bin/env python3
"""
exif_rename
A tool for batch renaming image files based on their (creation) date.
"""

__author__ = "Krista Karppinen"
__version__ = "0.1.0"
__copyright__ = "Copyright (C) 2020 Krista Karppinen"
__license__  = """License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.

Written by Krista Karppinen, based on a bash script by Fiona Klute.
"""

import argparse
import datetime
import os
import piexif
import re
import sys


def main(args):
    p = re.compile('^(\\d{4}):(\\d{2}):(\\d{2}) (\\d{2}):(\\d{2}):(\\d{2})$')

    for filename in args.files:
        if not os.path.isfile(filename):
            print("File {0} does not exist!".format(filename), file=sys.stderr)
            continue

        exif_dict = piexif.load(filename)
        if len(exif_dict["Exif"]) == 0:
            print("File {0} does not contain any EXIF data!".format(filename), file=sys.stderr)
            continue

        if not piexif.ExifIFD.DateTimeDigitized in exif_dict["Exif"]:
            print("File {0} does not contain an EXIF timestamp.".format(filename), file=sys.stderr)
            continue

        datetime_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized].decode()
        datetime_tuple = list(map(int, p.match(datetime_str).groups()))
        dt = datetime.datetime(datetime_tuple[0], datetime_tuple[1], datetime_tuple[2], datetime_tuple[3], datetime_tuple[4], datetime_tuple[5])
        to_filename = dt.strftime("%Y-%m-%d-%H.%m.%s.jpg")

        print("{0} -> {1}".format(filename, to_filename))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Files to process
    parser.add_argument("files", nargs="+", metavar="FILE", help="List of files to process")

    # Specify output of "--version"
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})\n{copyright}\n{license}".format(
            version=__version__, copyright=__copyright__, license=__license__))

    args = parser.parse_args()
    main(args)

