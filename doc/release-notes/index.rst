Release notes
=============

Release 2.0
-----------

- Code base has been migrated to Python 3.

- Code base has been statically typed with Mypy.

- Backends are now developed as separate plugins.

- Poetry & Poetry2nix are used for packaging.

- Separate state backends for storing state.

- Major code cleanups.

- Now the network specification is using the module system from ``nixpkgs.lib``
  - Now network specification files can import other files via ``imports``.
  - We have a ``nodes.*`` option where we put every NixOS configuration for the configured nodes. We suggest to use it instead of defining nodes in the top level.

- Removed NixOS Options

  - ``deployment.autoLuks.*`` - moved to `nixos-modules-contrib`_.
  - ``deployment.autoRaid0.*`` - moved to `nixos-modules-contrib`_.

- Notable Files Removed

  - ``nix/adhoc-cloud-vm.nix`` (`#1303`_, `#1312`_) - the included behavior was
    not targeted to any specific use case or generic to support all
    cloud VMs.


  - ``nix/auto-luks.nix`` (`#1297`_, `#1312`_) - the module is now
    nixos-modules-contrib_, since its behavior was not specific to
    NixOps, and outside of the core feature set of NixOps.

  - ``nix/auto-raid0.nix`` (`#1299`_, `#1312`_) - the module is now
    nixos-modules-contrib_, since its behavior was not specific to
    NixOps, and outside of the core feature set of NixOps.

  - ``nixops/data/nixos-infect`` (`#1305`_, `#1312`_) - plugins needing
    nixos-infect should include it themselves.

- Too many other features/fixes to count.
  See `#1242`_ for more insight.

.. _nixos-modules-contrib: https://github.com/nix-community/nixos-modules-contrib
.. _#1297: https://github.com/NixOS/nixops/pull/1297
.. _#1299: https://github.com/NixOS/nixops/pull/1299
.. _#1303: https://github.com/NixOS/nixops/pull/1303
.. _#1305: https://github.com/NixOS/nixops/pull/1305
.. _#1312: https://github.com/NixOS/nixops/pull/1312
.. _#1242: https://github.com/NixOS/nixops/issues/1242

This release has contributions by:
- Aaron Hall
- Adam Höse
- Adam Mccullough
- Amine Chikhaoui
- Andreas Rammhold
- Andrey Golovizin
- Antoine Eiche
- Benjamin Hipple
- Bernardo Meurer
- Chaker Benhamed
- Cole Helbling
- David Kleuker
- Davíð Steinn Geirsson
- Domen Kožar
- Eelco Dolstra
- Florian Klink
- Graham Christensen
- Jean-baptiste Musso
- Jeff Slight
- Jleeuwes
- John A. Lotoski
- John Lotoski
- Joseph Lucas
- Lenz Weber
- Lorenzo Manacorda
- Luke Bentley-fox
- Matthieu Coudron
- Maximilian Bosch
- Mazen.homrane
- Michael Fellinger
- Nathan Van Doorn
- Niklas Hambüchen
- Pascal Wittmann
- Pixelkind
- Psyanticy
- Regnat
- Robert Hensing
- Ryan Mulligan
- Samuel Leathers
- Shay Bergmann
- Tanner Doshier
- Tewfik Ghariani
- Tobias Pflug
- Tom Bereknyei
- Tomasz Rybarczyk
- Victor Multun Collod
- Vika
- Vladimir Serov
- Wout Mertens
- Yc.s

.. _ssec-relnotes-1.7:

Release 1.7 (April 17, 2019)
----------------------------

-  General

   -  Mitigation for ``ssh StrictHostKeyChecking=no`` issue.

   -  Fix ``nixops info --plain`` output.

   -  Documentation fixes: add AWS VPC resources and fix some outdated
      command outputs.

   -  Addition of Hashicorp's Vault AppRole resource.

-  AWS

   -  Add more auto retries to api calls to prevent eventual consistency
      issues.

   -  Fix ``nixops check`` with NVMe devices.

   -  Route53: normalize DNS hostname.

   -  S3: support bucket lifecycle configuration as well as versioning.

   -  S3: introduce ``persistOnDestroy`` for S3 buckets which allows keeping
      the bucket during a destroy for later usage

   -  Fix backup-status output when backup is performed on a subset of
      devices.

