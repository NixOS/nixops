Description
===========

NixOps is a tool for deploying NixOS machines in a network or cloud.

Common options
==============

``--state``; ``-s``
   Path to the state file that contains the deployments. It defaults to
   the value of the NIXOPS_STATE environment variable, or
   ``~/.nixops/deployments.nixops`` if that one is not defined. It must
   have extension ``.nixops``. The state file is actually a SQLite
   database that can be inspected using the ``sqlite3`` command (for
   example, ``sqlite3 deployments.nixops .dump``). If it does not exist,
   it is created automatically.

``--deployment``; ``-d``
   UUID or symbolic name of the deployment on which to operate. Defaults
   to the value of the NIXOPS_DEPLOYMENT environment variable.

``--confirm``
   Automatically confirm “dangerous” actions, such as terminating EC2
   instances or deleting EBS volumes. Without this option, you will be
   asked to confirm each dangerous action interactively.

``--debug``
   Turn on debugging output. In particular, this causes NixOps to print
   a Python stack trace if an unhandled exception occurs.

``--help``
   Print a brief summary of NixOps’s command line syntax.

``--version``
   Print NixOps’s version number.

Common options passed along to Nix
==================================

``-I``
   Append a directory to the Nix search path.

``--max-jobs``
   Set maximum number of concurrent Nix builds.

``--cores``
   Sets the value of the NIX_BUILD_CORES environment variable in the
   invocation of builders

``--keep-going``
   Keep going after failed builds.

``--keep-failed``
   Keep temporary directories of failed builds.

``--show-trace``
   Print a Nix stack trace if evaluation fails.

``--fallback``
   Fall back on installation from source.

``--option``
   Set a Nix option.

``--read-only-mode``
   Run Nix evaluations in read-only mode.

Environment variables
=====================

NIXOPS_STATE
   The location of the state file if ``--state`` is not used. It
   defaults to ``~/.nixops/deployments.nixops``.

NIXOPS_DEPLOYMENT
   UUID or symbolic name of the deployment on which to operate. Can be
   overridden using the ``-d`` option.

EC2_ACCESS_KEY; AWS_ACCESS_KEY_ID
   AWS Access Key ID used to communicate with the Amazon EC2 cloud. Used
   if ``deployment.ec2.accessKeyId`` is not set in an EC2 machine’s
   configuration.

EC2_SECRET_KEY; AWS_SECRET_ACCESS_KEY
   AWS Secret Access Key used to communicate with the Amazon EC2 cloud.
   It is only used if no secret key corresponding to the AWS Access Key
   ID is defined in ``~/.ec2-keys`` or ``~/.aws/credentials``.

AWS_SHARED_CREDENTIALS_FILE
   Alternative path to the the shared credentials file, which is located
   in ``~/.aws/credentials`` by default.

HETZNER_ROBOT_USER; HETZNER_ROBOT_PASS
   Username and password used to access the Robot for Hetzner
   deployments.

GCE_PROJECT
   GCE Project which should own the resources in the Google Compute
   Engine deployment. Used if ``deployment.gce.project`` is not set in a
   GCE machine configuration and if ``resources.$TYPE.$NAME.project`` is
   not set in a GCE resource specification.

GCE_SERVICE_ACCOUNT; ACCESS_KEY_PATH
   GCE Service Account ID and the path to the corresponding private key
   in .pem format which should be used to manage the Google Compute
   Engine deployment. Used if ``deployment.gce.serviceAccount`` and
   ``deployment.gce.accessKey`` are not set in a GCE machine
   configuration and if ``resources.$TYPE.$NAME.serviceAccount`` and
   ``resources.$TYPE.$NAME.accessKey`` are not set in a GCE resource
   specification.

Files
=====

``~/.ec2-keys``
   This file maps AWS Access Key IDs to their corresponding Secret
   Access Keys. Each line must consist of an Access Key IDs, a Secret
   Access Keys and an optional symbolic identifier, separated by
   whitespace. Comments starting with ``#`` are stripped. An example:

   ::

      AKIABOGUSACCESSKEY BOGUSSECRETACCESSKEY dev # AWS development account
      AKIABOGUSPRODACCESSKEY BOGUSPRODSECRETACCESSKEY prod # AWS production account

   The identifier can be used instead of actual Access Key IDs in
   ``deployment.ec2.accessKeyId``, e.g.

   ::

      deployment.ec2.accessKeyId = "prod";

   This is useful if you have an AWS account with multiple user accounts
   and you don’t want to hard-code an Access Key ID in a NixOps
   specification.

``~/.aws/credentials``
   This file pairs AWS Access Key IDs with their corresponding Secret
   Access Keys under symbolic profile names. It consists of sections
   marked by profile names. Sections contain newline-separated
   "assignments" of "variables" ``aws_access_key_id`` and
   ``aws_secret_access_key`` to a desired Access Key ID and a Secret
   Access Key, respectively, e.g.:

   ::

      [dev]
      aws_access_key_id = AKIABOGUSACCESSKEY
      aws_secret_access_key = BOGUSSECRETACCESSKEY

      [prod]
      aws_access_key_id = AKIABOGUSPRODACCESSKEY
      aws_secret_access_key = BOGUSPRODSECRETACCESSKEY

   Symbolic profile names are specified in
   ``deployment.ec2.accessKeyId``, e.g.:

   ::

      deployment.ec2.accessKeyId = "prod";

   If an actual Access Key IDs is used in ``deployment.ec2.accessKeyId``
   its corresponding Secret Access Key is looked up under ``[default]``
   profile name. Location of credentials file can be customized by
   setting the AWS_SHARED_CREDENTIALS_FILE environment variable.

Command ``nixops create``
=========================

Synopsis
--------

nixops create
nixexprs
-I
path
Description
-----------

This command creates a new deployment state record in NixOps’s database.
The paths of the Nix expressions that specify the desired deployment
(nixexprs) are stored in the state file. The UUID of the new deployment
is printed on standard output.

Options
-------

``-I`` path
   Add path to the Nix expression search path for all future evaluations
   of the deployment specification. NixOps stores path in the state
   file. This option may be given multiple times. See the description of
   the ``-I`` option in nix-instantiate1 for details.

``--deployment``; ``-d``
   Set the symbolic name of the new deployment to the given string. The
   name can be used to refer to the deployment by passing the option
   ``-d name`` or the environment variable ``NIXOPS_DEPLOYMENT=name`` to
   subsequent NixOps invocations. This is typically more convenient than
   using the deployment’s UUID. However, names are not required to be
   unique; if you create multiple deployments with the same name, NixOps
   will complain.

Examples
--------

To create a deployment with symbolic name ``foo``, and then perform the
actual deployment:

::

   $ nixops create expr1.nix expr2.nix -d foo
   created deployment ‘32b06868-d27c-11e2-a055-81d7beb7925e’

   $ nixops deploy -d foo

Command ``nixops modify``
=========================

Synopsis
--------

nixops modify
nixexprs
--name
-n
name
-I
path
Description
-----------

This command modifies an existing deployment. The options are the same
as for ``nixops create``. The symbolic name of the deployment can be
changed using the ``--name`` flag.

Examples
--------

To change the Nix expressions specifying the deployment, and rename it
from ``foo`` to ``bar``:

::

   $ nixops modify -d foo -n bar expr3.nix expr4.nix

Note that ``-d`` identifies the existing deployment, while ``-n``
specifies its new name.

Command ``nixops clone``
========================

Synopsis
--------

nixops clone
--name
-n
name
Description
-----------

This command clones an existing deployment; that is, it creates a new
deployment that has the same deployment specification and parameters,
but a different UUID and (optionally) name. Note that ``nixops clone``
does not currently clone the state of the machines in the existing
deployment. Thus, when you first run ``nixops deploy`` on the cloned
deployment, NixOps will create new instances from scratch.

