#!/usr/bin/env python3
"""
exif_rename
A tool for batch renaming image files based on their (creation) date.
"""

__author__ = "Krista Karppinen"
__version__ = "0.8.0"
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
import subprocess
import sys


simulated_filelist = []
def find_unique_filename(basename, extension, simulate):
    index = 1
    candidate = basename + "." + extension
    while os.path.exists(candidate) or ( simulate and candidate in simulated_filelist ):
        candidate = "{0}-{1}.{2}".format(basename, index, extension)
        index += 1

    if simulate:
        simulated_filelist.append(candidate)

    return candidate

def matches_timestamp(filename, timestamp, extension):
    if (timestamp + "." + extension) == filename:
        return True
    if not filename.startswith(timestamp) or not filename.endswith(extension):
        return False
    midsection = filename[len(timestamp):-len(extension)]
    return re.match("-\\d+", midsection) != None

def main(args):
    ext = "jpg"
    p = re.compile('^(\\d{4}):(\\d{2}):(\\d{2}) (\\d{2}):(\\d{2}):(\\d{2})$')
    cmd_list = args.mv_cmd.split(" ")

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
        formatted_date = dt.strftime(args.date_format)
        if matches_timestamp(filename, formatted_date, ext):
            print("File {0} unmodified (file name already matches exif data)".format(filename), file=sys.stderr)
            continue

        to_filename = find_unique_filename(formatted_date, ext, args.simulate)

        print("{0} -> {1}".format(filename, to_filename))

        if args.simulate:
            print('{0} "{1}" "{2}"'.format(args.mv_cmd, filename, to_filename))
        else:
            subprocess.run(cmd_list + [filename, to_filename])


if __name__ == "__main__":
    default_dateformat = "%%Y-%%m-%%d_%%H.%%M.%%S"
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Files to process
    parser.add_argument("files", nargs="+", metavar="FILE", help="List of files to process")

    # Options
    parser.add_argument("-f", "--date-format", action="store", metavar="fmt", default=default_dateformat, help="Specify a custom date format (default " + default_dateformat + ", see man (1) date for details)")
    parser.add_argument("-g", "--git-mv", action="store_true", default=False, help="Use git mv instead of regular mv for renaming")
    parser.add_argument("-m", "--mv-cmd", action="store", metavar="cmd", default="mv", dest="mv_cmd", help="Specify a command to use for renaming instead of mv")
    parser.add_argument("-s", "--simulate", action="store_true", default=False, help="Simulate only (print what would be done, don't do anything)")

    # Specify output of "--version"
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})\n{copyright}\n{license}".format(
            version=__version__, copyright=__copyright__, license=__license__))

    args = parser.parse_args()

    # Resolve conflicts
    if args.git_mv:
        if args.mv_cmd != "mv":
            print("Conflicting options specified: -g and -m")
            sys.exit(1)
        args.mv_cmd = "git mv"

    main(args)