-  Datadog

   -  add tags for Datadog monitors

-  GCE

   -  Fix machines being leaked when running destroy after a stop
      operation.

   -  make sure the machine exists before attempting a destroy.

-  Hetzner

   -  Remove usage of local commands for network configuration.

         **Warning**

         Note that this is incompatible with NixOS versions prior to
         18.03, see
         `release-notes. <https://nixos.org/nixos/manual/release-notes.html#sec-release-18.03-notable-changes>`__

-  VirtualBox

   -  added NixOS 18.09/19.03 images.

   -  handle deleted VMs from outside NixOps.

This release has contributions from Amine Chikhaoui, Assassinkin,
aszlig, Aymen Memni, Chaker Benhamed, Chawki Cheikch, David Kleuker,
Domen Kožar, Dorra Hadrich, dzanot, Eelco Dolstra, Jörg Thalheim,
Kosyrev Serge, Max Wilson, Michael Bishop, Niklas Hambüchen, Pierre
Bourdon, PsyanticY, Robert Hensing.

.. _ssec-relnotes-1.6.1:

Release 1.6.1 (Sep 14, 2018)
----------------------------

-  General

   -  Fix the deployment of machines with a large number of keys.

   -  Show exit code of configuration activation script, when it is
      non-zero.

   -  Ignore evaluation errors in destroy and delete operations.

   -  Removed top-level Exception catch-all

   -  Minor bugfixes.

-  AWS

   -  Automatically retry certain API calls.

   -  Fixed deployment errors when ``deployment.route53.hostName``
      contains uppercase letters.

   -  Support for GCE routes.

   -  Support attaching NVMe disks.

-  GCE

   -  Add labels for GCE volumes and snapshots.

   -  Add option to enable IP forwarding.

-  VirtualBox

   -  Use images from nixpkgs if available.

This release has contributions from Amine Chikhaoui, aszlig, Aymen
Memni, Chaker Benhamed, Domen Kožar, Eelco Dolstra, Justin Humm, Michael
Bishop, Niklas Hambüchen, Rob Vermaas, Sergei Khoma.

.. _ssec-relnotes-1.6:

Release 1.6 (Mar 28, 2018)
--------------------------

-  General

   -  JSON output option for ``show-option`` command.

   -  Added experimental ``--show-plan`` to ``deploy`` command. Only
      works for VPC resources currently.

-  Backend: libvirtd

   -  Added support for custom kernel/initrd/cmdline, for easier kernel
      testing/developing.

   -  Fail early when defining domain.

   -  Support NixOS 18.03

-  Backend: AWS/EC2

   -  Allow changing security groups for instances that were deployed
      with a default VPC (no explicit subnetId/vpc)

   -  Make sure EC2 key pair not destroyed when it is in use, instead
      produce error.

   -  Support for separate Route53 resources.

   -  Support CloudWatch metrics and alarms.

   -  Support updating IAM instance profile of an existing instance.

   -  Support VPC resources.

   -  RDS: allow multiple security groups.

   -  Allow S3 buckets to be configured as websites.

   -  Fix issue where S3 bucket policy was only set on initial deploy.

-  Backend: Datadog

   -  Support sending start/finish of deploy and destroy events.

   -  Support setting downtime during deployment.

-  Backend: Azure

   -  Fix Azure access instructions.

-  Backend: Google Compute

   -  Add support for labelling GCE instances

   -  Minor fixes to make GCE backend more consistent with backends such
      as EC2.

   -  Fix attaching existing volumes to instances.

   -  Implemented ``show-physical --backup`` for GCE, similar to EC2.

   -  Prevent google-instance-setup service from replacing the host key
      deployed by NixOps.

   -  Allow instances to be created inside VPC subnets.

This release has contributions from Adam Scott, Amine Chikhaoui, Anthony
Cowley, Brian Olsen, Daniel Kuehn, David McFarland, Domen Kožar, Eelco
Dolstra, Glenn Searby, Graham Christensen, Masato Yonekawa, Maarten
Hoogendoorn, Matthieu Coudron, Maximilian Bosch, Michael Bishop, Niklas
Hambüchen, Oussama Elkaceh, Pierre-Étienne Meunier, Peter Jones, Rob
Vermaas, Samuel Leathers, Shea Levy, Tomasz Czyż, Vaibhav Sagar.

