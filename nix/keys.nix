{ config, pkgs, ... }:

with pkgs.lib;

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
      example = { password = "foobar"; };
      type = types.attrsOf types.str;
      description = ''
        The set of keys to be deployed to the machine.  Each attribute
        maps a key name to a key string.  On the machine, the key can
        be accessed as
        <filename>/run/keys/<replaceable>name></replaceable></filename>.
        Thus, <literal>{ password = "foobar"; }</literal> causes a
        file <filename>/run/keys/password</filename> to be created
        with contents <literal>foobar</literal>.  The directory
        <filename>/run/keys</filename> is only accessible to root.
      '';
    };

  };


  ###### implementation

  config = {

    system.activationScripts.nixops-keys =
      ''
        mkdir -p /run/keys -m 0700

        ${optionalString config.deployment.storeKeysOnMachine
            (concatStrings (mapAttrsToList (name: value:
              let
                # FIXME: The key file should be marked as private once
                # https://github.com/NixOS/nix/issues/8 is fixed.
                keyFile = pkgs.writeText name value;
              in "ln -sfn ${keyFile} /run/keys/${name}\n")
              config.deployment.keys)
            + ''
              # FIXME: delete obsolete keys?
              touch /run/keys/done
            '')
        }
      '';

    systemd.services.nixops-keys =
      { description = "Waiting for NixOps Keys";
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
