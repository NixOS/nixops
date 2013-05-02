from distutils.core import setup
import glob

setup(name='nixops',
      version='0.1',
      description='NixOS cloud deployment tool',
      url='https://github.com/NixOS/charon',
      author='Eelco Dolstra',
      author_email='eelco.dolstra@logicblox.com',
      scripts=['scripts/nixops'],
      packages=['nixops', 'nixops.resources', 'nixops.backends'],
      )