.. _ssec-relnotes-1.5.2:

Release 1.5.2 (Oct 29, 2017)
----------------------------

-  General

   -  This release has various minor bug and documentation fixes.

   -  #703: don't ask for known host if file doesn't exist.

   -  Deprecated ``--evaluate-only`` for ``--dry-run``.

-  Backend: libvirtd

   -  Added domainType option.

   -  Make the libvirt images readable only by their owner/group.

   -  Create "persistent" instead of "transient" domains, this ensures
      that nixops deployments/VMs survive a reboot.

   -  Stop using disk backing file and use self contained images.

-  Backend: EC2

   -  #652, allow securityGroups of Elastic File System mount target to
      be set.

   -  #709: allow Elastic IP resource for security group sourceIP
      attribute.

-  Backend: Azure

   -  Use Azure images from nixpkgs, if they are available.

-  Backend: Google Compute

   -  Use Google Compute images from nixpkgs, if they are available.

This release has contributions from Andreas Rammhold, Bjørn Forsman,
Chris Van Vranken, Corbin, Daniel Ehlers, Domen Kožar, Johannes
Bornhold, John M. Harris, Jr, Kevin Quick, Kosyrev Serge, Marius
Bergmann, Nadrieril, Rob Vermaas, Vlad Ki.

.. _ssec-relnotes-1.5.1:

Release 1.5.1 (Jul 5, 2017)
---------------------------

-  General

   -  This release has various minor bug and documentation fixes.

-  Backend: None

   -  #661: Added ``deployment.keys.*.keyFile`` option to provide keys
      from local files, rather than from text literals.

   -  #664: Added ``deployment.keys.*.destDir`` and
      ``deployment.keys.*.path`` options to give more control over where
      the deployment keys are stored on the deployed machine.

-  Backend: Datadog

   -  Show URL for dashboards and timeboards in info output.

-  Backend: Hetzner

   -  Added option to disable creation of sub-accounts.

-  Backend: Google Compute

   -  Added option to set service account for an instance.

   -  Added option to use preemptible option when creating an instance.

-  Backend: Digital Ocean

   -  Added option to support IPv6 on Digital Ocean.

This release has contributions from Albert Peschar, Amine Chikhaoui,
aszlig, Clemens Fruhwirth, Domen Kožar, Drew Hess, Eelco Dolstra, Igor
Pashev, Johannes Bornhold, Kosyrev Serge, Leon Isenberg, Maarten
Hoogendoorn, Nadrieril Feneanar, Niklas Hambüchen, Philip Patsch, Rob
Vermaas, Sven Slootweg.

.. _ssec-relnotes-1.5:

Release 1.5 (Feb 16, 2017)
--------------------------

-  General

   -  Various minor documentation and bug fixes

   -  #508: Implementation of SSH tunnels has been rewritten to use
      iproute instead of netttools

   -  #400: The ownership of keys is now implemented after user/group
      creation

   -  #216: Added ``--keep-days`` option for cleaning up backups

   -  #594: NixOps statefile is now created with stricter permissions

   -  Use ``types.submodule`` instead of deprecated ``types.optionSet``

   -  #566: Support setting ``deployment.hasFastConnection``

   -  Support for ``nixops deploy --evaluate-only``

-  Backend: None

   -  Create ``/etc/hosts``

-  Backend: Amazon Web Services

   -  Support for Elastic File Systems

   -  Support latest EBS volume types

   -  Support for Simple Notification Service

   -  Support for Cloudwatch Logs resources

   -  Support loading credentials from ``~/.aws/credentials`` (AWS default)

   -  Use HVM as default virtualization type (all new instance types are
      HVM)

   -  #550: Fix sporadic error "Error binding parameter 0 - probably
      unsupported type"

-  Backend: Datadog

   -  Support provisioning Datadog Monitors

   -  Support provisioning Datadog Dashboards

-  Backend: Hetzner

   -  #564: Binary cache substitutions didn't work because of
      certificate errors

-  Backend: VirtualBox

   -  Support dots in machine names

   -  Added ``vcpu`` option

-  Backend: Libvirtd

   -  Documentation typo fixes

-  Backend: Digital Ocean

   -  Initial support for Digital Ocean to deploy machines

