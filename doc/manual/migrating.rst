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

.. _sec-state:
