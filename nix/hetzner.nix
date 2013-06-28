# Configuration specific to the Hetzner backend.

{ config, pkgs, utils, ... }:

with pkgs.lib;
with utils;

let

  cfg = config.deployment.hetzner;

  partitionOptions = {
    label = mkOption {
      example = "nixos";
      type = types.nullOr types.string;
      description = ''
        The label to create for this partition. If multiple devices are used and
        no <literal>raidLevel</literal> is set, each of the labels gets a
        numbered suffix such as <literal>-1</literal> or <literal>-2</literal>.
      '';
    };

    devices = mkOption {
      default = [ "/dev/sda" "/dev/sdb" ];
      type = types.list types.string;
      description = ''
        This are the devices where the partition is to be created. Please note,
        that these are <emphasis>not</emphasis> partitions such as
        <literal>/dev/sda1</literal> but the devices of the disks themselves!
      '';
    };

    mountPoint = mkOption {
      example = "/boot";
      type = types.nullOr types.string;
      description = ''
        The path where the filesystem is to be mounted in the installed system.

        Use <literal>null</literal> for swap partations.

        This will also be used to autogenerate a default
        <option>fileSystems</option> attribute set.

        In case you use multiple devices without RAID, only the
        <emphasis>first</emphasis> device is mounted. Useful for example with
        btrfs.
      '';
    };

    raidLevel = mkOption {
      default = 1;
      example = null;
      type = types.nullOr types.int;
      description = ''
        The RAID level to use for mdraid. Use <literal>null</literal> to disable
        RAID for the partition.
      '';
    };

    fsType = mkOption {
      example = "ext4";
      type = types.nullOr types.string;
      description = ''
        The filesystem to create for this partition. Use <literal>null</literal>
        to not create any filesystem at all. You can use
        <option>fileSystems.*.autoformat</option> to do that later when the
        system is running.
      '';
    };

    size = mkOption {
      default = "rest";
      example = "50G";
      type = types.string;
      description = ''
        The size of the partition in bytes (if no multiplier is specified).
        If you specify <literal>"rest"</literal> here, the partition will use
        all of the remaining space on the disk.

        <variablelist><title>Supported multipliers</title>
          <varlistentry>
            <term><literal>K</literal></term>
            <listitem><para>Kilobytes</para></listitem>
          </varlistentry>
          <varlistentry>
            <term><literal>M</literal></term>
            <listitem><para>Megabytes</para></listitem>
          </varlistentry>
          <varlistentry>
            <term><literal>G</literal></term>
            <listitem><para>Gigabytes</para></listitem>
          </varlistentry>
          <varlistentry>
            <term><literal>T</literal></term>
            <listitem><para>Terabytes</para></listitem>
          </varlistentry>
          <varlistentry>
            <term><literal>P</literal></term>
            <listitem><para>Petabytes</para></listitem>
          </varlistentry>
          <varlistentry>
            <term><literal>%</literal></term>
            <listitem><para>Percentage</para></listitem>
          </varlistentry>
        </variablelist>
      '';
    };
  };

in

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
      default = null;
      type = types.nullOr types.string;
      description = ''
        Username of the Hetzner robot account.
      '';
    };

    robotPass = mkOption {
      default = null;
      type = types.nullOr types.string;
      description = ''
        Password of the Hetzner robot account.
      '';
    };

    partitions = mkOption {
      default = [
        { label = "swap";
          fsType = "swap";
          raidLevel = null;
          mountPoint = null;
          size = "4G";
        }
        { label = "root";
          fsType = "ext4";
          mountPoint = "/";
        }
      ];
      example = [
        { label = "boot";
          fsType = "ext3";
          mountPoint = "/boot";
          size = "500M";
        }
        { label = "swap";
          fsType = "swap";
          raidLevel = null;
          mountPoint = null;
          size = "4G";
        }
        { label = "root";
          fsType = "xfs";
          mountPoint = "/";
        }
      ];
      type = types.list types.optionSet;
      options = partitionOptions;
      description = ''
        Provide the layout of the partition table and the to be created file
        systems.
      '';
    };
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "hetzner") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";
  };
}