Examples
--------

To create a new deployment ``bar`` by cloning the deployment ``foo``:

::

   $ nixops clone -d foo -n bar

Command ``nixops delete``
=========================

Synopsis
--------

nixops delete
--all
--force
Description
-----------

This command deletes a deployment from the state file. NixOps will
normally refuse to delete the deployment if any resources belonging to
the deployment (such as virtual machines) still exist. You must run
``nixops destroy`` first to get rid of any such resources. However, if
you pass ``--force``, NixOps will forget about any still-existing
resources; this should be used with caution.

If the ``--all`` flag is given, all deployments in the state file are
deleted.

Examples
--------

To delete the deployment named ``foo``:

::

   $ nixops delete -d foo

Command ``nixops deploy``
=========================

Synopsis
--------

nixops deploy
--kill-obsolete
-k
--dry-run
--repair
--create-only
--build-only
--copy-only
--check
--allow-reboot
--force-reboot
--allow-recreate
--include
machine-name
--exclude
machine-name
-I
path
--max-concurrent-copy
N
Description
-----------

This command deploys a set of machines on the basis of the specification
described by the Nix expressions given in the preceding
``nixops create`` call. It creates missing virtual machines, builds each
machine configuration, copies the closure of each configuration to the
corresponding machine, uploads any keys described in
``deployment.keys``, and activates the new configuration.

Options
-------

``--kill-obsolete``; ``-k``
   Destroy (terminate) virtual machines that were previously created as
   part of this deployment, but are obsolete because they are no longer
   mentioned in the deployment specification. This happens if you remove
   a machine from the specification after having run ``nixops deploy``
   to create it. Without this flag, such obsolete machines are left
   untouched.

``--dry-run``
   Dry run; show what would be done by this command without actually
   doing it.

``--repair``
   Use --repair when calling nix-build. This is useful for repairing the
   nix store when some inconsistency is found and nix-copy-closure is
   failing as a result. Note that this option only works in nix setups
   that run without the nix daemon.

``--create-only``
   Exit after creating any missing machines. Nothing is built and no
   existing machines are touched.

``--build-only``
   Just build the configuration locally; don’t create or deploy any
   machines. Note that this may fail if the configuration refers to
   information only known after machines have been created (such as IP
   addresses).

``--copy-only``
   Exit after creating missing machines, building the configuration and
   copying closures to the target machines; i.e., do everything except
   activate the new configuration.

``--check``
   Normally, NixOps assumes that the deployment state of machines
   doesn’t change behind its back. For instance, it assumes that a
   VirtualBox VM, once started, will continue to run unless you run
   ``nixops destroy`` to terminate it. If this is not the case, e.g.,
   because you shut down or destroyed a machine through other means, you
   should pass the ``--check`` option to tell NixOps to verify its
   current knowledge.

``--allow-reboot``
   Allow NixOps to reboot the instance if necessary. For instance, if
   you change the type of an EC2 instance, NixOps must stop, modify and
   restart the instance to effectuate this change.

``--force-reboot``
   Reboot the machine to activate the new configuration (using
   ``nixos-rebuild boot``).

``--allow-recreate``
   Recreate resources that have disappeared (e.g. destroyed through
   mechanisms outside of NixOps). Without this flag, NixOps will print
   an error if a resource that should exist no longer does.

``--include`` machine-name...
   Only operate on the machines explicitly mentioned here, excluding
   other machines.

``--exclude`` machine-name...
   Only operate on the machines that are *not* mentioned here.

``-I`` path
   Add path to the Nix expression search path. This option may be given
   multiple times and takes precedence over the ``-I`` flags used in the
   preceding ``nixops create`` invocation. See the description of the
   ``-I`` option in nix-instantiate1 for details.

