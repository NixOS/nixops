.. _chap-overview:

Overview
========

This chapter aims to provide guidelines on migrating from NixOps 1.x to 2.0.

.. _sec-layout:

Code layout changes
-------------------

Using NixOps 1.0 multiple deployments spread out over the file and deployed
from any working directory with the ``--deployment (-d)`` parameter.

NixOps 2 however requires a file relative to the invocation working directory.
It needs to be called either ``nixops.nix`` for a traditional deployment or
``flake.nix`` for the as of yet experimental
`flakes support <https://github.com/tweag/rfcs/blob/flakes/rfcs/0049-flakes.md>`.

.. _sec-state-location:

State location
--------------

In NixOps 1.0 deployment state such as provisioned resources are stored in a
SQLite database located in ``~/.nixops``.

NixOps 2 however has pluggable state backends, meaning that you will have to
make a choice where to store this state.

To implement the old behaviour of loading deployment state from the SQLite
database located in ``~/.nixops`` add the following snippet to your deployment:

::
   {
     network = {
       storage.legacy = {};
     };
   }

To implement a fire-and-forget strategy use this code snippet:

::
  {
    network = {
      storage.memory = {};
    };
  }

For additional state storage strategies see the various NixOps plugins.

.. _sec-state-migration:

State migration
---------------

Migrating to any non-legacy backend from a previous deployment requires a
manual migration step.

#. Start by configuring the legacy backend as such::
   {
     network = {
       storage.legacy = {};
     };
   }

#. Then export the current state::
   nixops export > state.json

#. Now go ahead and configure your desired state backend.

#. And finally import the old state::
   nixops import < state.json

#. Make sure to remove ``state.json`` as it may contain deployment secrets.
