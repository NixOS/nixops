# Configuration specific to the Google Compute Engine backend.

{ config, lib, pkgs, name, uuid, resources, ... }:

with lib;
with import ./lib.nix lib;

let

  gce_dev_prefix = "/dev/disk/by-id/scsi-0Google_PersistentDisk_";

  get_disk_name = cfg:
    if cfg.disk != null
      then cfg.disk.name or cfg.disk
      else "${config.deployment.gce.machineName}-${cfg.disk_name}";

  mkDefaultDiskName = mountPoint: cfg: cfg // {
    disk_name = if (cfg.disk_name == null) && (cfg.disk == null)
                  then replaceChars ["/" "." "_"] ["-" "-" "-"]
                    (substring 1 ((stringLength mountPoint) - 1) mountPoint)
                  else cfg.disk_name;
  };

  addr_manager = pkgs.stdenv.mkDerivation {
    name = "google-address-manager";
    src = pkgs.fetchFromGitHub {
      owner = "GoogleCloudPlatform";
      repo = "compute-image-packages";
      rev = "6cb6f9d2219dca1d14aeb60177a15492814032a3";
      sha256 = "10qgdd2sahvb3pwajbrw2zi8ad2xqgpi782lzzkp6yzvwyiybn18";
    };
    preConfigure = ''
      substituteInPlace google-daemon/usr/share/google/google_daemon/address_manager.py --replace /sbin/ip ${pkgs.iproute}/sbin/ip
      substituteInPlace google-daemon/usr/share/google/google_daemon/manage_addresses.py --replace /usr/bin/python ${pkgs.python2}/bin/python2
    '';
    installPhase = ''
      mkdir -p $out/share/google_daemon
      cp google-daemon/usr/share/google/google_daemon/address_manager.py $out/share/google_daemon
      cp google-daemon/usr/share/google/google_daemon/manage_addresses.py $out/share/google_daemon
      cp google-daemon/usr/share/google/google_daemon/utils.py $out/share/google_daemon
    '';
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
        type = types.nullOr ( types.either types.str (resource "gce-disk") );
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
        type = types.nullOr ( types.either types.str (resource "gce-image") );
        description = ''
          The image name or resource from which to create the GCE disk. If
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

      diskType = mkOption {
        default = "standard";
        type = types.addCheck types.str
                (v: elem v [ "standard" "ssd" ]);
        description = ''
          The disk storage type (standard/ssd).
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
      (mkAssert ( (config.size != null) || (config.snapshot != null)
               || (config.image != null) || (config.disk != null) )
                "Disk size is required unless it is created from an image or snapshot" {
          # Automatically delete volumes that are automatically created.
          deleteOnTermination = mkDefault ( config.disk == null );
        }
      ));

  };

  fileSystemsOptions = { config, ... }: {
    options = {
      gce = mkOption {
        default = null;
        type = with types; uniq (nullOr (submodule gceDiskOptions));
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
          get_disk_name (mkDefaultDiskName config.mountPoint config.gce)
      }";
    };
  };

in
{
  ###### interface

  options = {

    deployment.gce = (import ./gce-credentials.nix lib "instance") // {

      machineName = mkOption {
        default = "n-${shorten_uuid uuid}-${name}";
        example = "custom-machine-name";
        type = types.str;
        description = "The GCE Instance <literal>Name</literal>.";
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

      labels = (import ./common-gce-options.nix { inherit lib; }).labels;

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
        type = types.nullOr ( types.either types.str (resource "gce-static-ip") );
        description = ''
          GCE Static IP address resource to bind to or the name of
          an IP address not managed by NixOps.
        '';
      };

      network = mkOption {
        default = null;
        example = "resources.gceNetworks.verySecureNetwork";
        type = types.nullOr ( types.either types.str (resource "gce-network") );
        description = ''
          The GCE Network to make the instance a part of. Can be either
          a gceNetworks resource or a name of a network not managed by NixOps.
        '';
      };

      subnet = mkOption {
        default = null;
        type = with types; nullOr str;
        description =  ''
          Specifies the subnet that the instances will be part of.
        '';
      };

      canIpForward = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Allows the instance to send and receive packets with non-matching destination or source IPs.
        '';
      };

      instanceServiceAccount = mkOption {
        default  = {};
        type = (types.submodule {
          options = {
            email = mkOption {
              default = "default";
              type = types.str;
              description = ''
                Email address of the service account.
                If not given, Google Compute Engine default service account is used.
              '';
            };
            scopes = mkOption {
              default = [];
              type = types.listOf types.str;
              description = ''
                The list of scopes to be made available for this service account.
              '';
            };
          };
        });
        description = ''
          A service account with its specified scopes, authorized for this instance.
        '';
      };

      blockDeviceMapping = mkOption {
        default = { };
        example = { "/dev/sda".image = "bootstrap-img"; "/dev/sdb".disk = "vol-d04895b8"; };
        type = with types; attrsOf (submodule gceDiskOptions);
        description = ''
          Block device mapping.
        '';
      };

      bootstrapImage = mkOption {
        default = resources.gceImages.bootstrap;
        type = types.either types.str (resource "gce-image");
        description = ''
          Bootstrap image name or resource to use to create the root disk of the instance.
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

      rootDiskType = mkOption {
        default = "standard";
        type = types.addCheck types.str
                (v: elem v [ "standard" "ssd" ]);
        description = ''
          The root disk storage type (standard/ssd).
        '';
      };

      scheduling.automaticRestart = mkOption {
        default = true;
        type = types.bool;
        description = ''
          Whether the Instance should be automatically restarted when it is
          terminated by Google Compute Engine (not terminated by user).
        '';
      };

      scheduling.onHostMaintenance = mkOption {
        default = "MIGRATE";
        type = types.addCheck types.str
            (v: elem v [ "MIGRATE" "TERMINATE" ]);
        description = ''
          Defines the maintenance behavior for this instance. For more information, see <link
          xlink:href='https://developers.google.com/compute/docs/instances#onhostmaintenance'/>.

          Allowed values are: "MIGRATE" to let GCE automatically migrate your
          instances out of the way of maintenance events and
          "TERMINATE" to allow GCE to terminate and restart the instance.
        '';
      };

      scheduling.preemptible = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Whether the instance is preemptible.
          For more information, see <link
          xlink:href='https://developers.google.com/compute/docs/instances#onhostmaintenance'/>.
        '';
      };

    };

    fileSystems = mkOption {
      type = with types; loaOf (submodule fileSystemsOptions);
    };

  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "gce") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";

    deployment.gce.blockDeviceMapping =  {
      "${gce_dev_prefix}${config.deployment.gce.machineName}-root" = {
          image = config.deployment.gce.bootstrapImage;
          size = config.deployment.gce.rootDiskSize;
          diskType = config.deployment.gce.rootDiskType;
          bootDisk = true;
          disk_name = "root";
      };
    } // (listToAttrs
      (map (fs: let fsgce = mkDefaultDiskName fs.mountPoint fs.gce; in
                nameValuePair "${gce_dev_prefix}${get_disk_name fsgce}" fsgce
        )
       (filter (fs: fs.gce != null) (attrValues config.fileSystems))));

    deployment.autoLuks =
      let
        f = name: dev: nameValuePair (get_disk_name dev)
          { device = name;
            autoFormat = true;
            inherit (dev) cipher keySize passphrase;
          };
      in mapAttrs' f (filterAttrs (name: dev: dev.encrypt) config.deployment.gce.blockDeviceMapping);

    systemd.services.configure-forwarding-rules =
      { description = "Add extra IPs required for forwarding rules to work";

        wantedBy = [ "multi-user.target" ];
        before = [ "sshd.service" ];
        after = [ "network.target" ];

        serviceConfig.ExecStart = "${addr_manager}/share/google_daemon/manage_addresses.py";
      };

  };
}