``--max-concurrent-copy`` N
   Use at most N concurrent ``nix-copy-closure`` processes to deploy
   closures to the target machines. N defaults to 5.

Examples
--------

To deploy all machines:

::

   $ nixops deploy

To deploy only the logical machines ``foo`` and ``bar``, checking
whether their recorded deployment state is correct:

::

   $ nixops deploy --check --include foo bar

To create any missing machines (except ``foo``) without doing anything
else:

::

   $ nixops deploy --create-only --exclude foo

Command ``nixops destroy``
==========================

Synopsis
--------

nixops destroy
--all
--include
machine-name
--exclude
machine-name
Description
-----------

This command destroys (terminates) all virtual machines previously
created as part of this deployment, and similarly deletes all disk
volumes if they’re marked as “delete on termination”. Unless you pass
the ``--confirm`` option, you will be asked to approve every machine
destruction.

This command has no effect on machines that cannot be destroyed
automatically; for instance, machines in the ``none`` target environment
(such as physical machines, or virtual machines not created by NixOps).

Options
-------

``--all``
   Destroy all deployments.

``--include`` machine-name...
   Only destroy the machines listed here.

``--exclude`` machine-name...
   Destroy all machines except the ones listed here.

Examples
--------

To destroy all machines:

::

   $ nixops destroy

To destroy the machine named ``foo``:

::

   $ nixops destroy --include foo

Command ``nixops stop``
=======================

Synopsis
--------

nixops stop
--include
machine-name
--exclude
machine-name
Description
-----------

This command stops (shuts down) all non-obsolete machines that can be
automatically started. This includes EC2 and VirtualBox machines, but
not machines using the ``none`` backend (because NixOps doesn’t know how
to start them automatically).

Options
-------

``--include`` machine-name...
   Only stop the machines listed here.

``--exclude`` machine-name...
   Stop all machines except the ones listed here.

Examples
--------

To stop all machines that support being stopped:

::

   $ nixops stop

Command ``nixops start``
========================

Synopsis
--------

nixops start
--include
machine-name
--exclude
machine-name
Description
-----------

This command starts all non-obsolete machines previously stopped using
``nixops stop``.

Options
-------

``--include`` machine-name...
   Only start the machines listed here.

``--exclude`` machine-name...
   Start all machines except the ones listed here.

Examples
--------

To start all machines that were previously stopped:

::

   $ nixops start

Command ``nixops list``
=======================

Synopsis
--------

nixops list
Description
-----------

This command prints information about all deployments in the database:
the UUID, the name, the description, the number of running or stopped
machines, and the types of those machines.

Examples
--------

::

   $ nixops list
   +--------------------------------------+------------------------+------------------------+------------+------------+
   |                 UUID                 |          Name          |      Description       | # Machines |    Type    |
   +--------------------------------------+------------------------+------------------------+------------+------------+
   | 80dc8e11-287d-11e2-b05a-a810fd2f513f |          test          |      Test network      |     4      |    ec2     |
   | 79fe0e26-d1ec-11e1-8ba3-a1d56c8a5447 |   nixos-systemd-test   | Unnamed NixOps network |     1      | virtualbox |
   | 742c2a4f-0817-11e2-9889-49d70558c59e |       xorg-test        | NixOS X11 Updates Test |     0      |            |
   +--------------------------------------+------------------------+------------------------+------------+------------+

Command ``nixops info``
=======================

Synopsis
--------

nixops info
--all
--plain
--no-eval
Description
-----------

This command prints some information about the current state of the
deployment. For each machine, it prints:

-  The logical name of the machine.

-  Its state, which is one of ``New`` (not deployed yet), ``Up``
   (created and up to date), ``Outdated`` (created but not up to date
   with the current configuration, e.g. due to use of the ``--exclude``
   option to ``nixops deploy``) and ``Obsolete`` (created but no longer
   present in the configuration).

