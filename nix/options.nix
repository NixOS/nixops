{ name, config, lib, ... }:
with lib;
{
  imports = [ ./keys.nix ];
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
      # If ``targetUser`` is set to ``null``
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

    deployment.provisionSSHKey = mkOption {
      type = types.bool;
      default = true;
      description = ''
        This option specifies whether to let NixOps provision SSH deployment keys.

        NixOps will by default generate an SSH key, store the private key in its state file,
        and add the public key to the remote host.

        Setting this option to ``false`` will disable this behaviour
        and rely on you to manage your own SSH keys by yourself and to ensure
        that ``ssh`` has access to any keys it requires.
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
      default = [ ];
      description = ''
        Extra options passed to the OpenSSH client verbatim, and are not executed by a shell.
      '';
    };

    deployment.privilegeEscalationCommand = mkOption {
      type = types.listOf types.str;
      default = [ "sudo" "-H" "--" ];
      description = ''
        A command to escalate to root privileges when using SSH as a non-root user.
        This option is ignored if the ``targetUser`` option is set to ``root``.

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
        set to ``false`` using the command line option
        ``--always-activate`` on deployment.

        If this is set to ``false``, activation is done only if
        the new system profile doesn't match the previous one.
      '';
    };

    deployment.owners = mkOption {
      default = [ ];
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
        If set to ``true``, whole closure will be copied using just `nix-copy-closure`.

        If set to ``false``, closure will be copied first using binary substitution.
        Additionally, any missing derivations copied with `nix-copy-closure` will be done
        using ``--gzip`` flag.

        Some backends set this value to ``true``.
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

    # Provide a default hostname and deployment target equal
    # to the attribute name of the machine in the model.
    networking.hostName = lib.mkOverride 900 name;
    deployment.targetHost = mkDefault config.networking.hostName;
    deployment.targetPort = mkDefault (head config.services.openssh.ports);

  };

}
