Overview
--------

This section gives a quick overview of how to use NixOps.

.. _sec-deploying-to-physical-nixos:

Deploying to a NixOS machine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To deploy to a machine that is already running NixOS, simply set
``deployment.targetHost`` to the IP address or host name of the
machine, and leave ``deployment.targetEnv`` undefined.  See
:ref:`ex-physical-nixos.nix`.

.. _ex-physical-nixos.nix:

:file:`trivial-nixos.nix`: NixOS target physical network specification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   {
      nodes.webserver =
        { config, pkgs, ... }:
        { deployment.targetHost = "1.2.3.4";
        };
    }

Accessing machines
~~~~~~~~~~~~~~~~~~

You can login to individual machines by doing ``nixops ssh *name*``,
where ``*name*`` is the name of the machine.

It’s also possible to perform a command on all machines:

::

    $ nixops ssh-for-each -d load-balancer-ec2 -- df /tmp
    backend1...> /dev/xvdb      153899044 192084 145889336   1% /tmp
    proxy......> /dev/xvdb      153899044 192084 145889336   1% /tmp
    backend2...> /dev/xvdb      153899044 192084 145889336   1% /tmp

By default, the command is executed sequentially on each machine.  You
can add the flag to execute it in parallel.

Checking machine status
~~~~~~~~~~~~~~~~~~~~~~~

The command :command:`nixops check` checks the status of each machine
in a deployment.  It verifies that the machine still exists
(i.e. hasn’t been destroyed outside of NixOps), is up (i.e. the
instance has been started) and is reachable via SSH.  It also checks
that any attached disks (such as EBS volumes) are not in a failed
state, and prints the names of any systemd units that are in a failed
state.

For example, for the 3-machine EC2 network shown above, it might
show:

::

    $ nixops check -d load-balancer-ec2
    +----------+--------+-----+-----------+----------+----------------+---------------+-------+
    | Name     | Exists | Up  | Reachable | Disks OK | Load avg.      | Failed units  | Notes |
    +----------+--------+-----+-----------+----------+----------------+---------------+-------+
    | backend1 | Yes    | Yes | Yes       | Yes      | 0.03 0.03 0.05 | httpd.service |       |
    | backend2 | Yes    | No  | N/A       | N/A      |                |               |       |
    | proxy    | Yes    | Yes | Yes       | Yes      | 0.00 0.01 0.05 |               |       |
    +----------+--------+-----+-----------+----------+----------------+---------------+-------+

This indicates that Apache httpd has failed on``backend1`` and that
machine``backend2`` is not running at all.  In this situation, you
should run :command:`nixops deploy --check` to repair the deployment.

Network special attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~

It is possible to define special options for the whole network. For
example:

::

    {
    network = {
      description = "staging environment";
      enableRollback = true;
    };

    defaults = {
      imports = [ ./common.nix ];
    };

    nodes.machine = { ... }: {};
    }

Each attribute is explained below:

- ``defaults``: applies given NixOS module to all machines defined in the network.

- ``network.description``: a sentence describing the purpose of the
    network for easier comparison when running :command:`nixops list`

- ``network.enableRollback``: if ``true``, each deployment creates a
    new profile generation to able to run :command:`nixops rollback`.
    Defaults to ``false``.

Network arguments
~~~~~~~~~~~~~~~~~

In NixOps you can pass in arguments from outside the nix
expression. The network file can be a nix function, which takes a set
of arguments which are passed in externally and can be used to change
configuration values, or even to generate a variable number of
machines in the network.

Here is an example of a network with network arguments:

::

    { maintenance ? false
    }:
    {
      nodes.machine =
        { config, pkgs, ... }:
        { services.httpd.enable = maintenance;
          ...
        };
    }

This network has a *maintenance* argument that defaults to false. This
value can be used inside the network expression to set NixOS option,
in this case whether or not Apache HTTPD should be enabled on the
system.

You can pass network arguments using the set-args nixops command. For
example, if we want to set the maintenance argument to true in the
previous example, you can run:

::

    $ nixops set-args --arg maintenance true -d argtest

