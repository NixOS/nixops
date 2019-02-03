# Configuration specific to the EC2 backend.

{ config, pkgs, lib, utils, ... }:

with utils;
with lib;
with import ./lib.nix lib;

let

  types =
    if lib.types ? either then
      lib.types
    else
      builtins.trace "Please update Nixpkgs for this deployment. The next NixOps release will be incompatible with your current version of Nixpkgs."
      (lib.types // {
         either = t1: t2: mkOptionType {
           name = "${t1.name} or ${t2.name}";
           check = x: t1.check x || t2.check x;
           merge = mergeOneOption;
         };
       });

  cfg = config.deployment.ec2;

  defaultEbsOptimized =
    let props = config.deployment.ec2.physicalProperties;
    in if props == null then false else (props.allowsEbsOptimized or false);

  defaultUsePrivateIpAddress =
    let
      assocPublicIp = config.deployment.ec2.associatePublicIpAddress;
      subnetId = config.deployment.ec2.subnetId;
    in
      if assocPublicIp == false && subnetId != "" then
        true
      else
        false;

  commonEC2Options = import ./common-ec2-options.nix { inherit lib; };

  ec2DiskOptions = { config, ... }: {

    imports = [ ./common-ebs-options.nix ];

    options = {

      disk = mkOption {
        default = "";
        example = "vol-00000000";
        type = types.either types.str (resource "ebs-volume");
        apply = x: if builtins.isString x then x else "res-" + x._name;
        description = ''
          EC2 identifier of the disk to be mounted.  This can be an
          ephemeral disk (e.g. <literal>ephemeral0</literal>), a
          snapshot ID (e.g. <literal>snap-00000000</literal>) or a
          volume ID (e.g. <literal>vol-00000000</literal>).  Leave
          empty to create an EBS volume automatically.  It can also be
          an EBS resource (e.g. <literal>resources.ebsVolumes.big-disk</literal>).
        '';
      };

      fsType = mkOption {
        default = "ext4"; # FIXME: this default doesn't work
        type = types.str;
        description = ''
          Filesystem type for automatically created EBS volumes.
        '';
      };

      deleteOnTermination = mkOption {
        type = types.bool;
        description = ''
          For automatically created EBS volumes, determines whether the
          volume should be deleted on instance termination.
        '';
      };

      # FIXME: remove the LUKS options eventually?

      encrypt = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Whether the EBS volume should be encrypted using LUKS.
        '';
      };

      encryptionType = mkOption {
        default = "luks";
        type = types.enum [ "luks" "ebs" ];
        description = ''
          Whether the EBS volume should be encrypted using LUKS or on the
          underlying EBS volume (Amazon EBS feature). Possible values are
          "luks" (default) and "ebs".
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
          access to the EBS volume or instance store that contains the
          Nix store can subsequently decrypt the encrypted volume.
        '';
      };

    };

    config = {
      size = mkIf (config.disk != "") (mkDefault 0);
      # Automatically delete volumes that are automatically created.
      deleteOnTermination = mkDefault (config.disk == "" || substring 0 5 config.disk == "snap-");
    };

  };

  fileSystemsOptions = {
    options.ec2 = mkOption {
      default = null;
      type = with types; (nullOr (submodule ec2DiskOptions));
      description = ''
        EC2 disk to be attached to this mount point.  This is
        shorthand for defining a separate
        <option>deployment.ec2.blockDeviceMapping</option>
        attribute.
      '';
    };
  };

  isEc2Hvm =
    let
      instanceTypeGroup = builtins.elemAt (splitString "." cfg.instanceType) 0;
      pvGrubGroups = [ "c1" "hi1" "m1" "m2" "t1" ];
    in
      ! (builtins.elem instanceTypeGroup pvGrubGroups);

  # Map "/dev/mapper/xvdX" to "/dev/xvdX".
  dmToDevice = dev:
    if builtins.substring 0 12 dev == "/dev/mapper/"
    then "/dev/" + builtins.substring 12 100 dev
    else dev;

  nixosVersion = builtins.substring 0 5 (config.system.nixos.version or config.system.nixosVersion);

  amis = import <nixpkgs/nixos/modules/virtualisation/ec2-amis.nix>;

in