This release has contributions from Amine Chikhaoui, Anders Papitto,
aszlig, Aycan iRiCAN, Christian Kauhaus, Corbin Simpson, Domen Kožar,
Eelco Dolstra, Evgeny Egorochkin, Igor Pashev, Maarten Hoogendoorn,
Nathan Zadoks, Pascal Wittmann, Renzo Carbonaram, Rob Vermaas, Ruslan
Babayev, Susan Potter and Danylo Hlynskyi.

.. _ssec-relnotes-1.4:

Release 1.4 (Jul 11, 2016)
--------------------------

-  General

   -  Added ``show-arguments`` command to query nixops arguments that are
      defined in the nix expressions

   -  Added ``--dry-activate`` option to the deploy command, to see what
      services will be stopped/started/restarted.

   -  Added ``--fallback`` option to the deploy command to match the same
      flag on nix-build.

   -  Added ``--cores`` option to the deploy command to match the same
      flag on nix-build.

-  Backend: None

-  Amazon EC2

   -  Use hvm-s3 AMIs when appropriate

   -  Allow EBS optimized flag to be changed (needs ``--allow-reboot``)

   -  Allow to recover from spot instance kill, when using external
      volume defined as resource (``resources.ebsVolumes``)

   -  When disassociating an elastic IP, make sure to check the current
      instance is the one who is currently associated with it, in case
      someone else has 'stolen' the elastic IP

   -  Use generated list for ``deployment.ec2.physicalProperties``, based on
      Amazon Pricing listing

   -  EC2 AMI registry has been moved the the nixpkgs repository

   -  Allow a timeout on spot instance creation

   -  Allow updating security groups on running instances in a VPC

   -  Support x1 instances

-  Backend: Azure

   -  New Azure Cloud backend contributed by Evgeny Egorochkin

-  Backend: VirtualBox

   -  Respect ``deployment.virtualbox.disks.*.size`` for images with a
      baseImage

   -  Allow overriding the VirtualBox base image size for disk1

-  Libvirt

   -  Improve logging messages

   -  #345: Use ``qemu-system-x86_64`` instead of ``qemu-kvm`` for non-NixOS
      support

   -  add ``extraDomainXML`` NixOS option

   -  add ``extraDevicesXML`` NixOS option

   -  add ``vcpu`` NixOS option

This release has contributions from Amine Chikhaoui, aszlig, Cireo,
Domen Kožar, Eelco Dolstra, Eric Sagnes, Falco Peijnenburg, Graham
Christensen, Kevin Cox, Kirill Boltaev, Mathias Schreck, Michael Weiss,
Brian Zach Abe, Pablo Costa, Peter Hoeg, Renzo Carbonara, Rob Vermaas,
Ryan Artecona, Tobias Pflug, Tom Hunger, Vesa Kaihlavirta, Danylo
Hlynskyi.

.. _ssec-relnotes-1.3.1:

Release 1.3.1 (January 14, 2016)
--------------------------------

-  General

   -  #340: "too long for Unix domain socket" error

   -  #335: Use the correct port when setting up an SSH tunnel

   -  #336: Add support for non-machine IP resources in ``/etc/hosts``

   -  Fix determining ``system.stateVersion``

   -  ssh_util: Reconnect on dead SSH master socket

   -  #379: Remove reference to ``jobs`` attribute in NixOS

-  Backend: None

   -  Pass ``deployment.targetPort`` to ssh for none backend

   -  #361: don't use _ssh_private_key if its corresponding public key
      hasn't been deployed yet

-  Amazon EC2

   -  Allow specifying ``assumeRolePolicy`` for IAM roles

   -  Add ``vpcId`` option to EC2 security group resources

   -  Allow VPC security groups to refer to sec. group names (within the
      same sec. group) as well as group ids

   -  Prevent vpc calls to be made if only security group ids are being
      used (instead of names)

   -  Use correct credentials for VPC API calls

   -  Fix "creating EC2 instance (... region ‘None’)" when recreating
      missing instance

   -  Allow keeping volumes while destroying deployment

-  VirtualBox

   -  #359: Change ``sbin/mount.vboxsf`` to ``bin/mount.vboxsf``

-  Hetzner

   -  #349: Don't create ``/root/.ssh/authorized_keys``

   -  #348: Fixup and refactor Hetzner backend tests

   -  hetzner-bootstrap: Fix wrapping Nix inside chroot

   -  hetzner-bootstrap: Allow to easily enter chroot

-  Libvirt

   -  #374: Add headless mode

   -  #374: Use more reliable method to retrieve IP address

   -  #374: Nicer error message for missing images dir

   -  #374: Be able to specify xml for devices

This release has contributions from aszlig, Bas van Dijk, Domen Kožar,
Eelco Dolstra, Kevin Cox, Paul Liu, Robin Gloster, Rob Vermaas, Russell
O'Connor, Tristan Helmich and Yves Parès (Ywen)

.. _ssec-relnotes-1.3:

Release 1.3 (September 28, 2015)
--------------------------------

-  General

   -  NixOps now requires NixOS 14.12 and up.

   -  Machines in NixOps network now have access to the deployment name,
      uuid and its arguments, by means of the ``deployment.name``,
      ``deployment.uuid`` and ``deployment.arguments`` options.

   -  Support for ``<...>`` paths in network spec filenames, e.g. you can
      use: ``nixops create '<nixops/templates/container.nix>'``.

   -  Support ``username@machine`` for ``nixops scp``

-  Amazon EC2

   -  Support for the latest EC2 instance types, including t2 and c4
      instance.

   -  Support Amazon EBS SSD disks.

   -  Instances can be placed in an EC2 placement group. This allows
      instances to be grouped in a low-latency 10 Gbps network.

   -  Allow starting EC2 instances in a VPC subnet.

   -  More robust handling of spot instance creation.

   -  Support for setting bucket policies on S3 buckets created by
      NixOps.

   -  Route53 support now uses CNAME to public DNS hostname, in stead of
      A record to the public IP address.

   -  Support Amazon RDS instances.

-  Google Cloud

   -  New backend for Google Cloud Platform. It includes support for the
      following resources:

-  VirtualBox

   -  VirtualBox 5.0 is required for the VirtualBox backend.

-  NixOS container

   -  New backend for NixOS containers.

-  Libvirt

   -  New backend for libvirt using QEMU/KVM.

This release has contributions from Andreas Herrmann, Andrew Murray,
aszlig, Aycan iRiCAN, Bas van Dijk, Ben Moseley, Bjørn Forsman, Boris
Sukholitko, Bruce Adams, Chris Forno, Dan Steeves, David Guibert, Domen
Kožar, Eelco Dolstra, Evgeny Egorochkin, Leroy Hopson, Michael Alyn
Miller, Michael Fellinger, Ossi Herrala, Rene Donner, Rickard Nilsson,
Rob Vermaas, Russell O'Connor, Shea Levy, Tomasz Kontusz, Tom Hunger,
Trenton Strong, Trent Strong, Vladimir Kirillov, William Roe.

.. _ssec-relnotes-1.2:

Release 1.2 (April 30, 2014)
----------------------------

-  General

   -  NixOps now requires NixOS 13.10 and up.

   -  Add ``--all`` option to ``nixops destroy``,
      ``nixops delete`` and ``nixops ssh-for-each``.

   -  The ``-d`` option now matches based on prefix for convenience when
      the specified uuid/id is not found.

   -  Resources can now be accessed via direct reference, i.e. you can
      use ``securityGroups = [ resources.ec2SecurityGroups.foo ];`` in
      stead of
      ``securityGroups = [ resources.ec2SecurityGroups.foo.name ];``.

   -  Changed default value of ``deployment.storeKeysOnMachine`` to
      false, which is the more secure option. This can prevent
      unattended reboot from finishing, as keys will need to be pushed
      to the machine.

-  Amazon EC2

   -  Support provisioning of elastic IP addresses.

   -  Support provisioning of EC2 security groups.

   -  Support all HVM instance types.

   -  Support ``ap-southeast-1`` region.

   -  Better handling of errors in pushing Route53 records.

   -  Support using ARN's for applying instance profiles to EC2
      instances. This allows cross-account API access.

   -  Base HVM image was updated to allow using all emphemeral devices.

   -  Instance ID is now available in nix through the
      ``deployment.ec2.instanceId`` option, set by nixops.

   -  Support independent provisioning of EBS volumes. Previously, EBS
      volumes could only be created as part of an EC2 instance, meaning
      their lifetime was tied to the instance and they could not be
      managed separately. Now they can be provisioned independently,
      e.g.:

      ::

               resources.ebsVolumes.bigdata =
                 { name = "My Big Fat Data";
                   region = "eu-west-1";
                   zone = "eu-west-1a";
                   accessKeyId = "...";
                   size = 1000;
                 };


   -  To allow cross-account API access, the
      ``deployment.ec2.instanceProfile`` option can now be set to either a
      name (previous behaviour) or an Amazon Resource Names (ARN) of the
      instance profile you want to apply.

