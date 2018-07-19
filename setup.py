import sys
import subprocess

from distutils.core import setup, Command


class TestCommand(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        ret = subprocess.call([sys.executable, 'tests.py', 'tests/unit'])
        raise SystemExit(ret)


setup(name='nixops',
      version='@version@',
      description='NixOS cloud deployment tool',
      url='https://github.com/NixOS/nixops',
      author='Eelco Dolstra',
      author_email='eelco.dolstra@logicblox.com',
      scripts=['scripts/nixops'],
      packages=['nixops', 'nixops.plugins', 'nixops.resources', 'nixops.backends'],
      package_data={'nixops': ['data/nixos-infect']},
      cmdclass={'test': TestCommand}
      )
