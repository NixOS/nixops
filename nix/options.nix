{ config, pkgs, ... }:

with pkgs.lib;

let

  cfg = config.deployment;

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

    };

    config = {
      deleteOnTermination = mkDefault (config.disk == "");
    };

  };

  isEc2Hvm = (cfg.ec2.instanceType == "cc1.4xlarge" || cfg.ec2.instanceType == "cc2.8xlarge");
  
in

{
  options = {

    deployment.targetEnv = mkOption {
      default = "none";
      example = "ec2";
      type = types.uniq types.string;
      description = ''
        This option specifies the type of the environment in which the
        machine is to be deployed by Charon.  Currently, it can have
        the following values. <literal>"none"</literal> means
        deploying to a pre-existing physical or virtual NixOS machine,
        reachable via SSH under the hostname or IP address specified
        in <option>deployment.targetHost</option>.
        <literal>"ec2"</literal> means that a virtual machine should
        be instantiated in an Amazon EC2-compatible cloud environment
        (see <option>deployment.ec2.*</option>).
        <literal>"virtualbox"</literal> causes a VirtualBox VM to be
        created on your machine.  (This requires VirtualBox to be
        configured on your system.)  <literal>"adhoc-cloud"</literal>
        means that a virtual machine should be instantiated by
        executing certain commands via SSH on a cloud controller
        machine (see <option>deployment.adhoc.*</option>).  This is
        primarily useful for debugging Charon.
      '';
    };

    deployment.targetHost = mkOption {
      default = config.networking.hostName;
      type = types.uniq types.string;
      description = ''
        This option specifies the hostname or IP address to be used by
        Charon to execute remote deployment operations.
      '';
    };

    
    # EC2/Nova/Eucalyptus-specific options.

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

    
    # Ad hoc cloud options.

    deployment.adhoc.controller = mkOption {
      example = "cloud.example.org";
      type = types.uniq types.string;
      description = ''
        Hostname or IP addres of the machine to which Charon should
        connect (via SSH) to execute commands to start VMs or query
        their status.
      '';
    };

    deployment.adhoc.createVMCommand = mkOption {
      default = "create-vm";
      type = types.uniq types.string;
      description = ''
        Remote command to create a NixOS virtual machine.  It should
        print an identifier denoting the VM on standard output.
      '';
    };

    deployment.adhoc.destroyVMCommand = mkOption {
      default = "destroy-vm";
      type = types.uniq types.string;
      description = ''
        Remote command to destroy a previously created NixOS virtual
        machine.
      '';
    };

    deployment.adhoc.queryVMCommand = mkOption {
      default = "query-vm";
      type = types.uniq types.string;
      description = ''
        Remote command to query information about a previously created
        NixOS virtual machine.  It should print the IPv6 address of
        the VM on standard output.
      '';
    };

    
    # VirtualBox options.

    deployment.virtualbox.baseImage = mkOption {
      example = "/home/alice/base-disk.vdi";
      description = ''
        Path to the initial disk image used to bootstrap the
        VirtualBox instance.  The instance boots from a clone of this
        image.
      '';
    };

    deployment.virtualbox.memorySize = mkOption {
      default = 512;
      type = types.int;
      description = ''
        Memory size (M) of virtual machine.
      '';
    };

    deployment.virtualbox.headless = mkOption {
      default = false;
      description = ''
        If set, the VirtualBox instance is started in headless mode,
        i.e., without a visible display on the host's desktop.
      '';
    };

    
    # Computed options useful for referring to other machines in
    # network specifications.

    networking.privateIPv4 = mkOption {
      example = "10.1.2.3";
      type = types.uniq types.string;
      description = ''
        IPv4 address of this machine within in the logical network.
        This address can be used by other machines in the logical
        network to reach this machine.  However, it need not be
        visible to the outside (i.e., publicly routable).
      '';
    };

    networking.publicIPv4 = mkOption {
      example = "198.51.100.123";
      type = types.uniq types.string;
      description = ''
        Publicly routable IPv4 address of this machine.
      '';
    };

  };


  config = {
  
    boot.loader.grub.extraPerEntryConfig = mkIf isEc2Hvm ( mkOverride 10 "root (hd0,0)" );

    # Workaround: the evaluation of blockDeviceMapping requires fileSystems to be defined.
    fileSystems = [];

    deployment.ec2 = mkIf (cfg.ec2.region != "") {
    
      controller = mkDefault "https://ec2.${cfg.ec2.region}.amazonaws.com/";

      # The list below is generated by running the "create-amis.sh" script, then doing:
      # $ while read system region ami; do echo "        if cfg.ec2.region == \"$region\" && config.nixpkgs.system == \"$system\" then \"$ami\" else"; done < amis
      ami = mkDefault (
        if cfg.ec2.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" &&  isEc2Hvm then "ami-6a9e4503" else
        if cfg.ec2.region == "eu-west-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ec2.ebsBoot then "ami-732c1407" else
        if cfg.ec2.region == "eu-west-1" && config.nixpkgs.system == "x86_64-linux" &&  cfg.ec2.ebsBoot then "ami-2b665d5f" else
        if cfg.ec2.region == "eu-west-1" && config.nixpkgs.system == "i686-linux"   && !cfg.ec2.ebsBoot then "ami-dd90a9a9" else
        if cfg.ec2.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ec2.ebsBoot then "ami-d9409fb0" else
        if cfg.ec2.region == "us-east-1" && config.nixpkgs.system == "x86_64-linux" &&  cfg.ec2.ebsBoot then "ami-54a8733d" else
        if cfg.ec2.region == "us-west-1" && config.nixpkgs.system == "x86_64-linux" && !cfg.ec2.ebsBoot then "ami-4996ce0c" else
        # !!! Doesn't work, not lazy enough.
        #throw "I don't know an AMI for region ‘${cfg.ec2.region}’ and platform type ‘${config.nixpkgs.system}’"
        "");

      blockDeviceMapping = listToAttrs
        (map (fs: nameValuePair fs.device
          { disk = fs.ec2.disk;
            size = fs.ec2.size;
            fsType = if fs.fsType != "auto" then fs.fsType else fs.ec2.fsType;
          })
         (filter (fs: fs.ec2 != null) config.fileSystems));

    };

    deployment.virtualbox = {

      baseImage = mkDefault (
        let
          unpack = name: sha256: pkgs.runCommand "virtualbox-charon-${name}.vdi" {}
            ''
              xz -d < ${pkgs.fetchurl {
                url = "http://nixos.org/releases/nixos/virtualbox-charon-images/virtualbox-charon-${name}.vdi.xz";
                inherit sha256;
              }} > $out
            '';
        in if config.nixpkgs.system == "x86_64-linux" then
          unpack "0.1pre33926-33924-x86_64" "0c9857e3955bb5af273375e85c0a62a50323ccfaef0a29b5eb7f1539077c1c40"
        else
          # !!! Stupid lack of laziness
          # throw "Unsupported VirtualBox system type!"
          ""
      );
    
    };
        
  };
  
}