{

  ###### interface

  options = {

    deployment.ec2.accessKeyId = mkOption {
      default = "";
      example = "AKIABOGUSACCESSKEY";
      type = types.str;
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key. If the lookup was unsuccessful it is continued
        in the standard AWS tools <filename>~/.aws/credentials</filename> file.
        If it does not appear in these files, the
        environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    deployment.ec2.region = mkOption {
      default = "";
      example = "us-east-1";
      type = types.str;
      description = ''
        AWS region in which the instance is to be deployed.
        This option only applies when using EC2.  It implicitly sets
        <option>deployment.ec2.ami</option>.
      '';
    };

    deployment.ec2.zone = mkOption {
      default = "";
      example = "us-east-1c";
      type = types.str;
      description = ''
        The EC2 availability zone in which the instance should be
        created.  If not specified, a zone is selected automatically.
      '';
    };

    deployment.ec2.ebsBoot = mkOption {
      default = true;
      type = types.bool;
      description = ''
        Whether you want to boot from an EBS-backed AMI.  Only
        EBS-backed instances can be stopped and restarted, and attach
        other EBS volumes at boot time.  This option determines the
        selection of the default AMI; if you explicitly specify
        <option>deployment.ec2.ami</option>, it has no effect.
      '';
    };

    deployment.ec2.ebsInitialRootDiskSize = mkOption {
      default = 0;
      type = types.int;
      description = ''
        Preferred size (G) of the root disk of the EBS-backed instance. By
        default, EBS-backed images have a size determined by the
        AMI. Only supported on creation of the instance.
      '';
    };

    deployment.ec2.ami = mkOption {
      example = "ami-00000000";
      type = types.str;
      description = ''
        EC2 identifier of the AMI disk image used in the virtual
        machine.  This must be a NixOS image providing SSH access.
      '';
    };

    deployment.ec2.instanceType = mkOption {
      default = "m1.small";
      example = "m1.large";
      type = types.str;
      description = ''
        EC2 instance type.  See <link
        xlink:href='http://aws.amazon.com/ec2/instance-types/'/> for a
        list of valid Amazon EC2 instance types.
      '';
    };

    deployment.ec2.instanceId = mkOption {
      default = "";
      type = types.str;
      description = ''
        EC2 instance ID (set by NixOps).
      '';
    };

    deployment.ec2.instanceProfile = mkOption {
      default = "";
      example = "rolename";
      type = types.str;
      description = ''
        The name of the IAM Instance Profile (IIP) to associate with
        the instances.
      '';
    };

    deployment.ec2.keyPair = mkOption {
      example = "my-keypair";
      type = types.either types.str (resource "ec2-keypair");
      apply = x: if builtins.isString x then x else x.name;
      description = ''
        Name of the SSH key pair to be used to communicate securely
        with the instance.  Key pairs can be created using the
        <command>ec2-add-keypair</command> command.
      '';
    };

    deployment.ec2.privateKey = mkOption {
      default = "";
      example = "/home/alice/.ssh/id_rsa-my-keypair";
      type = types.str;
      description = ''
        Path of the SSH private key file corresponding with
        <option>deployment.ec2.keyPair</option>.  NixOps will use this
        private key if set; otherwise, the key must be findable by SSH
        through its normal mechanisms (e.g. it should be listed in
        <filename>~/.ssh/config</filename> or added to the
        <command>ssh-agent</command>).
      '';
    };

    deployment.ec2.securityGroups = mkOption {
      default = [ "default" ];
      example = [ "my-group" "my-other-group" ];
      type = types.listOf (types.either types.str (resource "ec2-security-group"));
      apply = map (x: if builtins.isString x then x else x.name);
      description = ''
        Security groups for the instance.  These determine the
        firewall rules applied to the instance.
      '';
    };

    deployment.ec2.securityGroupIds = mkOption {
      default = [ "default" ];
      type = types.listOf types.str;
      description = ''
        Security Group IDs for the instance. Necessary if starting
        an instance inside a VPC/subnet. In the non-default VPC, security
        groups needs to be specified by ID and not name.
      '';
    };

    deployment.ec2.subnetId = mkOption {
      default = "";
      example = "subnet-00000000";
      type = types.either types.str (resource "vpc-subnet");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The subnet inside a VPC to launch the instance in.
      '';
    };

    deployment.ec2.associatePublicIpAddress = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If instance in a subnet/VPC, whether to associate a public
        IP address with the instance.
      '';
    };

    deployment.ec2.usePrivateIpAddress = mkOption {
      default = defaultUsePrivateIpAddress;
      type = types.bool;
      description = ''
        If instance is in a subnet/VPC whether to use the private
        IP address for ssh connections to this host. Defaults to
        true in the case that you are deploying into a subnet but
        not associating a public ip address.
      '';
    };

    deployment.ec2.placementGroup = mkOption {
      default = "";
      example = "my-cluster";
      type = types.either types.str (resource "ec2-placement-group");
      apply = x: if builtins.isString x then x else x.name;
      description = ''
        Placement group for the instance.
      '';
    };

    deployment.ec2.tags = commonEC2Options.tags;

    deployment.ec2.blockDeviceMapping = mkOption {
      default = { };
      example = { "/dev/xvdb".disk = "ephemeral0"; "/dev/xvdg".disk = "vol-00000000"; };
      type = with types; attrsOf (submodule ec2DiskOptions);
      description = ''
        Block device mapping.

        <filename>/dev/sd[a-e]</filename> or <filename>/dev/xvd[a-e]</filename> must be ephemeral devices.

        With the following instances, EBS volumes are exposed as NVMe block devices: C5, C5d, i3.metal, M5, and M5d (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html). For these instances volumes should be attached as <filename>/dev/nvme[1-26]n1</filename>, there should be no hole in numbering.

        <example>
        {
          machine = {
            deployment.ec2.blockDeviceMapping."/dev/nvme1n1".size = 1;
            deployment.ec2.blockDeviceMapping."/dev/nvme3n1".size = 1; # this device will be attached as /dev/nvme2n1, you should use /dev/nvme2n1
          };
        }
        </example>
      '';
    };

    deployment.ec2.elasticIPv4 = mkOption {
      default = "";
      example = "123.1.123.123";
      type = types.either types.str (resource "elastic-ip");
      apply = x: if builtins.isString x then x else "res-" + x._name;
      description = ''
        Elastic IPv4 address to be associated with this machine.
      '';
    };

    deployment.ec2.physicalProperties = mkOption {
      default = {};
      example = { cores = 4; memory = 14985; };
      description = ''
        Attribute set containing number of CPUs and memory available to
        the machine.
      '';
    };

    deployment.ec2.spotInstancePrice = mkOption {
      default = 0;
      type = types.int;
      description = ''
        Price (in dollar cents per hour) to use for spot instances request for the machine.
        If the value is equal to 0 (default), then spot instances are not used.
      '';
    };

    deployment.ec2.spotInstanceTimeout = mkOption {
      default = 0;
      type = types.int;
      description = ''
        The duration (in seconds) that the spot instance request is
        valid. If the request cannot be satisfied in this amount of
        time, the request will be cancelled automatically, and NixOps
        will fail with an error message. The default (0) is no timeout.
      '';
    };

    deployment.ec2.ebsOptimized = mkOption {
      default = defaultEbsOptimized;
      type = types.bool;
      description = ''
        Whether the EC2 instance should be created as an EBS Optimized instance.
      '';
    };

    fileSystems = mkOption {
      type = with types; loaOf (submodule fileSystemsOptions);
    };

  };


  ###### implementation

  config = mkIf (config.deployment.targetEnv == "ec2") {

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    deployment.ec2.ami = mkDefault (
      let
        # FIXME: select hvm-s3 AMIs if appropriate.
        type =
          if isEc2Hvm then
            if cfg.ebsBoot then "hvm-ebs" else "hvm-s3"
          else
            if cfg.ebsBoot then "pv-ebs" else "pv-s3";
        amis' = amis."${nixosVersion}" or amis.latest;
      in
        with builtins;
        if hasAttr cfg.region amis' then
          let r = amis'."${cfg.region}";
        in if hasAttr type r then r."${type}" else
          throw "I don't know an AMI for virtualisation type ${type} with instance type ${cfg.instanceType}"
        else
          throw "I don't know an AMI for region ‘${cfg.region}’ and platform type ‘${config.nixpkgs.system}’"
      );

    # Workaround: the evaluation of blockDeviceMapping requires fileSystems to be defined.
    fileSystems = {};

    deployment.ec2.blockDeviceMapping = mkFixStrictness (listToAttrs
      (map (fs: nameValuePair (dmToDevice fs.device)
        { inherit (fs.ec2) disk size deleteOnTermination encrypt cipher keySize passphrase iops volumeType encryptionType;
          fsType = if fs.fsType != "auto" then fs.fsType else fs.ec2.fsType;
        })
       (filter (fs: fs.ec2 != null) (attrValues config.fileSystems))));

    deployment.autoLuks =
      let
        f = name: dev: nameValuePair (baseNameOf name)
          { device = "/dev/${baseNameOf name}";
            autoFormat = true;
            inherit (dev) cipher keySize passphrase;
          };
      in mapAttrs' f (filterAttrs (name: dev: dev.encrypt) cfg.blockDeviceMapping);

    deployment.ec2.physicalProperties =
      let
        type = config.deployment.ec2.instanceType or "unknown";
        mapping = import ./ec2-properties.nix;
      in attrByPath [ type ] null mapping;

  };

}
