{ config, pkgs, ... }:

with pkgs.lib;

let

  cfg = config.deployment;

in

{

  imports = [ ./ec2.nix ./ssh-tunnel.nix ];
  
  
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

    deployment.encryptedLinksTo = mkOption {
      default = [];
      type = types.list types.string;
      description = ''
        Charon will set up an encrypted tunnel (via SSH) to the
        machines listed here.  Since this is a two-way (peer to peer)
        connection, it is not necessary to set this option on both
        endpoints.  Charon will set up <filename>/etc/hosts</filename>
        so that the host names of the machines listed here resolve to
        the IP addresses of the tunnels.  It will also add the alias
        <literal><replaceable>machine</replaceable>-encrypted</literal>
        for each machine.
      '';
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
