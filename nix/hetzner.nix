# Configuration specific to the Hetzner backend.

{ config, lib, ... }:

with lib;

{
  ###### interface

  options.deployment.hetzner = {
    mainIPv4 = mkOption {
      default = null;
      example = "78.46.1.93";
      type = types.nullOr types.str;
      description = ''
        Main IP address identifying the server.
      '';
    };

    createSubAccount = mkOption {
      default = true;
      type = types.bool;
      description = ''
        Whether NixOps should create a Hetzner "Admin account"
        (a sub-account that allows to manage this single machine).

        You must disable this when your Hetzner main account
        is protected with 2-factor authentication, as the
        Hetzner webservice API does not support 2-factor auth.

        When this is disabled, you must manually create the
        sub-account for each machine in the Hetzner
        Robot UI before running NixOps.

        When this is disabled, NixOps assumes that the credentials
        for the sub-account are those given with the `robotUser`
        and `robotPass` options.
        If those are left empty, the values of the environment
        variables <envar>HETZNER_ROBOT_USER</envar> and
        <envar>HETZNER_ROBOT_PASS</envar> are used instead.

        Note that if you have more than one Hetzner
        and `createSubAccount = false`, it does not make sense
        to use <envar>HETZNER_ROBOT_USER</envar> because Hetzner
        (as of writing) enforces a different sub-account user name
        for each server, so you should use `robotUser` per machine
        instead of using the environment variable.
        But you may use the environment variable for the password
        if you set the sub-account passwords to be identical.
      '';
    };

    robotUser = mkOption {
      default = "";
      type = types.nullOr types.str;
      description = ''
        Username of the Hetzner robot account.

        If left empty, the value of the environment variable
        <envar>HETZNER_ROBOT_USER</envar> is used instead.
      '';
    };

    robotPass = mkOption {
      default = "";
      type = types.nullOr types.str;
      description = ''
        Password of the Hetzner robot account.

        If left empty, the value of the environment variable
        <envar>HETZNER_ROBOT_PASS</envar> is used instead.
      '';
    };

    partitions = mkOption {
      default = ''
        clearpart --all --initlabel --drives=sda,sdb

        part swap1 --recommended --label=swap1 --fstype=swap --ondisk=sda
        part swap2 --recommended --label=swap2 --fstype=swap --ondisk=sdb

        part raid.1 --grow --ondisk=sda
        part raid.2 --grow --ondisk=sdb

        raid / --level=1 --device=md0 --fstype=ext4 --label=root raid.1 raid.2
      '';
      example = ''
        # Example for partitioning on a vServer:
        clearpart --all --initlabel --drives=vda
        part swap --recommended --label=swap --fstype=swap --ondisk=vda
        part / --fstype=ext4 --label=root --grow --ondisk=vda
      '';
      type = types.lines;
      description = ''
        Specify layout of partitions and file systems using Anacondas Kickstart
        format. For possible options and commands, please have a look at:

        <link xlink:href="http://fedoraproject.org/wiki/Anaconda/Kickstart"/>
      '';
    };
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "hetzner") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
    boot.loader.grub.version = 2;
    boot.loader.timeout = 1;
    services.openssh.enable = true;

    # Blacklist nvidiafb by default as it causes issues with some GPUs.
    boot.blacklistedKernelModules = [ "nvidiafb" ];

    security.initialRootPassword = mkDefault "!";
  };
}
