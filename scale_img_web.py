#!/usr/bin/python3
"""scale_img_web

A tool for scaling images to certain maximum dimensions, naming the
output file after date information for the original.

"""

__author__ = "Fiona Klute"
__version__ = "0.1.0"
__copyright__ = "Copyright (C) 2021 Fiona Klute"
__license__ = """
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
"""
import exif_rename
import sys
from pathlib import Path
from PIL import Image


def scale_file(infile, size=(1280, 1280), date_format='%Y%m%d_%H%M%S'):
    timestamp = exif_rename.get_timestamp(
        infile,
        [
            exif_rename.DateSource.EXIF,
            exif_rename.DateSource.FILE_CREATED
        ])[1]

    formatted_date = timestamp.strftime(date_format)
    # TODO: detect/avoid collisions
    outfile = formatted_date + infile.suffix

    print(f'{infile} -> {outfile}')
    with Image.open(infile) as img:
        img.thumbnail(size)
        # img.save() accepts a file handle, so we can use exclusive
        # open for collision detection
        img.save(outfile)


# TODO: configurable size (command line)
# TODO: configurable date format (command line, exif_rename config)
for f in sys.argv[1:]:
    scale_file(Path(f))