The arguments that have been set will show up:

::

    $ nixops info -d argtest
    Network name: argtest
    Network UUID: 634d6273-f9f6-11e2-a004-15393537e5ff
    Network description: Unnamed NixOps network
    Nix expressions: .../network-arguments.nix*Nix arguments: maintenance = true*

    +---------+---------------+------+-------------+------------+
    | Name    |     Status    | Type | Resource Id | IP address |
    +---------+---------------+------+-------------+------------+
    | machine | Missing / New | none |             |            |
    +---------+---------------+------+-------------+------------+

Running nixops deploy after changing the arguments will deploy the new
configuration.

Managing keys
~~~~~~~~~~~~~

Files in :file:`/nix/store/` are readable by every user on that host,
so storing secret keys embedded in nix derivations is insecure. To
address this, nixops provides the configuration option
`deployment.keys`, which nixops manages separately from the main
configuration derivation for each machine.

Add a key to a machine like so.

::

    {
      nodes.machine =
      { config, pkgs, ... }:
      {
        deployment.keys.my-secret.text = "shhh this is a secret";
        deployment.keys.my-secret.user = "myuser";
        deployment.keys.my-secret.group = "wheel";
        deployment.keys.my-secret.permissions = "0640";
      };
    }

This will create a file :file:`/run/keys/my-secret` with the specified
contents, ownership, and permissions.

Only the contents of the secret is required.
It can be specified using one of the options ``text``, ``keyFile``
or ``keyCommand``. The ``user`` and
``group`` options both default to ``"root"``, and ``permissions``
defaults to ``"0600"``.

Keys from ``deployment.keys`` are stored under :file:`/run/` on a
temporary filesystem and will not persist across a reboot.  To send a
rebooted machine its keys, use :command:`nixops send-keys`. Note that
all :command:`nixops` commands implicitly upload keys when
appropriate, so manually sending keys should only be necessary after
an unattended reboot.

If you have a custom service that depends on a key from
``deployment.keys``, you can opt to let systemd track that
dependency. Each key gets a corresponding systemd service
``"${keyname}-key.service"`` which is active while the key is present,
and otherwise inactive when the key is absent. See
:ref:`key-dependency.nix` for how to set this up.

.. _key-dependency.nix:

:file:`key-dependency.nix`: track key dependence with systemd
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

    {
      nodes.machine =
        { config, pkgs, ... }:
        {
          deployment.keys.my-secret.text = "shhh this is a secret";

          systemd.services.my-service = {
            after = [ "my-secret-key.service" ];
            wants = [ "my-secret-key.service" ];
            script = ''
              export MY_SECRET=$(cat /run/keys/my-secret)
              run-my-program
            '';
          };
        };
    }

These dependencies will ensure that the service is only started when
the keys it requires are present. For example, after a reboot, the
services will be delayed until the keys are available, and
:command:`systemctl status` and friends will lead you to the cause.

Special NixOS module inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~

In deployments with multiple machines, it is often convenient to
access the configuration of another node in the same network, e.g. if
you want to store a port number only once.

This is possible by using the extra NixOS module input ``nodes``.

::

    {
      network.description = "Gollum server and reverse proxy";
      
      nodes = {
        gollum =
          { config, pkgs, ... }:
          {
            services.gollum = {
              enable = true;
              port = 40273;
            };
            networking.firewall.allowedTCPPorts = [ config.services.gollum.port ];
          };

        reverseproxy =
          { config, pkgs, nodes, ... }:
          let
            gollumPort = nodes.gollum.config.services.gollum.port;
          in
          {
            services.nginx = {
              enable = true;
              virtualHosts."wiki.example.net".locations."/" = {
                proxyPass = "http://gollum:${toString gollumPort}";
              };
            };
            networking.firewall.allowedTCPPorts = [ 80 ];
          };
      };
    }

Moving the port number to a different value is now without the risk of
an inconsistent deployment.

Additional module inputs are

- ``name``: The name of the machine.

- ``uuid``: The NixOps UUID of the deployment.

- ``resources``: NixOps resources associated with the deployment.
