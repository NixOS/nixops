# Configuration specific to the Google Compute Engine backend.

{ config, pkgs, name, uuid, ... }:

with pkgs.lib;

let

  gce_dev_prefix = "/dev/disk/by-id/scsi-0Google_PersistentDisk_";

  get_disk_name = cfg:
    if cfg.disk != null
      then cfg.disk.name or cfg.disk
      else "${config.deployment.gce.machineName}-${cfg.disk_name}";

  resource = type: mkOptionType {
    name = "resource of type ‘${type}’";
    check = x: x._type or "" == type;
    merge = mergeOneOption;
  };

  # FIXME: move to nixpkgs/lib/types.nix.
  union = t1: t2: mkOptionType {
    name = "${t1.name} or ${t2.name}";
    check = x: t1.check x || t2.check x;
    merge = mergeOneOption;
  };

  gceDiskOptions = { config, ... }: {

    options = {

      disk_name = mkOption {
        default = null;
        example = "machine-persistent-disk2";
        type = types.nullOr types.str;
        description = ''
          Name of the GCE disk to create.
        '';
      };

      disk = mkOption {
        default = null;
        example = "resources.gceDisks.exampleDisk";
        type = types.nullOr ( union types.str (resource "gce-disk") );
        description = ''
          GCE Disk resource or name of a disk not managed by NixOps to be mounted.
        '';
      };

      snapshot = mkOption {
        default = null;
        example = "snapshot-432";
        type = types.nullOr types.str;
        description = ''
          The snapshot name from which to create the GCE disk. If
          not specified, an empty disk is created.  Changing the
          snapshot name has no effect if the disk already exists.
        '';
      };

      image = mkOption {
        default = null;
        example = "image-432";
        type = types.nullOr types.str;
        description = ''
          The image name from which to create the GCE disk. If
          not specified, an empty disk is created.  Changing the
          image name has no effect if the disk already exists.
        '';
      };

      size = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          Volume size (in gigabytes) for automatically created
          GCE disks. This may be left unset if you are
          creating the disk from a snapshot or image, in which case the
          size of the disk will be equal to the size of the snapshot or image.
          You can set a size larger than the snapshot or image,
          allowing the disk to be larger than the snapshot from which it is
          created.
        '';
      };

      readOnly = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Should the disk be attached to the instance as read-only.
        '';
      };

      bootDisk = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Should the instance boot from this disk.
        '';
      };

      deleteOnTermination = mkOption {
        type = types.bool;
        description = ''
          For automatically created GCE disks, determines whether the
          disk should be deleted on instance destruction.
        '';
      };

      # FIXME: remove the LUKS options eventually?

      encrypt = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Whether the GCE disk should be encrypted using LUKS.
        '';
      };

      cipher = mkOption {
        default = "aes-cbc-essiv:sha256";
        type = types.str;
        description = ''
          The cipher used to encrypt the disk.
        '';
      };

      keySize = mkOption {
        default = 128;
        type = types.int;
        description = ''
          The size of the encryption key.
        '';
      };

      passphrase = mkOption {
        default = "";
        type = types.str;
        description = ''
          The passphrase (key file) used to decrypt the key to access
          the device.  If left empty, a passphrase is generated
          automatically; this passphrase is lost when you destroy the
          machine or remove the volume, unless you copy it from
          NixOps's state file.  Note that the passphrase is stored in
          the Nix store of the instance, so an attacker who gains
          access to the GCE disk or instance store that contains the
          Nix store can subsequently decrypt the encrypted volume.
        '';
      };

    };

    config =
      (mkAssert ( (config.snapshot == null) || (config.image == null) )
                "Disk can not be created from both a snapshot and an image at once"
      (mkAssert ( (config.disk != null) || (config.disk_name != null) )
                "Specify either an external disk name to mount or a disk name to create"
      (mkAssert ( (config.size != null) || (config.snapshot != null)
               || (config.image != null) || (config.disk != null) )
                "Disk size is required unless it is created from an image or snapshot" {
          # Automatically delete volumes that are automatically created.
          deleteOnTermination = mkDefault ( config.disk == null );
        }
      )));

  };

in
{
  ###### interface

  options = {

    deployment.gce = {

      machineName = mkOption {
        default = "nixops-${uuid}-${name}";
        example = "custom-machine-name";
        type = types.str;
        description = "The GCE Instance <literal>Name</literal>.";
      };

      serviceAccount = mkOption {
        default = "";
        example = "12345-asdf@developer.gserviceaccount.com";
        type = types.str;
        description = ''
          The GCE Service Account Email. If left empty, it defaults to the
          contents of the environment variable <envar>GCE_SERVICE_ACCOUNT</envar>.
        '';
      };

      accessKey = mkOption {
        default = "";
        example = "/path/to/secret/key.pem";
        type = types.str;
        description = ''
          The path to GCE Service Account key. If left empty, it defaults to the
          contents of the environment variable <envar>ACCESS_KEY_PATH</envar>.
        '';
      };

      project = mkOption {
        default = "";
        example = "myproject";
        type = types.str;
        description = ''
          The GCE project which should own the instance. If left empty, it defaults to the
          contents of the environment variable <envar>GCE_PROJECT</envar>.
        '';
      };

      region = mkOption {
        example = "europe-west1-b";
        type = types.str;
        description = ''
          The GCE datacenter in which the instance should be created.
        '';
      };

      instanceType = mkOption {
        default = "g1-small";
        example = "n1-standard-1";
        type = types.str;
        description = ''
          GCE instance type. See <link
          xlink:href='https://developers.google.com/compute/pricing'/> for a
          list of valid instance types.
        '';
      };

      tags = mkOption {
        default = [ ];
        example = [ "random" "tags" ];
        type = types.listOf types.str;
        description = ''
          Tags to assign to the instance. These can be used in firewall and
          networking rules and are additionally available as metadata.
        '';
      };

      metadata = mkOption {
        default = {};
        example = { loglevel = "warn"; };
        type = types.attrsOf types.str;
        description = ''
          Metadata to assign to the instance. These are available to the instance
          via the metadata server. Some metadata keys such as "startup-script"
          are reserved by GCE and can influence the instance.
        '';
      };

      ipAddress = mkOption {
        default = null;
        example = "resources.gceStaticIPs.exampleIP";
        type = types.nullOr ( union types.str (resource "gce-static-ip") );
        description = ''
          GCE Static IP address resource to bind to or the name of
          an IP address not managed by NixOps.
        '';
      };

      network = mkOption {
        default = null;
        example = "resources.gceNetworks.verySecureNetwork";
        type = types.nullOr ( union types.str (resource "gce-network") );
        description = ''
          The GCE Network to make the instance a part of. Can be either
          a gceNetworks resource or a name of a network not managed by NixOps.
        '';
      };

      blockDeviceMapping = mkOption {
        default = { };
        example = { "/dev/sda".image = "bootstrap-img"; "/dev/sdb".disk = "vol-d04895b8"; };
        type = types.attrsOf types.optionSet;
        options = gceDiskOptions;
        description = ''
          Block device mapping.
        '';
      };

      bootstrapImage = mkOption {
        default = "nixos-14-04pre-d215564-x86-64-linux";
        type = types.str;
        description = ''
          Bootstrap image name to use to create the root disk of the instance.
        '';
      };

      rootDiskSize = mkOption {
        default = null;
        example = 200;
        type = types.nullOr types.int;
        description = ''
          Root disk size(in gigabytes). Leave unset to be
          the same as <option>bootstrapImage</option> size.
        '';
      };


      scheduling.automaticRestart = mkOption {
        default = null;
        type = types.nullOr types.bool;
        description = ''
          Whether the Instance should be automatically restarted when it is
          terminated by Google Compute Engine (not terminated by user).
          Set to null to let GCE pick the default value.
        '';
      };

      scheduling.onHostMaintenance = mkOption {
        default = null;
        type = types.nullOr (types.addCheck types.str
            (v: elem v [ "MIGRATE" "TERMINATE" ]) );
        description = ''
          Defines the maintenance behavior for this instance. For more information, see <link
          xlink:href='https://developers.google.com/compute/docs/instances#onhostmaintenance'/>.

          Allowed values are: "MIGRATE" to let GCE automatically migrate your
          instances out of the way of maintenance events and
          "TERMINATE" to allow GCE to terminate and restart the instance.

          Set to null to let GCE pick the default.
        '';
      };

    };

    fileSystems = mkOption {
      options = { config, ... }: {
        options = {
          gce = mkOption {
            default = null;
            type = types.uniq (types.nullOr types.optionSet);
            options = gceDiskOptions;
            description = ''
              GCE disk to be attached to this mount point.  This is
              shorthand for defining a separate
              <option>deployment.gce.blockDeviceMapping</option>
              attribute.
            '';
          };
        };
        config = mkIf(config.gce != null) {
          device = mkDefault "${
              if config.gce.encrypt then "/dev/mapper/" else gce_dev_prefix
            }${
              get_disk_name config.gce
          }";
        };
      };
    };

  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "gce") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";

    fileSystems."/".label = "nixos";

    deployment.gce.blockDeviceMapping =  {
      "${gce_dev_prefix}${config.deployment.gce.machineName}-root" = {
          image = config.deployment.gce.bootstrapImage;
          size = config.deployment.gce.rootDiskSize;
          bootDisk = true;
          disk_name = "root";
      };
    } // (listToAttrs
      (map (fs: nameValuePair "${gce_dev_prefix}${get_disk_name fs.gce}"
        { inherit (fs.gce) disk disk_name size snapshot image
                           readOnly bootDisk deleteOnTermination encrypt cipher keySize passphrase;
        })
       (filter (fs: fs.gce != null) (attrValues config.fileSystems))));

    deployment.autoLuks =
      let
        f = name: dev: nameValuePair (get_disk_name dev)
          { device = name;
            autoFormat = true;
            inherit (dev) cipher keySize passphrase;
          };
      in mapAttrs' f (filterAttrs (name: dev: dev.encrypt) config.deployment.gce.blockDeviceMapping);

    boot.kernelParams = [ "console=ttyS0" "panic=1" "boot.panic_on_fail" ];
    boot.initrd.kernelModules = [ "virtio_scsi" "virtio_balloon" "virtio_console" "virtio_rng" ];
    boot.initrd.availableKernelModules = [ "virtio_net" "virtio_pci" "virtio_blk" "9p" "9pnet_virtio" ];

    # Generate a GRUB menu
    boot.loader.grub.device = "/dev/sda";
    boot.loader.grub.timeout = 0;

    # Don't put old configurations in the GRUB menu.  The user has no
    # way to select them anyway.
    boot.loader.grub.configurationLimit = 0;

    # Allow root logins only using the SSH key that the user specified
    # at instance creation time.
    services.openssh.enable = true;
    services.openssh.permitRootLogin = "without-password";

    # Force getting the hostname from Google Compute.
    networking.hostName = mkDefault "";

    # Always include cryptsetup so that NixOps can use it.
    environment.systemPackages = [ pkgs.cryptsetup ];

    # Configure default metadata hostnames
    networking.extraHosts = ''
      169.254.169.254 metadata.google.internal metadata
    '';

    sound.enable = false;
    boot.vesa = false;

    # Don't start a tty on the serial consoles.
    systemd.services."serial-getty@ttyS0".enable = false;
    systemd.services."serial-getty@hvc0".enable = false;
    systemd.services."getty@tty1".enable = false;
    systemd.services."autovt@".enable = false;

    # Don't allow emergency mode, because we don't have a console.
    systemd.enableEmergencyMode = false;

    boot.initrd.postDeviceCommands =
      ''
        # Set the system time from the hardware clock to work around a
        # bug in qemu-kvm > 1.5.2 (where the VM clock is initialised
        # to the *boot time* of the host).
        hwclock -s
      '';
  };
}
