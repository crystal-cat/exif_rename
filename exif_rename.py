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
import exifread
import logging
import os
import re
import shlex
import subprocess
import sys
import typing
from collections import ChainMap, defaultdict, namedtuple
from collections.abc import Mapping
from enum import Enum
from pathlib import Path


logger = logging.getLogger(__name__)


class TimestampReadException(Exception):
    pass


class CommandLineParseException(Exception):
    pass


class DateSource(Enum):
    EXIF = 'exif'
    FILE_NAME = 'file-name'
    FILE_CREATED = 'file-created'
    FILE_MODIFIED = 'file-modified'


def matches_timestamp(filename: str, timestamp: str, extension: str) -> bool:
    if (timestamp + extension) == filename:
        return True
    if not filename.startswith(timestamp) or not filename.endswith(extension):
        return False
    midsection = filename[len(timestamp):-len(extension)]
    return re.match(r'-\d+', midsection) is not None


exif_date_pattern = \
    re.compile(r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$')


def get_exif_timestamp(filename: str | Path) -> datetime.datetime:
    with open(filename, 'rb') as fh:
        exif_dict = exifread.process_file(fh)

    if 'EXIF DateTimeDigitized' not in exif_dict:
        raise TimestampReadException(
            f"File {filename} does not contain an EXIF timestamp.")

    datetime_str = str(exif_dict['EXIF DateTimeDigitized'])
    if (m := exif_date_pattern.match(datetime_str)) is not None:
        datetime_tuple = tuple(map(int, m.groups()))
    else:
        raise TimestampReadException('invalid EXIF timestamp format')
    return datetime.datetime(
            datetime_tuple[0], datetime_tuple[1], datetime_tuple[2],
            datetime_tuple[3], datetime_tuple[4], datetime_tuple[5])


def get_filename_timestamp(filename: str,
                           filename_format: str) \
                           -> datetime.datetime:
    try:
        return datetime.datetime.strptime(filename, filename_format)
    except ValueError:
        raise TimestampReadException(
            "Filename didn't match the specified pattern")


def get_stat_timestamp(file: Path, timestamp_type: str) -> datetime.datetime:
    statinfo = file.stat()
    return datetime.datetime.fromtimestamp(getattr(statinfo, timestamp_type))


def get_timestamp(file: Path,
                  date_sources: list[DateSource],
                  source_name_format: str | None = None) \
                  -> tuple[DateSource, datetime.datetime]:
    exceptions = []

    for date_source in date_sources:
        try:
            if date_source == DateSource.EXIF:
                return (date_source, get_exif_timestamp(str(file)))
            elif date_source == DateSource.FILE_NAME:
                # The config parser ensures source_name_format is not
                # None when the FILE_NAME source is enabled.
                return (date_source,
                        get_filename_timestamp(
                            file.name, source_name_format))  # type: ignore
            elif date_source == DateSource.FILE_CREATED:
                return (date_source, get_stat_timestamp(file, 'st_ctime'))
            elif date_source == DateSource.FILE_MODIFIED:
                return (date_source, get_stat_timestamp(file, 'st_mtime'))
            else:
                raise ValueError('Unknown date source: ' + date_source)
        except TimestampReadException as e:
            exceptions.append(str(e))

    raise TimestampReadException('\n'.join(exceptions))


class Renamer:
    """The base Renamer class.
    The main purpose of this class is to keep state while renaming or
    simulating renaming. Additionally the constructor performs some
    parameter restructuring.

    The subclasses SimulatedRenamer and FilesystemChangingRenamer contain
    some of the mutually exclusive logic for dry and actual runs. This
    split exists to simplify and generalize some of the functions and to
    split the responsibility for better maintainability and testing.
    """
    mv_cmd: list[str] | None

    def __new__(cls, args: Mapping[str, typing.Any]) -> 'Renamer':
        """Return a new instance of Renamer when instantiated.
        This function decides which subclass to instantiate depending on
        the arguments (the "args" parameter) given.

        If we're simulating (args['simulate'] is True) the object returned
        will be of type SimulatedRenamer. Otherwise, it will be of type
        FilesystemChangingRenamer.
        """
        if cls is Renamer:
            if args['simulate']:
                return SimulatedRenamer(args)
            else:
                return FilesystemChangingRenamer(args)

        else:
            return object.__new__(cls)

    def __init__(self, args: Mapping[str, typing.Any]) -> None:
        """Initialize a new Renamer object.
        Initialization logic common to all subclasses happens here.
        """
        self.args = args
        if args['mv_cmd']:
            self.mv_cmd = shlex.split(args['mv_cmd'])
        else:
            self.mv_cmd = None

    def run(self) -> None:
        """Rename the files specified by args['files'].
        """
        for file in self.args['files']:
            if file.is_dir():
                logger.info('Skipping %s (is a directory)', file)
                continue

            if not file.is_file():
                logger.error('Could not find file: %s', file)
                continue

            try:
                (date_source, dt) = get_timestamp(
                    file,
                    self.args['date_sources'],
                    self.args['source_name_format'])
                formatted_date = dt.strftime(self.args['date_format'])
                ext = file.suffix.lower()
                if matches_timestamp(file.name, formatted_date, ext):
                    logger.debug('%s unmodified (file name already matches)',
                                 file)
                    continue

                dest_file = self.find_unique_filename(file.parent,
                                                      formatted_date, ext)
                logger.info('%s -(%s)-> %s',
                            file, date_source.value, dest_file)
                self.rename_file(file, dest_file)

            except TimestampReadException as e:
                logger.error('%s unmodified (no usable date source): %s',
                             file, e)

    def find_unique_filename(self,
                             directory: Path,
                             basename: str,
                             extension: str) -> Path:
        """Find a suitable file name that doesn't already exist.

        Positional arguments:
        directory -- The directory for the new file.
        basename -- "file" in "file.jpg"
        extension -- ".jpg" in "file.jpg"

        Returns:
        "file.jpg" or "file-1.jpg" or "file-2.jpg" etc. that's guaranteed
        not to exist in the filesystem
        """
        index = 1
        candidate = directory.joinpath(f'{basename}{extension}')
        while (self.path_exists(candidate)):
            candidate = directory.joinpath(f'{basename}-{index}{extension}')
            index += 1

        return candidate

    def path_exists(self, path: Path) -> bool:
        """Return whether the path given exists."""
        raise NotImplementedError('must be implemented in subclass')

    def rename_file(self, src_file: Path, dest_file: Path) -> None:
        """Rename a file."""
        raise NotImplementedError('must be implemented in subclass')


class SimulatedRenamer(Renamer):
    """This class contains the logic for doing a dry run, or simulated
    renaming. The actual files are not touched.
    """
    def __init__(self, args: Mapping[str, typing.Any]) -> None:
        """Initialize a new SimulatedRenamer object.
        This constructor extends the functionality of the constructor
        from the base class.
        """
        super().__init__(args)

        self.files_added_counter: dict[Path, int] = defaultdict(int)
        """Paths that are marked to exist within the simulation.
        The value for each key marks how many times the path has been
        marked to exist (as in, being the target path for renaming)
        """

        self.files_removed_counter: dict[Path, int] = defaultdict(int)
        """Paths that are marked to not exist within the simulation.
        The value for each key marks how many times the path has been
        marked to not exist (as in, being the source path for renaming)
        """

    def path_exists(self, path: Path) -> bool:
        """Return whether the path given exists.
        Called by the find_unique_filename() method in the base class.

        In the context of this class a path exists either if it exists in
        the file system and hasn't been marked removed, or if there's a
        new path that's been marked as added.
        """
        return (path.exists()
                + self.files_added_counter[path]
                - self.files_removed_counter[path] > 0)

    def rename_file(self, src_file: Path, dest_file: Path) -> None:
        """Record a simulated rename.
        The results of path_exists() function will reflect the rename.
        """
        self.files_added_counter[dest_file] += 1
        self.files_removed_counter[src_file] += 1


class FilesystemChangingRenamer(Renamer):
    """This class contains the logic for the actual renaming of the files
    in the file system, as opposed to simulated renaming.
    """

    def rename_file(self, src_file: Path, dest_file: Path) -> None:
        """Rename a file.
        Note that no checking of file names is made by this function, the
        source file name is expected to exist and the destination file name
        is expected not to exist.
        """
        if self.mv_cmd:
            logger.debug('%s "%s" "%s"', self.mv_cmd, src_file, dest_file)
            subprocess.run(self.mv_cmd + [src_file, dest_file])
        else:
            logger.debug('%r.rename(\'%s\')', src_file, dest_file)
            src_file.rename(dest_file)

    def path_exists(self, path: Path) -> bool:
        """Return whether the path given exists in the file system.
        Called by the find_unique_filename() method in the base class.
        """
        return path.exists()


def parse_date_sources(args: Mapping[str, typing.Any]) -> list[DateSource]:
    sources = list()
    for s in args['date_source'].split(','):
        try:
            source = DateSource(s)
            sources.append(source)
        except ValueError:
            raise CommandLineParseException(f'Unknown date source: {s}')
        if source == DateSource.FILE_NAME \
           and args['source_name_format'] is None:
            raise CommandLineParseException(
                'You have to specify "--source-name-format" to use the '
                '"file-name" source.')
    return sources


default_dateformat = '%Y-%m-%d_%H.%M.%S'
default_conf = {
    'pause_on_error': False,
    'date_source': 'exif',
    'date_format': default_dateformat,
    'source_name_format': None,
    'mv_cmd': None,
    'log': logging.INFO
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


def read_config(conffile: str | Path) -> dict[str, str | bool]:
    config = configparser.ConfigParser()
    with open(Path(conffile).expanduser()) as fh:
        config.read_file(fh)

    result = dict()
    value: str | bool | None
    for opt in conf_options:
        if opt.type == 'boolean':
            value = config.getboolean(opt.section, opt.option, fallback=None)
        else:
            value = config.get(opt.section, opt.option,
                               raw=opt.raw, fallback=None)
        if value is not None:
            result[opt.option] = value
    return result


def merge_args(args: argparse.Namespace, conffile: str | None = None) \
        -> Mapping[str, typing.Any]:
    """Merge the passed in command line arguments with configuration file
    and defaults.

    "args" must be the argparse.Namespace object returned by the
    argument parser.

    "conffile" is the path of the configuration file to read. If None
    (the default) the path is read from the environment variable
    EXIF_RENAME_CONF if set (empty diables configuration), otherwise
    it defaults to ~/.exif_rename.conf.

    Returns a dict of the arguments.

    """

    cmd_args = {k: v for k, v in vars(args).items() if v is not None}

    if conffile is None:
        try:
            conffile = os.environ['EXIF_RENAME_CONF']
        except KeyError:
            conffile = '~/.exif_rename.conf'

    conf_args = {}
    if len(conffile) > 0:
        try:
            conf_args = read_config(conffile)
        except FileNotFoundError:
            # It's okay if there is no config file.
            pass

    combined_args = ChainMap(cmd_args, conf_args, default_conf)

    # Do additional parsing, may raise CommandLineParseException
    combined_args['date_sources'] = parse_date_sources(combined_args)

    return combined_args


def main(command_line: list[str] | None = None) -> None:
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

    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument('-q', '--quiet', action='store_const',
                           const=logging.WARNING, dest='log',
                           help='Log only warning and errors')
    log_group.add_argument('-D', '--debug', action='store_const',
                           const=logging.DEBUG, dest='log',
                           help='Log debug info')

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

    args = parser.parse_args(args=command_line)
    try:
        combined_args = merge_args(args)
    except CommandLineParseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(format='%(message)s', level=combined_args['log'])
    try:
        r = Renamer(combined_args)
        r.run()
    except KeyboardInterrupt:
        print()        # Be nice and finish the line with ^C ;)
        sys.exit(2)
    except BrokenPipeError:
        sys.exit(2)


if __name__ == "__main__":
    main()
