Deploying without Root
======================

Requirements
------------

NixOps 2.0 allows for deploying as users other than root, as long
as the deploying user meets two requirements:

1. The user can become root without needing to type a password.
2. Nix considers the user to be a `"trusted user" <https://nixos.org/nix/manual/#conf-trusted-users>`_.

In this guide, we will use passwordless sudo.

We assume:

1. The deploying user's name is "deployer".
2. The target machine's name is "hermes".
3. The target machine is already managed by NixOps.

Steps
-----

1. Configure the target machine according to the listed requirements.
2. Update the NixOps network to use our alternative user.
3. Deploy as the new user.


Configuring the Target Machine
******************************

First, mark the deploying user as trusted:

.. code-block:: nix

  {
    nix.trustedUsers = [ "deployer" ];
  }

This will let the user copy Nix store paths to the target.

Let the deploying user use sudo:

.. code-block:: nix

  {
    users.users.deployer.extraGroups = [ "wheel" ];
  }

Then, we configure the machine to have passwordless sudo:

.. code-block:: nix

  {
    security.sudo.wheelNeedsPassword = false;
  }

Now use NixOps to deploy these changes to the server before taking
the next step.

Configuring the NixOps Network
******************************

Edit your nixops.nix to specify the machine's
``deployment.targetUser``:

.. code-block:: nix

  {
    network.description = "Non-root deployment";

    nodes.hermes =
      { resources, ... }:
      {
        deployment.targetUser = "deployer";
      };
  }


Testing our Changes
*******************

Then, run ``nixops deploy`` to update the NixOps database. This deploy
will use your "deployer" user instead of root.

Try running ``nixops ssh``, and see that you are logged in as
"deployer".

Notes
-----

* NixOps caches the target user and related variables in its state
  file, and commands like ``nixops send-keys`` and ``ssh`` use the
  cached data. After changing these values, run ``nixops deploy`` to
  update the cache.
