from distutils.core import setup

setup(name='nixops',
      version='@version@',
      description='NixOS cloud deployment tool',
      url='https://github.com/NixOS/nixops',
      author='Eelco Dolstra',
      author_email='eelco.dolstra@logicblox.com',
      scripts=['scripts/nixops'],
      packages=['nixops', 'nixops.resources', 'nixops.backends'],
      )
