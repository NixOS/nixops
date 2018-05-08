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
      type = types.nullOr types.lines;
      description = ''
        Specify layout of partitions and file systems using Anacondas Kickstart
        format. For possible options and commands, please have a look at:

        <link xlink:href="http://fedoraproject.org/wiki/Anaconda/Kickstart"/>

        If Kickstart is not sufficient for your partitioning needs,
        consider the <option>partitioningScript</option> option instead.

        The <option>partitions</option> and <option>partitioningScript</option>
        options are mutually exclusive.
      '';
    };

    partitioningScript = mkOption {
      type = types.nullOr types.lines;
      default = null;
      example = ''
        # Example custom partitioningScript
        # that creates an ext4 with external journal, across two RAID1s
        # (one on HDDs, one on SSDs).

        set -x
        set -euo pipefail

        # If the SSD doesn't support the RZAT (Return Zero After Trim) feature,
        # we can't do the `lazy_journal_init=1` journal creation speedup
        # below, so fail early in that case.
        # Note that as per
        #   https://github.com/torvalds/linux/blob/e64f638483a21105c7ce330d543fa1f1c35b5bc7/drivers/ata/libata-core.c#L4242-L4250
        # TRIM in general is optional and thus this would be unsafe,
        # but the kernel announces RZAT only for a whitelist of devices
        # that are known to execute TRIM when requested.
        #
        # Note that this is probably not needed when the ext4 journal is on top
        # of an mdadm RAID (because that one likely guarantees to read zeros from
        # freshly initialised RAID arrays, but I haven't checked that this really
        # works), but we keep it in here just in case it doesn't work or
        # somebody wants to run the journal NOT on top of a RAID.
        #
        # TODO Fall back to slow `lazy_journal_init=1` if RZAT isn't supported.
        if hdparm -I /dev/sda | grep -i 'Deterministic read ZEROs after TRIM'; then echo "RZAT supported, can use lazy_journal_init=1 safely"; else echo "RZAT not supported on /dev/sda, cannot use lazy_journal_init=1 safely, exiting" 1>&2; exit 1; fi
        if hdparm -I /dev/sdb | grep -i 'Deterministic read ZEROs after TRIM'; then echo "RZAT supported, can use lazy_journal_init=1 safely"; else echo "RZAT not supported on /dev/sdb, cannot use lazy_journal_init=1 safely, exiting" 1>&2; exit 1; fi

        # Stop RAID devices if running, otherwise we can't modify the disks below.
        test -b /dev/md0 && mdadm --stop /dev/md0
        test -b /dev/md1 && mdadm --stop /dev/md1

        # Zero out SSDs with TRIM command, so that `lazy_journal_init=1` can be safely used below.
        blkdiscard /dev/sda
        blkdiscard /dev/sdb

        # Create BIOS boot partition and main partition for each SSD and HDD.
        # Note Hetzner does use BIOS, not UEFI.
        # We use GPT because these disks could be too large for MSDOS partitions (e.g. 10TB disks).
        parted --script -a optimal /dev/sda -- mklabel gpt mkpart primary 1MiB 2MiB set 1 bios_grub on mkpart primary 2MiB '100%'
        parted --script -a optimal /dev/sdb -- mklabel gpt mkpart primary 1MiB 2MiB set 1 bios_grub on mkpart primary 2MiB '100%'
        parted --script -a optimal /dev/sdc -- mklabel gpt mkpart primary 1MiB 2MiB set 1 bios_grub on mkpart primary 2MiB '100%'
        parted --script -a optimal /dev/sdd -- mklabel gpt mkpart primary 1MiB 2MiB set 1 bios_grub on mkpart primary 2MiB '100%'

        # Now /dev/sd*1 is the BIOS boot partition, /dev/sd*2 is the one data partition

        # Reload partition table so Linux can see the changes
        partprobe

        # Wait for all devices to exist
        udevadm settle --timeout=5 --exit-if-exists=/dev/sda1
        udevadm settle --timeout=5 --exit-if-exists=/dev/sda2
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdb1
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdb2
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdc1
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdc2
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdd1
        udevadm settle --timeout=5 --exit-if-exists=/dev/sdd2

        # --run makes mdadm not prompt the user for confirmation
        mdadm --create --run --verbose /dev/md0 --level=1 --raid-devices=2 /dev/sda2 /dev/sdb2
        mdadm --create --run --verbose /dev/md1 --level=1 --raid-devices=2 /dev/sdc2 /dev/sdd2

        # Wipe filesystem signatures that might be on the RAID from some
        # possibly existing older use of the disks.
        # It's not clear to me *why* it is needed, but I have certainly
        # observed that it is needed because ext4 labels magically survive
        # mdadm RAID re-creations.
        # See
        #   https://serverfault.com/questions/911370/why-does-mdadm-zero-superblock-preserve-file-system-information
        wipefs -a /dev/md0
        wipefs -a /dev/md1

        # Disable RAID recovery. We don't want this to slow down machine provisioning
        # in the Hetzner rescue mode. It can run in normal operation after reboot.
        echo 0 > /proc/sys/dev/raid/speed_limit_max

        # `lazy_journal_init=1` to not have to zero the device;
        # we use ATA TRIM with RZAT support to guarantee the device
        # is already zeroed; see comment further up about the safety of that.
        mke2fs -F -L rootjournal -O journal_dev -E lazy_journal_init=1 /dev/md0
        mkfs.ext4 -F -L root -J device=/dev/md0 /dev/md1
      '';
      description = ''
        Script to run after booting into the Hetzner rescue mode
        to manually create partitions.

        Note as of writing, Hetzner uses BIOS, not UEFI, so if you want
        to use GPT partition tables (which you need in case you want to
        make partitions larger than 2 TiB) you will likely have to make
        a BIOS boot partition
        (<link xlink:href="http://fedoraproject.org/wiki/Anaconda/Kickstart"/>).

        Where possible, use the simpler <option>partitions</option> option instead of this option.

        The <option>partitions</option> and <option>partitioningScript</option>
        options are mutually exclusive.

        If you use this option, you must set "partitions = null",
        you must set "filesystemInfo" to an accurate representation
        of the partitions your script creates,
        and you must set "mountScript" to mount the created target
        root partition at /mnt.
      '';
    };

    mountScript = mkOption {
      type = types.nullOr types.lines;
      default = null;
      example = ''
        # Example mountScript matching the example for partitioningScript,
        # that creates an ext4 with external journal, across two RAID1s
        # (one on HDDs, one on SSDs).

        set -e
        mount -o data=journal /dev/md1 /mnt
      '';
      description = ''
        Script to run after booting into the Hetzner rescue mode,
        and after formatting, to mount the root filesystem at /mnt.

        This option is required when "partitioningScript" is used.
      '';
    };

    filesystemInfo = mkOption {
      type = types.nullOr types.attrs;
      default = null;
      example = literalExample ''
        {
          # Example filesystemInfo matching the example for partitioningScript,
          # that creates an ext4 with external journal, across two RAID1s
          # (one on HDDs, one on SSDs).
          swapDevices = [];
          boot.loader.grub.devices = [
            "/dev/sda"
            "/dev/sdb"
            "/dev/sdc"
            "/dev/sdd"
          ];
          fileSystems = {
            "/" = {
              fsType = "ext4";
              label = "root";
              options = [
                "journal_path=/dev/disk/by-label/rootjournal"
                "data=journal"
                "errors=remount-ro"
              ];
            };
          };
        }
      '';
      description = ''
        Override the filesystem info obtained from the machine after partitioning.

        This option is required when "partitioningScript" is used, but can also
        be set if the filesystem info obtained via <option>partitions</option> is not what you need.
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
