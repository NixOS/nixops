Introduction
------------

NixOps is a tool for deploying NixOS machines in a network or cloud.
It takes as input a declarative specification of a set of “logical”
machines and then performs any necessary steps or actions to realise
that specification: instantiate cloud machines, build and download
dependencies, stop and start services, and so on. NixOps has several
nice properties:

- It’s *declarative*: NixOps specifications state the desired
  configuration of the machines, and NixOps then figures out the
  actions necessary to realise that configuration. So there is no
  difference between doing a new deployment or doing a redeployment:
  the resulting machine configurations will be the same.

- It performs *fully automated* deployment. This is a good thing
  because it ensures that deployments are reproducible.

- It performs provisioning. Based on the given deployment
  specification, it will start missing virtual machines, create disk
  volumes, and so on.

- It’s based on the `Nix package manager <http://nixos.org/nix/>`_,
  which has a *purely functional* model that sets it apart from other
  package managers. Concretely this means that multiple versions of
  packages can coexist on a system, that packages can be upgraded or
  rolled back atomically, that dependency specifications can be
  guaranteed to be complete, and so on.

- It’s based on `NixOS <http://nixos.org/nixos/>`_, which has a
  declarative approach to describing the desired configuration of a
  machine. This makes it an ideal basis for automated configuration
  management of sets of machines. NixOS also has desirable properties
  such as (nearly) atomic upgrades, the ability to roll back to
  previous configurations, and more.

- It’s *multi-cloud*. Machines in a single NixOps deployment can be
  deployed to different target environments. For instance, one
  logical machine can be deployed to a local “physical” machine,
  another to an automatically instantiated Amazon EC2 instance in the
  ``eu-west-1`` region, another in the ``us-east-1`` region, and so
  on.

- It supports *separation of “logical” and “physical” aspects* of a
  deployment. NixOps specifications are modular, and this makes it
  easy to separate the parts that say *what* logical machines should
  do from *where* they should do it. For instance, the former might
  say that machine X should run a PostgreSQL database and machine Y
  should run an Apache web server, while the latter might state that X
  should be instantiated as an EC2 ``m1.large`` machine while Y should
  be instantiated as an ``m1.small``. We could also have a second
  physical specification that says that X and Y should both be
  instantiated as VirtualBox VMs on the developer’s workstation. So
  the same logical specification can easily be deployed to different
  environments.

- It uses a single formalism (the Nix expression language) for package
  management and system configuration management. This makes it very
  easy to add ad hoc packages to a deployment.

- It combines system configuration management and provisioning.
  Provisioning affects configuration management: for instance, if we
  instantiate an EC2 machine as part of a larger deployment, it may be
  necessary to put the IP address or hostname of that machine in a
  configuration file on another machine. NixOps takes care of this
  automatically.

- It can provision non-machine cloud resources such as Amazon S3
  buckets and EC2 key pairs.
