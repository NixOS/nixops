{ config, pkgs, ... }:

with pkgs.lib;

let
  keyOptionsType = types.submodule {
    options.text = mkOption {
      example = "super secret stuff";
      type = types.str;
      description = ''
        The text the key should contain. So if the key name is
        <replaceable>password</replaceable> and <literal>foobar</literal>
        is set here, the contents of the file
        <filename>/run/keys/<replaceable>password</replaceable></filename>
        will be <literal>foobar</literal>.
      '';
    };

    options.user = mkOption {
      default = "root";
      type = types.str;
      description = ''
        The user which will be the owner of the key file.
      '';
    };

    options.group = mkOption {
      default = "root";
      type = types.str;
      description = ''
        The group that will be set for the key file.
      '';
    };

    options.permissions = mkOption {
      default = "0600";
      example = "0640";
      type = types.str;
      description = ''
        The default permissions to set for the key file, needs to be in the
        format accepted by <citerefentry><refentrytitle>chmod</refentrytitle>
        <manvolnum>1</manvolnum></citerefentry>.
      '';
    };
  };

  keyType = mkOptionType {
    name = "string or key options";
    check = v: isString v || keyOptionsType.check v;
    inherit (keyOptionsType) merge getSubOptions;
  };

in

{

  ###### interface

  options = {

    deployment.storeKeysOnMachine = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If true (default), secret information such as LUKS encryption
        keys or SSL private keys is stored on the root disk of the
        machine, allowing the machine to do unattended reboots.  If
        false, secrets are not stored; NixOps supplies them to the
        machine at mount time.  This means that a reboot will not
        complete entirely until you run <command>nixops
        deploy</command> or <command>nixops send-keys</command>.
      '';
    };

    deployment.keys = mkOption {
      default = {};
      example = { password.text = "foobar"; };
      type = types.attrsOf keyType;

      apply = mapAttrs (k: v: let
        warning = "Using plain strings for `deployment.keys' is"
                + " deprecated, please use `deployment.keys.${k}.text ="
                + " \"<value>\"` instead of `deployment.keys.${k} ="
                + " \"<value>\"`.";
      in if isString v then builtins.trace warning { text = v; } else v);

      description = ''
        The set of keys to be deployed to the machine.  Each attribute
        maps a key name to a file that can be accessed as
        <filename>/run/keys/<replaceable>name</replaceable></filename>.
        Thus, <literal>{ password.text = "foobar"; }</literal> causes a
        file <filename>/run/keys/password</filename> to be created
        with contents <literal>foobar</literal>.  The directory
        <filename>/run/keys</filename> is only accessible to root and
        the <literal>keys</literal> group.  So keep in mind to add any
        users that need to have access to a particular key to this group.
      '';
    };

  };


  ###### implementation

  config = {

    system.activationScripts.nixops-keys =
      ''
        mkdir -p /run/keys -m 0750
        chown root:keys /run/keys

        ${optionalString config.deployment.storeKeysOnMachine
            (concatStrings (mapAttrsToList (name: value:
              let
                # FIXME: The key file should be marked as private once
                # https://github.com/NixOS/nix/issues/8 is fixed.
                keyFile = pkgs.writeText name value;
              in "ln -sfn ${keyFile.text} /run/keys/${name}\n")
              config.deployment.keys)
            + ''
              # FIXME: delete obsolete keys?
              touch /run/keys/done
            '')
        }
      '';

    systemd.services.nixops-keys =
      { enable = config.deployment.keys != {};
        description = "Waiting for NixOps Keys";
        wantedBy = [ "keys.target" ];
        before = [ "keys.target" ];
        unitConfig.DefaultDependencies = false; # needed to prevent a cycle
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
        script =
          ''
            while ! [ -e /run/keys/done ]; do
              sleep 0.1
            done
          '';
      };

  };

}
