{ config, lib, ... }:

with lib;

let

  cfg = config.deployment;

in

{

  imports =
    [ ./ec2.nix
      ./digital-ocean.nix
      ./route53.nix
      ./virtualbox.nix
      ./ssh-tunnel.nix
      ./auto-raid0.nix
      ./auto-luks.nix
      ./keys.nix
      ./gce.nix
      ./hetzner.nix
      ./container.nix
      ./libvirtd.nix
    ];


  options = {

    deployment.targetEnv = mkOption {
      default = "none";
      example = "ec2";
      type = types.str;
      description = ''
        This option specifies the type of the environment in which the
        machine is to be deployed by NixOps.  Currently, it can have
        the following values. <literal>"none"</literal> means
        deploying to a pre-existing physical or virtual NixOS machine,
        reachable via SSH under the hostname or IP address specified
        in <option>deployment.targetHost</option>.
        <literal>"ec2"</literal> means that a virtual machine should
        be instantiated in an Amazon EC2-compatible cloud environment
        (see <option>deployment.ec2.*</option>).
        <literal>"virtualbox"</literal> causes a VirtualBox VM to be
        created on your machine.  (This requires VirtualBox to be
        configured on your system.)
      '';
    };

    deployment.targetHost = mkOption {
      type = types.str;
      description = ''
        This option specifies the hostname or IP address to be used by
        NixOps to execute remote deployment operations.
      '';
    };

    deployment.targetPort = mkOption {
      type = types.int;
      description = ''
        This option specifies the SSH port to be used by
        NixOps to execute remote deployment operations.
      '';
    };

    deployment.alwaysActivate = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Always run the activation script, no matter whether the configuration
        has changed (the default). This behaviour can be enforced even if it's
        set to <literal>false</literal> using the command line option
        <literal>--always-activate</literal> on deployment.

        If this is set to <literal>false</literal>, activation is done only if
        the new system profile doesn't match the previous one.
      '';
    };

    deployment.encryptedLinksTo = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        NixOps will set up an encrypted tunnel (via SSH) to the
        machines listed here.  Since this is a two-way (peer to peer)
        connection, it is not necessary to set this option on both
        endpoints.  NixOps will set up <filename>/etc/hosts</filename>
        so that the host names of the machines listed here resolve to
        the IP addresses of the tunnels.  It will also add the alias
        <literal><replaceable>machine</replaceable>-encrypted</literal>
        for each machine.
      '';
    };

    deployment.owners = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        List of email addresses of the owners of the machines. Used
        to send email on performing certain actions.
      '';
    };

    deployment.hasFastConnection = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If set to <literal>true</literal>, whole closure will be copied using just `nix-copy-closure`.

        If set to <literal>false</literal>, closure will be copied first using binary substitution.
        Addtionally, any missing derivations copied with `nix-copy-closure` will be done
        using <literal>--gzip</literal> flag.

        Some backends set this value to <literal>true</literal>.
      '';
    };

    # Computed options useful for referring to other machines in
    # network specifications.

    networking.privateIPv4 = mkOption {
      example = "10.1.2.3";
      type = types.str;
      description = ''
        IPv4 address of this machine within in the logical network.
        This address can be used by other machines in the logical
        network to reach this machine.  However, it need not be
        visible to the outside (i.e., publicly routable).
      '';
    };

    networking.publicIPv4 = mkOption {
      default = null;
      example = "198.51.100.123";
      type = types.nullOr types.str;
      description = ''
        Publicly routable IPv4 address of this machine.
      '';
    };

    networking.vpnPublicKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Public key of the machine's VPN key (set by nixops)";
    };

  };


  config = {

    _type = "machine";

    deployment.targetHost = mkDefault config.networking.hostName;
    deployment.targetPort = mkDefault (head config.services.openssh.ports);

  };

}
