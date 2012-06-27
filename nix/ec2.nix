# Configuration specific to the EC2/Nova/Eucalyptus backend.

{ config, pkgs, ... }:

with pkgs.lib;

let

  cfg = config.deployment.ec2;

  ec2DiskOptions = { config, ... }: {
  
    options = {
      
      disk = mkOption {
        default = "";
        example = "vol-d04895b8";
        type = types.uniq types.string;
        description = ''
          EC2 identifier of the disk to be mounted.  This can be an
          ephemeral disk (e.g. <literal>ephemeral0</literal>), a
          snapshot ID (e.g. <literal>snap-1cbda474</literal>) or a
          volume ID (e.g. <literal>vol-d04895b8</literal>).  Leave
          empty to create an EBS volume automatically.
        '';
      };

      size = mkOption {
        default = 0;
        type = types.uniq types.int;
        description = ''
          Filesystem size (in gigabytes) for automatically created
          EBS volumes.
        '';
      };

      fsType = mkOption {
        default = "ext4";
        type = types.uniq types.string;
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

      encrypt = mkOption {
        default = false;
        type = types.bool;
        description = ''
          Whether the EBS volume should be encrypted using LUKS.
        '';
      };

      cipher = mkOption {
        default = "aes-cbc-essiv:sha256";
        type = types.uniq types.string;
        description = ''
          The cipher used to encrypt the disk.
        '';
      };

      keySize = mkOption {
        default = 128;
        type = types.uniq types.int;
        description = ''
          The size of the encryption key.
        '';
      };

      passphrase = mkOption {
        default = "";
        type = types.uniq types.string;
        description = ''
          The passphrase (key file) used to decrypt the key to access
          the device.  If left empty, a passphrase is generated
          automatically; this passphrase is lost when you destroy the
          machine or remove the volume, unless you copy it from
          Charon's state file.  Note that the passphrase is stored in
          the Nix store of the instance, so an attacker who gains
          access to the EBS volume or instance store that contains the
          Nix store can subsequently decrypt the encrypted volume.
        '';
      };

    };

    config = {
      deleteOnTermination = mkDefault (config.disk == "");
    };

  };

  isEc2Hvm = (cfg.instanceType == "cc1.4xlarge" || cfg.instanceType == "cc2.8xlarge");

  # Map "/dev/mapper/xvdX" to "/dev/xvdX".
  dmToDevice = dev:
    if builtins.substring 0 12 dev == "/dev/mapper/"
    then "/dev/" + builtins.substring 12 100 dev
    else dev;
  
in

{

  ###### interface

  options = {

    deployment.ec2.accessKeyId = mkOption {
      default = "";
      example = "AKIAIEMEJZVMPOHZWKZQ";
      type = types.uniq types.string;
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key.  If it does not appear in that file, the
        environment variables environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    deployment.ec2.type = mkOption {
      default = "ec2";
      example = "nova";
      type = types.uniq types.string;
      description = ''
        Specifies the type of cloud.  This affects the machine
        configuration.  Current values are <literal>"ec2"</literal>
        and <literal>"nova"</literal>.
      '';
    };

    deployment.ec2.controller = mkOption {
      example = https://ec2.eu-west-1.amazonaws.com/;
      type = types.uniq types.string;
      description = ''
        URI of an Amazon EC2-compatible cloud controller web service,
        used to create and manage virtual machines.  If you're using
        EC2, it's more convenient to set
        <option>deployment.ec2.region</option>.
      '';
    };

    deployment.ec2.region = mkOption {
      default = "";
      example = "us-east-1";
      type = types.uniq types.string;
      description = ''
        Amazon EC2 region in which the instance is to be deployed.
        This option only applies when using EC2.  It implicitly sets
        <option>deployment.ec2.controller</option> and
        <option>deployment.ec2.ami</option>.
      '';
    };

    deployment.ec2.ebsBoot = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Whether you want to boot from an EBS-backed AMI.  Only
        EBS-backed instances can be stopped and restarted, and attach
        other EBS volumes at boot time.  This option determines the
        selection of the default AMI; if you explicitly specify
        <option>deployment.ec2.ami</option>, it has no effect.
      '';
    };

    deployment.ec2.ami = mkOption {
      example = "ami-ecb49e98";
      type = types.uniq types.string;
      description = ''
        EC2 identifier of the AMI disk image used in the virtual
        machine.  This must be a NixOS image providing SSH access.
      '';
    };

    deployment.ec2.instanceType = mkOption {
      default = "m1.small";
      example = "m1.large";
      type = types.uniq types.string;
      description = ''
        EC2 instance type.  See <link
        xlink:href='http://aws.amazon.com/ec2/instance-types/'/> for a
        list of valid Amazon EC2 instance types.
      '';
    };

    deployment.ec2.keyPair = mkOption {
      example = "my-keypair";
      type = types.uniq types.string;
      description = ''
        Name of the SSH key pair to be used to communicate securely
        with the instance.  Key pairs can be created using the
        <command>ec2-add-keypair</command> command.
      '';
    };

    deployment.ec2.privateKey = mkOption {
      default = "";
      example = "/home/alice/.ssh/id_rsa-my-keypair";
      type = types.uniq types.string;
      description = ''
        Path of the SSH private key file corresponding with
        <option>deployment.ec2.keyPair</option>.  Charon will use this
        private key if set; otherwise, the key must be findable by SSH
        through its normal mechanisms (e.g. it should be listed in
        <filename>~/.ssh/config</filename> or added to the
        <command>ssh-agent</command>).
      '';
    };

    deployment.ec2.securityGroups = mkOption {
      default = [ "default" ];
      example = [ "my-group" "my-other-group" ];
      type = types.list types.string;
      description = ''
        Security groups for the instance.  These determine the
        firewall rules applied to the instance.
      '';
    };

    deployment.ec2.tags = mkOption {
      default = { };
      example = { foo = "bar"; xyzzy = "bla"; };
      type = types.attrsOf types.string;
      description = ''
        EC2 tags assigned to the instance.  Each tag name can be at
        most 128 characters, and each tag value can be at most 256
        characters.  There can be at most 10 tags.
      '';
    };

    deployment.ec2.blockDeviceMapping = mkOption {
      default = { };
      example = { "/dev/xvdb".disk = "ephemeral0"; "/dev/xvdg".disk = "vol-d04895b8"; };
      type = types.attrsOf types.optionSet;
      options = ec2DiskOptions;
      description = ''
        Block device mapping.  Currently only supports ephemeral devices.
      '';
    };

    deployment.ec2.elasticIPv4 = mkOption {
      default = "";
      example = "203.0.113.123";
      type = types.uniq types.string;
      description = ''
        Elastic IPv4 address to be associated with this machine.
      '';
    };

    fileSystems = mkOption {
      options = {
        ec2 = mkOption {
          default = null;
          type = types.uniq (types.nullOr types.optionSet);
          options = ec2DiskOptions;
          description = ''
            EC2 disk to be attached to this mount point.  This is
            shorthand for defining a separate
            <option>deployment.ec2.blockDeviceMapping</option>
            attribute.
          '';
        };
      };
    };

  };

      
  ###### implementation

  config = mkIf (config.deployment.targetEnv == "ec2") {
  
    boot.loader.grub.extraPerEntryConfig = mkIf isEc2Hvm ( mkOverride 10 "root (hd0,0)" );

    deployment.ec2.controller = mkDefault "https://ec2.${cfg.region}.amazonaws.com/";

    # The list below is generated by running the "create-amis.sh" script, then doing:
    # $ while read system region ami; do echo "        if cfg.region == \"$region\" && config.nixpkgs.system == \"$system\" then \"$ami\" else"; done < amis
    deployment.ec2.ami = mkDefault (
      if cfg.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" &&  isEc2Hvm then "ami-6a9e4503" else
      if cfg.region == "eu-west-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ebsBoot then "ami-732c1407" else
      if cfg.region == "eu-west-1" && config.nixpkgs.system == "x86_64-linux" &&  cfg.ebsBoot then "ami-c3e5e0b7" else
      if cfg.region == "eu-west-1" && config.nixpkgs.system == "i686-linux"   && !cfg.ebsBoot then "ami-dd90a9a9" else
      if cfg.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ebsBoot then "ami-d9409fb0" else
      if cfg.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" &&  cfg.ebsBoot then "ami-dabe1db3" else
      if cfg.region == "us-west-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ebsBoot then "ami-4996ce0c" else
      # !!! Doesn't work, not lazy enough.
      #throw "I don't know an AMI for region ‘${cfg.region}’ and platform type ‘${config.nixpkgs.system}’"
      "");

    # Workaround: the evaluation of blockDeviceMapping requires fileSystems to be defined.
    fileSystems = [];

    deployment.ec2.blockDeviceMapping = listToAttrs
      (map (fs: nameValuePair (dmToDevice fs.device)
        { inherit (fs.ec2) disk size deleteOnTermination encrypt passphrase;
          fsType = if fs.fsType != "auto" then fs.fsType else fs.ec2.fsType;
        })
       (filter (fs: fs.ec2 != null) config.fileSystems));

    jobs."init-luks" =
      { task = true;

        startOn = "starting mountall";

        path = [ pkgs.cryptsetup pkgs.utillinux ];

        script =
          ''
            ${concatStrings (attrValues (flip mapAttrs cfg.blockDeviceMapping (name: dev:
              # FIXME: The key file should be marked as private once
              # https://github.com/NixOS/nix/issues/8 is fixed.
              let keyFile = pkgs.writeText "luks-key" dev.passphrase; in
              optionalString dev.encrypt (assert dev.passphrase != ""; ''
                if [ -e "${name}" ]; then
                
                  # Do LUKS formatting if the device is empty.  FIXME:
                  # this check is kinda dangerous.  For EC2 we could
                  # just check if the first sector is empty.
                  type=$(blkid -p -s TYPE -o value "${name}" || true)
                  if [ -z "$type" ]; then
                    echo "initialising encryption on device ‘${name}’..."
                    cryptsetup luksFormat "${name}" --key-file=${keyFile} --cipher ${dev.cipher} --key-size ${toString dev.keySize}
                  fi

                fi

                base="$(basename "${name}")"
                if [ ! -e "/dev/mapper/$base" ]; then
                
                  # Activate the LUKS device.
                  cryptsetup luksOpen "${name}" "$base" --key-file=${keyFile}

                fi

              ''))))}
          '';
      };

  };

}
