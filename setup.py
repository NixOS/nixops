from distutils.core import setup
import glob

setup(name='charon',
      version='0.1',
      description='NixOS cloud deployment tool',
      url='https://github.com/NixOS/charon',
      author='Eelco Dolstra',
      author_email='eelco.dolstra@logicblox.com',
      scripts=['scripts/charon'],
      packages=['charon', 'charon.resources', 'charon.backends'],
      )