-  Hetzner

   -  Always hard reset on destroying machine.

   -  Support for Hetzner vServers.

   -  Disabled root password by default.

   -  Fix hard reset for rebooting to rescue mode.. This is particularly
      useful if you have a dead server and want to put it in rescue
      mode. Now it's possible to do that simply by running:

      ::

               nixops reboot --hard --rescue --include=deadmachine


-  VirtualBox

   -  Require VirtualBox >= 4.3.0.

   -  Support for shared folders in VirtualBox. You can mount host
      folder on the guest by setting the
      deployment.virtualbox.sharedFolders option.

   -  Allow destroy if the VM is gone already

This release has contributions from aszlig, Corey O'Connor, Domen Kožar,
Eelco Dolstra, Michael Stone, Oliver Charles, Rickard Nilsson, Rob
Vermaas, Shea Levy and Vladimir Kirillov.

.. _ssec-relnotes-1.1.1:

Release 1.1.1 (October 2, 2013)
-------------------------------

This a minor bugfix release.

-  Added a command-line option ``--include-keys`` to allow importing SSH
   public host keys, of the machines that will be imported, to the
   ``.ssh/known_hosts`` of the user.

-  Fixed a bug that prevented switching the
   ``deployment.storeKeysOnMachine`` option value.

-  On non-EC2 systems, NixOps will generate ECDSA SSH host key pairs
   instead of DSA from now on.

-  VirtualBox deployments use generated SSH host key pairs.

-  For all machines which nixops generates an SSH host key pair for, it
   will add the SSH public host key to the known_hosts configuration of
   all machines in the network.

-  For EC2 deployments, if the nixops expression specifies a set of
   security groups for a machine that is different from the security
   groups applied to the existing machine, it will produce a warning
   that the change cannot be made.

-  For EC2 deployments, disks that are not supposed to be attached to
   the machine are detached only after system activation has been
   completed. Previously this was done before, but that could lead to
   volumes not being able to detach without needing to stop the machine.

-  Added a command-line option ``--repair`` as a convient way to pass this
   option, which allows repairing of broken or changed paths in the nix
   store, to nix-build calls that nixops performs. Note that this option
   only works in nix setups that run without the nix daemon.

This release has contributions from aszlig, Ricardo Correia, Eelco
Dolstra, Rob Vermaas.

.. _ssec-relnotes-1.1:

Release 1.1 (September 9, 2013)
-------------------------------

-  Backend for `Hetzner <http://hetzner.de>`__, a German data center
   provider. More information and a demo video can be found
   `here <https://github.com/NixOS/nixops/pull/119>`__.

-  When using the ``deployment.keys.*`` options, the keys in ``/run/keys``
   are now created with mode 600.

-  Fixed bug where EBS snapshots name tag was overridden by the instance
   name tag.

-  The nixops executable now has the default OpenSSH from nixpkgs in its
   PATH now by default, to work around issues with left-over SSH master
   connections on older version of OpenSSH, such as the version that is
   installed by default on CentOS.

-  A new resource type has been introduced to generate sets of SSH
   public/private keys.

-  Support for spot instances in the EC2 backend. By specifying the
   ``deployment.ec2.spotInstancePrice`` option for a machine, you can
   set the spot instance price in cents. NixOps will wait 10 minutes for
   a spot instance to be fulfilled, if not, then it will error out for
   that machine.

.. _ssec-relnotes-1.0.1:

Release 1.0.1 (July 11, 2013)
-----------------------------

This is a minor bugfix release.

-  Reduce parallelism for running EC2 backups, to prevent hammering the
   AWS API in case of many disks.

-  Propagate the instance tags to the EBS volumes (except for Name tag,
   which is overridden with a detailed description of the volume and its
   use).

.. _ssec-relnotes-1.0:

Release 1.0 (June 18, 2013)
---------------------------

Initial release.
