#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
exif_rename
A tool for batch renaming image files based on their (creation) date.
"""

__author__ = "Krista Karppinen"
__version__ = "0.9.0"
__copyright__ = "Copyright (C) 2020 Krista Karppinen"
__license__ = """License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.

Written by Krista Karppinen, based on a bash script by Fiona Klute.
"""

import argparse
import configparser
import datetime
import os
import os.path
import piexif
import re
import subprocess
import struct
import sys
from pathlib import Path


class StderrLogger:
    def __init__(self, pause_on_error=False):
        if pause_on_error:
            self.log = self.log_with_pause
        else:
            self.log = self.log_without_pause

    def log_without_pause(self, error_str):
        print(error_str, file=sys.stderr)

    def log_with_pause(self, error_str):
        self.log_without_pause(error_str)
        input()


class TimestampReadException(Exception):
    pass


class CommandLineParseException(Exception):
    pass


simulated_filelist = []
def find_unique_filename(dir, basename, extension, simulate):
    index = 1
    candidate = dir.joinpath(f'{basename}.{extension}')
    while candidate.exists() \
          or (simulate and candidate in simulated_filelist):
        candidate = dir.joinpath(f'{basename}-{index}.{extension}')
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
    except struct.error as e:
        raise TimestampReadException("Possibly corrupt EXIF data ({0})".format(str(e)))

    if len(exif_dict["Exif"]) == 0:
        raise TimestampReadException("File {0} does not contain any EXIF data!".format(filename))
    if not piexif.ExifIFD.DateTimeDigitized in exif_dict["Exif"]:
        raise TimestampReadException("File {0} does not contain an EXIF timestamp.".format(filename))

    datetime_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized].decode()
    datetime_tuple = list(map(int, exif_date_pattern.match(datetime_str).groups()))
    return datetime.datetime(datetime_tuple[0], datetime_tuple[1], datetime_tuple[2], datetime_tuple[3], datetime_tuple[4], datetime_tuple[5])


def get_filename_timestamp(filename, filename_format):
    try:
        return datetime.datetime.strptime(filename, filename_format)
    except ValueError:
        raise TimestampReadException("Filename didn't match the specified pattern")


def get_stat_timestamp(file, timestamp_type):
    statinfo = file.stat()
    return datetime.datetime.fromtimestamp(getattr(statinfo, timestamp_type))


def get_timestamp(file, args):
    exceptions = []

    for date_source in args.date_sources:
        if date_source == 'exif':
            try:
                return (date_source, get_exif_timestamp(str(file)))
            except TimestampReadException as e:
                exceptions.append(str(e))

        elif date_source == 'file-name':
            return (date_source,
                    get_filename_timestamp(file.name,
                                           args.source_name_format))
        elif date_source == 'file-created':
            return (date_source, get_stat_timestamp(file, 'st_ctime'))
        elif date_source == 'file-modified':
            return (date_source, get_stat_timestamp(file, 'st_mtime'))
        else:
            raise ValueError('Unknown date source: ' + date_source)

    raise TimestampReadException('\n'.join(exceptions))


def main(args):
    ext = "jpg"
    cmd_list = None
    if args.mv_cmd:
        cmd_list = args.mv_cmd.split()
    logger = StderrLogger(pause_on_error=args.pause_on_error)

    for file in args.files:
        print(f'{file} ', end='')

        if file.is_dir():
            print("unmodified (is a directory)")
            logger.log(f'Skipping {file} (is a directory)')
            continue

        if not file.is_file():
            print("unmodified (could not find file)")
            logger.log(f'Could not find file: {file}')
            continue

        try:
            (date_source, dt) = get_timestamp(file, args)
            formatted_date = dt.strftime(args.date_format)
            if matches_timestamp(file.name, formatted_date, ext):
                print("unmodified (file name already matches)")
                continue

            dest_file = find_unique_filename(file.parent, formatted_date,
                                               ext, args.simulate)
            print(f'-({date_source})-> {dest_file}')

            if args.simulate:
                if args.mv_cmd:
                    print(f'{args.mv_cmd} "{file}" "{dest_file}"')
                else:
                    print(f'{file!r}.rename(\'{dest_file}\')')
            else:
                if args.mv_cmd:
                    subprocess.run(cmd_list + [file, dest_file])
                else:
                    file.rename(dest_file)

        except TimestampReadException as e:
            print('unmodified (no more date sources)')
            logger.log(e)


def parse_date_sources(args):
    sources = args.date_source_str.split(',')
    for source in sources:
        if source not in ('exif', 'file-name', 'file-created', 'file-modified'):
            raise CommandLineParseException('Unknown date source: ' + source)
        if source == 'file-name' and args.source_name_format == None:
            raise CommandLineParseException('You have to specify "--source-name-format" to use the "file-name" source.')

    return sources


if __name__ == "__main__":
    config = configparser.ConfigParser()
    try:
        with open(os.path.expanduser('~/.exif_rename.conf')) as conffile:
            config.read_file(conffile)
    except FileNotFoundError:
        # It's okay if there is no config file.
        pass

    default_dateformat = "%Y-%m-%d_%H.%M.%S"
    default_dateformat_help = default_dateformat.replace('%', '%%')
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)

    # Files to process
    parser.add_argument("files", nargs="+", metavar="FILE", type=Path,
                        help="List of files to process")

    exec_group = parser.add_argument_group("Program execution")
    exec_group.add_argument("-s", "-n", "--simulate", "--dry-run",
                            dest="simulate", action="store_true",
                            default=False,
                            help="Simulate only (print what would be done, "
                            "don't do anything)")
    exec_group.add_argument("-p", "--pause-on-error", action="store_true",
                            default=config.getboolean(exec_group.title,
                                                      'pause_on_error',
                                                      fallback=False),
                            help="Stop to wait for user input if an error "
                            "occurs.")
    mv_group = exec_group.add_mutually_exclusive_group()
    mv_group.add_argument("-g", "--git-mv", action="store_const",
                          const='git mv', dest='mv_cmd',
                          help="Use git mv for renaming")
    mv_group.add_argument("-m", "--mv-cmd", action="store", metavar="cmd",
                          dest="mv_cmd",
                          help="Specify a command to use for renaming")

    date_group = parser.add_argument_group("Date options")
    date_group.add_argument("-d", "--date-source", action="store",
                            dest="date_source_str", metavar="src",
                            default=config.get(date_group.title, 'date_source',
                                               fallback='exif'),
                            help="Specify the date source(s) to try in order, "
                            "comma-separated (exif, file-name, file-created, "
                            "file-modified)")
    date_group.add_argument("-f", "--date-format", action="store",
                            metavar="fmt",
                            default=config.get(date_group.title, 'date_format',
                                               raw=True,
                                               fallback=default_dateformat),
                            help="Specify a custom date format (default "
                            + default_dateformat_help + ", see man (3) "
                            "strftime for the format specification)")
    date_group.add_argument("--source-name-format", action="store",
                            metavar="fmt",
                            default=config.get(date_group.title,
                                               'source_name_format',
                                               raw=True, fallback=None),
                            help="Specify a source file name format for "
                            "file-name source. See man (3) strftime for the "
                            "format specification.")

    # Specify output of "--version"
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})\n{copyright}\n{license}".format(
            version=__version__, copyright=__copyright__, license=__license__))

    # enable bash completion if argcomplete is available
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()

    try:
        # Do additional parsing
        args.date_sources = parse_date_sources(args)
        # Defaults don't work in a mutually exclusive group, so we
        # have to apply config or defaults here.
        if not args.mv_cmd:
            args.mv_cmd = config.get(exec_group.title, 'mv_cmd', fallback=None)

    except CommandLineParseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    try:
        main(args)
    except KeyboardInterrupt:
        print()        # Be nice and finish the line with ^C ;)
        sys.exit(2)
    except BrokenPipeError:
        sys.exit(2)
