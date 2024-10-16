import nox


@nox.session
def lint(session):
    """Lint using Flake8."""
    session.install('flake8')
    session.run('flake8', '--statistics', '.')


@nox.session
def typecheck(session):
    """Typecheck using MyPy."""
    session.install('.')
    session.install('mypy')
    session.run('mypy', '.')


@nox.session(python=['3.10', '3.11', '3.12', '3.13'])
def test(session):
    """Run tests, report coverage."""
    session.install('.[tests]')
    session.run('coverage', 'run', '--parallel-mode', '-m', 'pytest', '-v')


@nox.session
def coverage(session):
    """Generate coverage report."""
    session.install('coverage')
    session.run('coverage', 'combine')
    session.run('coverage', 'report', '-m', 'exif_rename.py')
    session.run('coverage', 'html', 'exif_rename.py')