-  The type of the machine (i.e. the value of ``deployment.targetEnv``,
   such as ``ec2``). For EC2 machines, it also shows the machine’s
   region or availability zone.

-  The virtual machine identifier, if applicable. For EC2 machines, this
   is the instance ID. For VirtualBox VMs, it’s the virtual machine
   name.

-  The IP address of the machine. This is its public IP address, if it
   has one, or its private IP address otherwise. (For instance,
   VirtualBox machines only have a private IP address.)

Options
-------

``--all``
   Print information about all resources in all known deployments,
   rather than in a specific deployment.

``--plain``
   Print the information in a more easily parsed format where columns
   are separated by tab characters and there are no column headers.

``--no-eval``
   Do not evaluate the deployment specification. Note that as a
   consequence the “Status” field in the output will show all machines
   as “Obsolete” (since the effective deployment specification is
   empty).

Examples
--------

::

   $ nixops info -d foo
   Network name: test
   Network UUID: 80dc8e11-287d-11e2-b05a-a810fd2f513f
   Network description: Test network
   Nix expressions: /home/alice/test-network.nix

   +----------+-----------------+------------------------------+------------+-----------------+
   |   Name   |      Status     |             Type             |   VM Id    |    IP address   |
   +----------+-----------------+------------------------------+------------+-----------------+
   | backend0 |  Up / Outdated  | ec2 [us-east-1b; m2.2xlarge] | i-905e9def |   23.23.12.249  |
   | backend1 |  Up / Outdated  | ec2 [us-east-1b; m2.2xlarge] | i-925e9ded |  184.73.128.122 |
   | backend2 |  Up / Obsolete  | ec2 [us-east-1b; m2.2xlarge] | i-885e9df7 | 204.236.192.216 |
   | frontend | Up / Up-to-date |  ec2 [us-east-1c; m1.large]  | i-945e9deb |  23.23.161.169  |
   +----------+-----------------+------------------------------+------------+-----------------+

Command ``nixops check``
========================

Synopsis
--------

nixops check
--all
Description
-----------

This command checks and prints the status of each machine in the
deployment. For instance, for an EC2 machine, it will ask EC2 whether
the machine is running or stopped. If a machine is supposed to be up,
NixOps will try to connect to the machine via SSH and get the current
load average statistics.

Options
-------

``--all``
   Check all machines in all known deployments, rather than in a
   specific deployment.

Examples
--------

For a running VirtualBox instance, NixOps will print something like:

::

   $ nixops check
   machine> VM state is ‘running’
   machine> pinging SSH... up [1.03 0.34 0.12]

For a stopped EC2 instance, NixOps might show:

::

   machine> instance state is ‘stopped’

Command ``nixops ssh``
======================

Synopsis
--------

nixops ssh
username
@
machine
command
args
Description
-----------

This command opens an SSH connection to the specified machine and
executes the specified command. If no command is specified, an
interactive shell is started. If no user is specified, the machines
``deployment.targetUser`` is used.

Options
-------

``--include-keys``
   Include the public SSH host keys into .ssh/known_hosts for all
   machines in the imported network.

Examples
--------

To start a shell on machine ``foo``:

::

   $ nixops ssh foo

To run Emacs on machine ``bar``:

::

   $ nixops ssh bar -- -X emacs

Passes ``-X`` (“enable X11 forwarding”) to SSH.

Command ``nixops ssh-for-each``
===============================

Synopsis
--------

nixops ssh-for-each
--parallel
-p
--include
machine-name
--exclude
machine-name
command
args
Description
-----------

This operation executes the specified shell command on all non-obsolete
machines.

Options
-------

``--parallel``
   Execute the command on each machine in parallel. The default is to do
   each machine sequentially.

``--include`` machine-name...
   Execute the command only on the machines listed here.

``--exclude`` machine-name...
   Execute the command on all machines except the ones listed here.

Examples
--------

To reboot all machines in parallel:

