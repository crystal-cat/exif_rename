# exif_rename

Exif_rename is Python tool and library for renaming image files based
on their (creation) date.

## Installation

You can use `pipx` (or `pip`) to install as usual, with the repository
URL, local repository path, or downloaded archive. For example, to
install from the `main` branch using the repository URL:

```
pipx install git+https://github.com/crystal-cat/exif_rename.git@main
```

The installed command is `exif-rename`.

## Configuration

You can modify the default behavior using a configuration file. Its
default location is `~/.exif_rename.conf`. If `EXIF_RENAME_CONF` is
set its used as the path to the config file instead. The file uses the
INI-like format supported by the [`configparser` module of the Python
standard library](https://docs.python.org/3/library/configparser.html).

The following example shows the default values:

```ini
[Date options]
# Format for generated file names
date_format = %Y-%m-%d_%H.%M.%S
# Where to get the creation date from, see exif-rename -h for options
date_source = exif
# When using the "file-name" date source, expect this format
source_name_format = %Y-%m-%d_%H.%M.%S

[Program execution]
# stop and wait for user input if an error occurs during renaming
pause_on_error = false
# If set, use this command instead of standard library functions to
# rename files
#mv_cmd = None
```

## Developing

Exif_rename has [tests using pytest](test.py), and a
[`noxfile.py`](noxfile.py) to run tests and record coverage, as well
as lint using Flake8. Make sure to fix any issues that show up, and
add tests for any new code.

Pull requests are welcome! :smiley_cat:
