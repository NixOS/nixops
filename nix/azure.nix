# Configuration specific to the Azure backend.

{ config, pkgs, name, uuid, resources, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
let

  luksName = def:
    if (def.ephemeralName == null) || (def.ephemeralName == "")
    then (def.diskResource.name or def.diskResource)
    else def.ephemeralName;

  mkDefaultEphemeralName = mountPoint: cfg:
    let
      cfg' = cfg // (
        if (cfg.diskResource == null) && (cfg.ephemeralName == null)
        then {
          ephemeralName = replaceChars ["/" "." "_"] ["-" "-" "-"]
                            (substring 1 ((stringLength mountPoint) - 1) mountPoint); }
        else {});
    in cfg' // (
      if (cfg'.label == null) || (cfg'.label == "")
      then { label = cfg'.ephemeralName; }
      else {}
    );

  endpointOptions = { config, ... }: {

    options = {

      port = mkOption {
        example = 22;
        type = types.int;
        description = ''
          External port number bound to the public IP of the deployment.
        '';
      };

      localPort = mkOption {
        example = 22;
        type = types.int;
        description = ''
          Local port number bound to the the VM network interface.
        '';
      };

      setName = mkOption {
        default = null;
        example = "http_balancer";
        type = types.nullOr types.str;
        description = ''
          Name of the load-balanced endpoint set.
        '';
      };

      probe.path = mkOption {
        default = null;
        example = "/";
        type = types.nullOr types.str;
        description = ''
          The relative HTTP path to inspect to determine the availability status of the Virtual Machine.
          If probe protocol is set to TCP, this value must be NULL.
        '';
      };

      probe.protocol = mkOption {
        default = null;
        example = "HTTP";
        type = types.nullOr types.str;
        description = ''
          The protocol to use to inspect the availability status of the Virtual Machine.
          Possible values are: HTTP, TCP.
        '';
      };

      probe.port = mkOption {
        default = null;
        example = 80;
        type = types.nullOr types.int;
        description = ''
          The port to use to inspect the availability status of the Virtual Machine.
        '';
      };


      directServerReturn = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
          Enable direct server return.
        '';
      };

    };

    config = {};

  };


  azureDiskOptions = { config, ... }: {

    options = {

      diskResource = mkOption {
        default = null;
        example = "external-disk2";
        type = types.nullOr (types.either types.str (resource "azure-disk"));
        description = ''
          The resource or the name of an existing disk not
          managed by NixOps, to attach to the virtual machine.
        '';
      };

      ephemeralName = mkOption {
        default = null;
        example = "data";
        type = types.nullOr types.str;
        description = ''
          The short name of an ephemeral disk to create. Emphemeral disk resources
          are automatically created and destroyed by NixOps as needed. The user
          has an option to keep the BLOB with contents after the disk is destroyed.
          Ephemeral disk names only need to be unique among the other ephemeral
          disks of the virtual machine instance.
        '';
      };

      label = mkOption {
        default = "";
        type = types.nullOr types.str;
        description = "Human-friendly label for the Azure disk up to 100 characters in length.";
      };

      mediaLink = mkOption {
        default = null;
        example = "http://mystorage.blob.core.windows.net/mycontainer/machine-disk";
        type = types.nullOr types.str;
        description = ''
          The location of the BLOB in the Azure BLOB store to store the ephemeral disk contents.
          The BLOB location must belong to a storage account in the same subscription
          as the virtual machine.
          If the BLOB doesn't exist, it will be created.
        '';
      };

      size = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          Volume size (in gigabytes) for automatically created
          Azure disks. This option value is ignored if you are
          creating a disk backed by an existing BLOB.
        '';
      };

      lun = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          Logical Unit Number (LUN) location for the data disk
          in the virtual machine. Required if the disk is created
          via fileSystems.X.azure attrset. The disk will appear
          as /dev/disk/by-lun/*. Must be unique.
          Valid values are: 0-31.
          LUN value must be less than the maximum number of
          allowed disks for the virtual machine size.
        '';
      };

      hostCaching = mkOption {
        default = "None";
        type = types.addCheck types.str
                (v: elem v [ "None" "ReadOnly" "ReadWrite" ]);
        description = ''
          Specifies the platform caching behavior of data disk blob for
          read/write efficiency. The default vault is None.
          Possible values are: None, ReadOnly, ReadWrite.
        '';
      };

      # FIXME: remove the LUKS options eventually?

      encrypt = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Whether the Azure disk should be encrypted using LUKS.
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
          access to the Azure disk or instance store that contains the
          Nix store can subsequently decrypt the encrypted volume.
        '';
      };

    };

    config = {
      label = mkDefault (config.ephemeralName or "");
    };
  };

in
{
  ###### interface

  options = {

    deployment.azure = (import ./azure-credentials.nix pkgs "instance") // {

      machineName = mkOption {
        default = "nixops-${uuid}-${name}";
        example = "custom-machine-name";
        type = types.str;
        description = "The Azure machine <literal>Name</literal>.";
      };


      roleSize = mkOption {
        default = "Small";
        example = "Large";
        type = types.str;
        description = ''
            The size of the virtual machine to allocate.
            Possible values are: ExtraSmall, Small, Medium, Large, ExtraLarge. 
        '';
      };

      storage = mkOption {
        default = null;
        example = "resources.azureStorages.mystorage";
        type = types.nullOr (types.either types.str (resource "azure-storage"));
        description = ''
          Azure storage service name or resource to use to manage
          the disk BLOBs during backup/restore operations.
        '';
      };

      hostedService = mkOption {
        default = null;
        example = "resources.azureHostedServices.myservice";
        type = types.either types.str (resource "azure-hosted-service");
        description = ''
          Azure hosted service name or resource to deploy the machine to.
        '';
      };

      deployment = mkOption {
        default = null;
        example = "resources.azureDesployments.mydeployment";
        type = types.either types.str (resource "azure-deployment");
        description = ''
          Azure deployment name or resource to deploy the machine to.
        '';
      };

      rootDiskImage = mkOption {
        example = "nixos-bootstrap-30GB";
        type = types.str;
        description = ''
          Bootstrap image URL.
        '';
      };

      baseEphemeralDiskUrl = mkOption {
        default = null;
        example = "http://mystorage.blob.core.windows.net/mycontainer/";
        type = types.nullOr types.str;
        description = ''
          Base URL to use to construct BLOB URLs for ephemeral disks which
          don't explicitly specify mediaLink.
        '';
      };

      blockDeviceMapping = mkOption {
        default = { };
        example = { "/dev/disk/by-lun/1".mediaLink =
                        "http://mystorage.blob.core.windows.net/mycontainer/machine-disk"; };
        type = types.attrsOf types.optionSet;
        options = azureDiskOptions;
        description = ''
          Block device mapping.
        '';
      };

      inputEndpoints.tcp = mkOption {
        default = { };
        example = { ssh = { port = 33; localPort = 22; }; };
        type = types.attrsOf types.optionSet;
        options = endpointOptions;
        description = ''
          TCP input endpoint options.
        '';
      };

      inputEndpoints.udp = mkOption {
        default = { };
        example = { dns = { port = 53; localPort = 640; }; };
        type = types.attrsOf types.optionSet;
        options = endpointOptions;
        description = ''
          UDP input endpoint options.
        '';
      };

      obtainIP = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
          Whether to obtain a dedicated public IP for the instance.
        '';
      };

      availabilitySet = mkOption {
        default = "";
        example = "database";
        type = types.str;
        description = ''
          Azure Virtual Machines specified in the same availability set
          are allocated to different nodes to maximize availability.
        '';
      };

    };

    fileSystems = mkOption {
      options = { config, ... }: {
        options = {
          azure = mkOption {
            default = null;
            type = types.uniq (types.nullOr types.optionSet);
            options = azureDiskOptions;
            description = ''
              Azure disk to be attached to this mount point.  This is
              a shorthand for defining a separate
              <option>deployment.azure.blockDeviceMapping</option>
              attribute.
            '';
          };
        };
        config = mkIf(config.azure != null) {
          device = mkDefault (
              if config.azure.encrypt then "/dev/mapper/${luksName (mkDefaultEphemeralName config.mountPoint config.azure)}"
                                      else "/dev/disk/by-lun/${toString config.azure.lun}"
            );
        };
      };
    };

  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "azure") {
    nixpkgs.system = mkOverride 900 "x86_64-linux";

    deployment.azure.blockDeviceMapping = {
      "/dev/sda" = {
        ephemeralName = "root";
        hostCaching = "ReadWrite";
      };
    } // (listToAttrs
      (map (fs: let fsazure = mkDefaultEphemeralName fs.mountPoint fs.azure; in
                nameValuePair "/dev/disk/by-lun/${toString fs.azure.lun}" fsazure
        )
       (filter (fs: fs.azure != null) (attrValues config.fileSystems))));


    deployment.autoLuks =
      let
        f = dev: definition: nameValuePair
          ( luksName definition)
          { device = dev;
            autoFormat = true;
            inherit (definition) cipher keySize passphrase;
          };
      in mapAttrs' f (filterAttrs (name: dev: dev.encrypt) config.deployment.azure.blockDeviceMapping);


  };
}