::

   $ nixops ssh-for-each -p reboot

Command ``nixops mount``
========================

Synopsis
--------

nixops mount
--option
-o
option
username
@
machine
:
remote
local
Description
-----------

This command mounts the directory remote in the file system of the
specified machine onto the directory local in the local file system. If
``:remote`` is omitted, the entire remote file system is mounted. If you
specify an empty path (i.e. ``:``), then the home directory of the
specified user is mounted. If no user is specified, the machines
``deployment.targetUser`` is used.

This command is implemented using ``sshfs``, so you must have ``sshfs``
installed and the ``fuse`` kernel module loaded.

Options
-------

``--option`` / ``-o`` opt
   Pass additional options to ``sshfs``. See sshfs1 for details.

Examples
--------

To mount the entire file system of machine ``foo`` onto the local
directory ``~/mnt``:

::

   $ nixops mount foo ~/mnt

   $ ls -l ~/mnt
   total 72
   drwxr-xr-x 1 root  root   4096 Jan 15 11:44 bin
   drwx------ 1 root  root   4096 Jan 14 17:15 boot
   …

To mount the home directory of user ``alice``:

::

   $ nixops mount alice@foo: ~/mnt

To mount a specific directory, passing the option ``transform_symlinks``
to ensure that absolute symlinks in the remote file system work
properly:

::

   $ nixops mount foo:/data ~/mnt -o transform_symlinks

Command ``nixops reboot``
=========================

Synopsis
--------

nixops reboot
--include
machine-name
--exclude
machine-name
--no-wait
command
args
Description
-----------

This command reboots all non-obsolete machines in parallel.

Options
-------

``--include`` machine-name...
   Only reboot the machines listed here.

``--exclude`` machine-name...
   Reboot all machines except the ones listed here.

``--no-wait``
   Do not wait until the machines have finished rebooting.

Examples
--------

To reboot all machines except ``foo`` and wait until they’re up again,
that is, are reachable via SSH again:

::

   $ nixops reboot --exclude foo

Command ``nixops backup``
=========================

Synopsis
--------

nixops backup
--include
machine-name
--exclude
machine-name
Description
-----------

This command makes a backup of all persistent disks of all machines.
Currently this is only implemented for EC2 EBS instances/volumes.

Options
-------

``--include`` machine-name...
   Only backup the persistent disks of the machines listed here.

``--exclude`` machine-name...
   Backup the persistent disks of all machines except the ones listed
   here.

Examples
--------

To backup the persistent disks of all machines:

::

   $ nixops backup

Command ``nixops restore``
==========================

Synopsis
--------

nixops restore
--include
machine-name
--exclude
machine-name
--backup-id
backup-id
Description
-----------

This command restores a machine to a backup.

Options
-------

``--include`` machine-name...
   Only backup the persistent disks of the machines listed here.

``--exclude`` machine-name...
   Restore the persistent disks of all machines to a given backup except
   the ones listed here.

``--devices`` device-name...
   Restore only the persistent disks which are mapped to the specified
   device names.

``--backup-id``\ backup-id
   Restore the persistent disks of all machines to a given backup except
   the ones listed here.

Examples
--------

To list the available backups and restore the persistent disks of all
machines to a given backup:

::

               $ nixops backup-status
               $ nixops restore --backup-id 20120803151302

Restore the persistent disks at device /dev/xvdf of all machines to a
given backup:

::

               $ nixops restore --devices /dev/xvdf --backup-id 20120803151302

Command ``nixops show-option``
==============================

Synopsis
--------

nixops show-option
--xml
machine
option
Description
-----------

This command prints the value of the specified NixOS configuration
option for the specified machine.

Examples
--------

::

   $ nixops show-option machine services.xserver.enable
   false

   $ nixops show-option --xml machine boot.initrd.availableKernelModules
   <?xml version='1.0' encoding='utf-8'?>
   <expr>
     <list>
       <string value="md_mod" />
       <string value="raid0" />
       …
     </list>
   </expr>

