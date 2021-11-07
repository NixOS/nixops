.. _chap-hacking:

Hacking
=======

This section provides some notes on how to hack on NixOps. To get the
latest version of NixOps from GitHub:

::

   $ git clone git://github.com/NixOS/nixops.git
   $ cd nixops

To build it and its dependencies:

::

   $ nix-build

The resulting NixOps can be run as ``./result/bin/nixops``.

To build all dependencies and start a shell in which all environment
variables (such as PYTHONPATH) are set up so that those dependencies can
be found:

::

   $ nix-shell
   $ echo $PYTHONPATH
   /nix/store/34l1p57bn9jqdq2qvz269m9vkp1rsyq8-python3-3.9.6-env/lib/python3.9/site-packages:...

You can then run NixOps in your source tree as follows:

::

   $ nixops

To run the tests, do

::

   $ pytest

Note that some of the tests involve the creation of EC2 resources and
thus cost money. You must set the environment variable EC2_ACCESS_KEY
and (optionally) EC2_SECRET_KEY. (If the latter is not set, it will be
looked up in ``~/.ec2-keys`` or in ``~/.aws/credentials``, as described
in `??? <#sec-deploying-to-ec2>`__.) To run a specific test, run
``python3 tests.py
test-name``, e.g. To filter on which backends you want to run functional
tests against, you can filter on one or more tags.

Some useful snippets to debug nixops: Logging

::

   # this will not work, because sys.stdout is substituted with log file
   print('asdf')

   # this will work
   self.log('asdf')
   from __future__ import print_function; import sys; print('asfd', file=sys.__stdout__)
   import sys; import pprint; pprint.pprint(some_structure, stream=sys.__stdout__)

To set breakpoint use

::

   import sys; import pdb; pdb.Pdb(stdout=sys.__stdout__).set_trace()

You can also avoid setting a breakpoint and enter pdb in post-mortem
mode on the first exception

::

   $ nixops --pdb
