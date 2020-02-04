#!/usr/bin/env python3
"""
exif_rename
A tool for batch renaming image files based on their (creation) date.
"""

__author__ = "Krista Karppinen"
__version__ = "0.9.0"
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


class TimestampReadException(Exception):
    pass

class CommandLineParseException(Exception):
    pass

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

exif_date_pattern = re.compile('^(\\d{4}):(\\d{2}):(\\d{2}) (\\d{2}):(\\d{2}):(\\d{2})$')
def get_exif_timestamp(filename):
    try:
        exif_dict = piexif.load(filename)
    except piexif.InvalidImageDataError as e:
        raise TimestampReadException(str(e))
    if len(exif_dict["Exif"]) == 0:
        raise TimestampReadException("File {0} does not contain any EXIF data!".format(filename))
    if not piexif.ExifIFD.DateTimeDigitized in exif_dict["Exif"]:
        raise TimestampReadException("File {0} does not contain an EXIF timestamp.".format(filename))

    datetime_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized].decode()
    datetime_tuple = list(map(int, exif_date_pattern.match(datetime_str).groups()))
    return datetime.datetime(datetime_tuple[0], datetime_tuple[1], datetime_tuple[2], datetime_tuple[3], datetime_tuple[4], datetime_tuple[5])

def get_stat_timestamp(filename, timestamp_type):
    statinfo = os.stat(filename)
    return datetime.datetime.fromtimestamp(getattr(statinfo, timestamp_type))

def get_timestamp(filename, date_sources):
    exceptions = []

    for date_source in date_sources:
        if date_source == 'exif':
            try:
                return (date_source, get_exif_timestamp(filename))
            except TimestampReadException as e:
                exceptions.append(str(e))

        elif date_source == 'file-created':
            return (date_source, get_stat_timestamp(filename, 'st_ctime'))
        elif date_source == 'file-modified':
            return (date_source, get_stat_timestamp(filename, 'st_mtime'))
        else:
            raise CommandLineParseException('Unknown date source: ' + date_source)

    raise TimestampReadException('\n'.join(exceptions))

def main(args):
    ext = "jpg"
    cmd_list = args.mv_cmd.split(" ")

    for filename in args.files:
        sys.stdout.write(filename)
        sys.stdout.write(' ')

        if os.path.isdir(filename):
            print("unmodified (is a directory)")
            print("Skipping {0} (is a directory)".format(filename), file=sys.stderr)
            continue

        if not os.path.isfile(filename):
            print("unmodified (could not find file)")
            print("Could not find file: {0}".format(filename), file=sys.stderr)
            continue

        try:
            (date_source, dt) = get_timestamp(filename, args.date_sources)
            formatted_date = dt.strftime(args.date_format)
            if matches_timestamp(filename, formatted_date, ext):
                print("unmodified (file name already matches)".format(filename))
                continue

            to_filename = find_unique_filename(formatted_date, ext, args.simulate)
            print("-({0})-> {1}".format(date_source, to_filename))

            if args.simulate:
                print('{0} "{1}" "{2}"'.format(args.mv_cmd, filename, to_filename))
            else:
                subprocess.run(cmd_list + [filename, to_filename])

        except TimestampReadException as e:
            print('unmodified (no more date sources)')
            print(e, file=sys.stderr)

def parse_move_command(args):
    if args.git_mv:
        if args.mv_cmd_raw != "mv":
            raise CommandLineParseException("Conflicting options specified: -g and -m")
        return "git mv"

    return args.mv_cmd_raw

def parse_date_sources(args):
    sources = args.date_source_str.split(',')
    for source in sources:
        if source not in ('exif', 'file-created', 'file-modified'):
            raise CommandLineParseException('Unknown date source: ' + source)

    return sources

if __name__ == "__main__":
    default_dateformat = "%Y-%m-%d_%H.%M.%S"
    default_dateformat_help = default_dateformat.replace('%', '%%')
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Files to process
    parser.add_argument("files", nargs="+", metavar="FILE", help="List of files to process")

    # Options
    parser.add_argument("-d", "--date-source", action="store", dest="date_source_str", metavar="src", default="exif", help="Specify the date source(s) to try in order, comma-separated (exif, file-created, file-modified)")
    parser.add_argument("-f", "--date-format", action="store", metavar="fmt", default=default_dateformat, help="Specify a custom date format (default " + default_dateformat_help + ", see man (1) date for details)")
    parser.add_argument("-g", "--git-mv", action="store_true", default=False, help="Use git mv instead of regular mv for renaming")
    parser.add_argument("-m", "--mv-cmd", action="store", metavar="cmd", default="mv", dest="mv_cmd_raw", help="Specify a command to use for renaming instead of mv")
    parser.add_argument("-s", "--simulate", action="store_true", default=False, help="Simulate only (print what would be done, don't do anything)")

    # Specify output of "--version"
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})\n{copyright}\n{license}".format(
            version=__version__, copyright=__copyright__, license=__license__))

    args = parser.parse_args()

    try:
        # Do additional parsing
        args.mv_cmd = parse_move_command(args)
        args.date_sources = parse_date_sources(args)

    except CommandLineParseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    main(args)