Command ``nixops set-args``
===========================

Synopsis
--------

nixops set-args
--arg
name
value
--argstr
name
value
--unset
name
Description
-----------

This command persistently sets arguments to be passed to the deployment
specification.

Options
-------

``--arg`` name value
   Set the function argument name to value, where the latter is an
   arbitrary Nix expression.

``--argstr`` name value
   Like ``--arg``, but the value is a literal string rather than a Nix
   expression. Thus, ``--argstr name value`` is equivalent to
   ``--arg name \"value\"``.

``--unset`` name
   Remove a previously set function argument.

Examples
--------

Consider the following deployment specification (``servers.nix``):

::

   { nrMachines, active, lib }:

   with lib;

   let

     makeMachine = n: nameValuePair "webserver-${toString n}"
       ({ config, pkgs, ... }:
       { deployment.targetEnv = "virtualbox";
         services.httpd.enable = active;
         services.httpd.adminAddr = "foo@example.org";
       });

   in { nodes = listToAttrs (map makeMachine (range 1 nrMachines)); }

This specifies a network of nrMachines identical VirtualBox VMs that run
the Apache web server if active is set. To create 10 machines without
Apache:

::

   $ nixops create servers.nix
   $ nixops set-args --arg nrMachines 10 --arg active false
   $ nixops deploy

Next we can enable Apache on the existing machines:

::

   $ nixops set-args --arg active true
   $ nixops deploy

or provision additional machines:

::

   $ nixops set-args --arg nrMachines 20
   $ nixops deploy

Command ``nixops show-console-output``
======================================

Synopsis
--------

nixops show-console-output
machine
Description
-----------

This command prints the console output of the specified machine, if
available. Currently this is only supported for the EC2 backend.

Examples
--------

::

   $ nixops show-console-output machine
   Xen Minimal OS!
   [    0.000000] Initializing cgroup subsys cpuset
   [    0.000000] Initializing cgroup subsys cpu
   [    0.000000] Linux version 3.2.36 (nixbld@) (gcc version 4.6.3 (GCC) ) #1 SMP Fri Jan 4 16:07:14 UTC 2013
   …

Command ``nixops export``
=========================

Synopsis
--------

nixops export
--all
Description
-----------

This command exports the state of the specified deployment, or all
deployments if ``--all`` is given, as a JSON representation to standard
output. The deployment(s) can be imported into another state file using
``nixops import``.

Examples
--------

To export a specific deployment, and import it into the state file
``other.nixops``:

::

   $ nixops export -d foo > foo.json
   $ nixops import -s other.nixops < foo.json
   added deployment ‘2bbaddca-01cb-11e2-88b2-19d91ca51c50’

If desired, you can then remove the deployment from the old state file:

::

   $ nixops delete -d foo --force

To export all deployments:

::

   $ nixops export --all > all.json

Command ``nixops import``
=========================

Synopsis
--------

nixops import
--include-keys
Description
-----------

This command creates deployments from the state data exported by
``nixops export``. The state is read from standard input. See
``nixops export`` for examples.

Command ``nixops send-keys``
============================

Synopsis
--------

nixops send-keys
--include
machine-name
--exclude
machine-name
Description
-----------

This command uploads the keys described in ``deployment.keys`` to remote
machines in the ``/run/keys/`` directory.

Keys are *not* persisted across reboots by default. If a machine reboot
is triggered from outside ``nixops``, it will need ``nixops send-keys``
to repopulate its keys.

Note that ``nixops deploy`` does an implicit ``send-keys`` where
appropriate, so manually sending keys is only necessary after unattended
reboots.

Options
-------

``--include`` machine-name...
   Only operate on the machines explicitly mentioned here, excluding
   other machines.

``--exclude`` machine-name...
   Only operate on the machines that are *not* mentioned here.
