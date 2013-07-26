# Configuration specific to the Hetzner backend.

{ config, pkgs, ... }:

with pkgs.lib;

{
  ###### interface

  options.deployment.hetzner = {
    mainIPv4 = mkOption {
      default = null;
      example = "78.46.1.93";
      type = types.nullOr types.string;
      description = ''
        Main IP address identifying the server.
      '';
    };

    robotUser = mkOption {
      default = "";
      type = types.nullOr types.string;
      description = ''
        Username of the Hetzner robot account.

        If left empty, the value of the environment variable
        <envar>HETZNER_ROBOT_USER</envar> is used instead.
      '';
    };

    robotPass = mkOption {
      default = "";
      type = types.nullOr types.string;
      description = ''
        Password of the Hetzner robot account.

        If left empty, the value of the environment variable
        <envar>HETZNER_ROBOT_PASS</envar> is used instead.
      '';
    };

    partitions = mkOption {
      default = ''
        clearpart --all --initlabel

        part swap --recommended --label=swap1 --ondisk=sda
        part swap --recommended --label=swap2 --ondisk=sdb

        part raid.1 --grow --ondisk=sda
        part raid.2 --grow --ondisk=sdb

        raid / --level=1 --device=md0 --fstype=ext4 --label=root raid.1 raid.2
      '';
      type = types.string;
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
    boot.loader.grub.timeout = 1;
    services.openssh.enable = true;

    # Blacklist nvidiafb by default as it causes issues with some GPUs.
    boot.blacklistedKernelModules = [ "nvidiafb" ];
  };
}
