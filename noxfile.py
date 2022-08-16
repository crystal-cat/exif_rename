import nox


@nox.session
def lint(session):
    """Lint using Flake8."""
    session.install('flake8')
    session.run('flake8', '--statistics', '.')


@nox.session
def test(session):
    """Run tests, gather coverage data."""
    session.install('coverage', '.')
    session.run('coverage', 'run', 'test.py')
    session.notify('coverage')


@nox.session
def coverage(session):
    """Generage coverage report."""
    session.install('coverage')
    session.run('coverage', 'report', '-m', 'exif_rename.py')
    session.run('coverage', 'html', 'exif_rename.py')
