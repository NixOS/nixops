{ config, lib, ... }:

with lib;

let

  cfg = config.deployment;

in

{

  imports =
    [
      ./auto-raid0.nix
      ./auto-luks.nix
      ./keys.nix
    ];


  options = {

    deployment.targetEnv = mkOption {
      default = "none";
      example = "ec2";
      type = types.str;
      description = ''
        This option specifies the type of the environment in which the
        machine is to be deployed by NixOps.
      '';
    };

    deployment.targetUser = mkOption {
      # type = types.nullOr types.str;
      type = types.str;
      default = "root";
      description = ''
        The username to be used by NixOps by SSH when connecting to the
        remote system.
      '';
      # If <literal>targetUser</literal> is set to <literal>null</literal>
      # the username is set to the username of the user invoking
      # </literal>nixops</literal>.
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

    deployment.sshOptions = mkOption {
      type = types.listOf types.str;
      default = [];
      description = ''
        Extra options passed to the OpenSSH client verbatim, and are not executed by a shell.
      '';
    };

    deployment.privilegeEscalationCommand = mkOption {
      type = types.listOf types.str;
      default = [ "sudo" "-H" "--" ];
      description = ''
        A command to escalate to root privileges when using SSH as a non-root user.
        This option is ignored if the <literal>targetUser</literal> option is set to <literal>root</literal>.

        The program and its options are executed verbatim without shell.

        It's good practice to end with "--" to indicate that the privilege escalation command
        should stop processing command line arguments.
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
