#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
exif_rename
A tool for batch renaming image files based on their (creation) date.
"""

__author__ = "Krista Karppinen"
__version__ = "0.9.0"
__copyright__ = "Copyright (C) 2020 Krista Karppinen"
__license__ = """
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.

Written by Krista Karppinen, based on a bash script by Fiona Klute.
"""

import argparse
import configparser
import datetime
import piexif
import re
import subprocess
import struct
import sys
from collections import ChainMap, namedtuple
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
def find_unique_filename(src, basename, extension, simulate):
    dir = src.parent
    index = 1
    candidate = dir.joinpath(f'{basename}{extension}')
    while candidate.exists() \
          or (simulate and candidate in simulated_filelist):
        candidate = dir.joinpath(f'{basename}-{index}{extension}')
        index += 1

    if simulate:
        simulated_filelist.append(candidate)

    return candidate


def matches_timestamp(filename, timestamp, extension):
    if (timestamp + extension) == filename:
        return True
    if not filename.startswith(timestamp) or not filename.endswith(extension):
        return False
    midsection = filename[len(timestamp):-len(extension)]
    return re.match("-\\d+", midsection) is not None


exif_date_pattern = \
    re.compile(r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$')


def get_exif_timestamp(filename):
    try:
        exif_dict = piexif.load(filename)
    except piexif.InvalidImageDataError as e:
        raise TimestampReadException(str(e))
    except struct.error as e:
        raise TimestampReadException(f"Possibly corrupt EXIF data ({e})")

    if len(exif_dict["Exif"]) == 0:
        raise TimestampReadException(
            f"File {filename} does not contain any EXIF data!")

    if piexif.ExifIFD.DateTimeDigitized not in exif_dict["Exif"]:
        raise TimestampReadException(
            "File {filename} does not contain an EXIF timestamp.")

    datetime_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized].decode()
    datetime_match = exif_date_pattern.match(datetime_str).groups()
    datetime_tuple = list(map(int, datetime_match))
    return datetime.datetime(
            datetime_tuple[0], datetime_tuple[1], datetime_tuple[2],
            datetime_tuple[3], datetime_tuple[4], datetime_tuple[5])


def get_filename_timestamp(filename, filename_format):
    try:
        return datetime.datetime.strptime(filename, filename_format)
    except ValueError:
        raise TimestampReadException(
            "Filename didn't match the specified pattern")


def get_stat_timestamp(file, timestamp_type):
    statinfo = file.stat()
    return datetime.datetime.fromtimestamp(getattr(statinfo, timestamp_type))


def get_timestamp(file, args):
    exceptions = []

    for date_source in args['date_sources']:
        try:
            if date_source == 'exif':
                return (date_source, get_exif_timestamp(str(file)))
            elif date_source == 'file-name':
                return (date_source,
                        get_filename_timestamp(file.name,
                                               args['source_name_format']))
            elif date_source == 'file-created':
                return (date_source, get_stat_timestamp(file, 'st_ctime'))
            elif date_source == 'file-modified':
                return (date_source, get_stat_timestamp(file, 'st_mtime'))
            else:
                raise ValueError('Unknown date source: ' + date_source)
        except TimestampReadException as e:
            exceptions.append(str(e))

    raise TimestampReadException('\n'.join(exceptions))


def main(args):
    cmd_list = None
    if args['mv_cmd']:
        cmd_list = args['mv_cmd'].split()
    logger = StderrLogger(pause_on_error=args['pause_on_error'])

    for file in args['files']:
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
            formatted_date = dt.strftime(args['date_format'])
            ext = file.suffix.lower()
            if matches_timestamp(file.name, formatted_date, ext):
                print("unmodified (file name already matches)")
                continue

            dest_file = find_unique_filename(file, formatted_date,
                                             ext, args['simulate'])
            print(f'-({date_source})-> {dest_file}')

            if args['simulate']:
                if args['mv_cmd']:
                    print(f'{args["mv_cmd"]} "{file}" "{dest_file}"')
                else:
                    print(f'{file!r}.rename(\'{dest_file}\')')
            else:
                if args['mv_cmd']:
                    subprocess.run(cmd_list + [file, dest_file])
                else:
                    file.rename(dest_file)

        except TimestampReadException as e:
            print('unmodified (no more date sources)')
            logger.log(e)


def parse_date_sources(args):
    accepted_sources = ('exif', 'file-name', 'file-created', 'file-modified')
    sources = args['date_source'].split(',')
    for source in sources:
        if source not in accepted_sources:
            raise CommandLineParseException('Unknown date source: ' + source)
        if source == 'file-name' and args['source_name_format'] is None:
            raise CommandLineParseException(
                'You have to specify "--source-name-format to use the '
                '"file-name" source.')

    return sources


default_dateformat = '%Y-%m-%d_%H.%M.%S'
default_conf = {
    'pause_on_error': False,
    'date_source': 'exif',
    'date_format': default_dateformat,
    'source_name_format': None,
    'mv_cmd': None
}


exec_group_title = 'Program execution'
date_group_title = 'Date options'
confopt = namedtuple('confopt', ['section', 'option', 'type', 'raw'],
                     defaults=['str', False])
conf_options = [
    confopt(exec_group_title, 'pause_on_error', 'boolean'),
    confopt(exec_group_title, 'mv_cmd'),
    confopt(date_group_title, 'date_source'),
    confopt(date_group_title, 'date_format', raw=True),
    confopt(date_group_title, 'source_name_format', raw=True),
]


def read_config(conffile):
    config = configparser.ConfigParser()
    with open(Path(conffile).expanduser()) as conffile:
        config.read_file(conffile)

    result = dict()
    for opt in conf_options:
        if opt.type == 'boolean':
            value = config.getboolean(opt.section, opt.option, fallback=None)
        else:
            value = config.get(opt.section, opt.option,
                               raw=opt.raw, fallback=None)
        if value is not None:
            result[opt.option] = value
    return result


if __name__ == "__main__":
    default_dateformat_help = default_dateformat.replace('%', '%%')
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # Files to process
    parser.add_argument("files", nargs="+", metavar="FILE", type=Path,
                        help="List of files to process")

    exec_group = parser.add_argument_group(exec_group_title)
    exec_group.add_argument("-s", "-n", "--simulate", "--dry-run",
                            dest="simulate", action="store_true",
                            default=False,
                            help="Simulate only (print what would be done, "
                            "don't do anything)")
    exec_group.add_argument("-p", "--pause-on-error", action="store_true",
                            help="Stop to wait for user input if an error "
                            "occurs.")
    mv_group = exec_group.add_mutually_exclusive_group()
    mv_group.add_argument("-g", "--git-mv", action="store_const",
                          const='git mv', dest='mv_cmd',
                          help="Use git mv for renaming")
    mv_group.add_argument("-m", "--mv-cmd", action="store", metavar="cmd",
                          dest="mv_cmd",
                          help="Specify a command to use for renaming")

    date_group = parser.add_argument_group(date_group_title)
    date_group.add_argument("-d", "--date-source", action="store",
                            metavar="src",
                            help="Specify the date source(s) to try in order, "
                            "comma-separated (exif, file-name, file-created, "
                            "file-modified)")
    date_group.add_argument("-f", "--date-format", action="store",
                            metavar="fmt",
                            help="Specify a custom date format (default "
                            + default_dateformat_help + ", see man (3) "
                            "strftime for the format specification)")
    date_group.add_argument("--source-name-format", action="store",
                            metavar="fmt",
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
    cmd_args = {k: v for k, v in vars(args).items() if v is not None}

    try:
        conf_args = read_config('~/.exif_rename.conf')
    except FileNotFoundError:
        # It's okay if there is no config file.
        conf_args = {}

    combined_args = ChainMap(cmd_args, conf_args, default_conf)

    try:
        # Do additional parsing
        combined_args['date_sources'] = parse_date_sources(combined_args)
    except CommandLineParseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    try:
        main(combined_args)
    except KeyboardInterrupt:
        print()        # Be nice and finish the line with ^C ;)
        sys.exit(2)
    except BrokenPipeError:
        sys.exit(2)
