{ config, pkgs, lib, ... }:

with lib;

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

    keyDirOptionsType = types.submodule {
    options.path = mkOption {
      example = "./my-secret-directory/";
      type = types.str;
      description = ''
        The path to the directory that contains keys. May have a trailing slash
        or not. Sub-directories of the path will also be copied. So if the
        keyDir name is <replaceable>dir</replaceable> and
        <literal>/path/to/dir</literal> is set here, the contents of the
        directory <filename>/run/keys/<replaceable>dir</replaceable></filename>
        will be the contents of <literal>/path/to/dir</literal>.
      '';
    };

    options.user = mkOption {
      default = "root";
      type = types.str;
      description = ''
        The user which will be the owner of the key directory.
      '';
    };

    options.group = mkOption {
      default = "root";
      type = types.str;
      description = ''
        The group that will be set for the key directory.
      '';
    };

    options.dirPermissions = mkOption {
      default = "0700";
      example = "0750";
      type = types.str;
      description = ''
        The default permissions to set for the key directory and sub-directories,
        needs to be in the format accepted by <citerefentry><refentrytitle>chmod
        </refentrytitle><manvolnum>1</manvolnum></citerefentry>. Permissions set
        here will not be set for files inside the directory.
      '';
    };
    options.filePermissions = mkOption {
      default = "0600";
      example = "0640";
      type = types.str;
      description = ''
        The default permissions to set for the key files inside the key directory,
        needs to be in the format accepted by <citerefentry><refentrytitle>chmod
        </refentrytitle><manvolnum>1</manvolnum></citerefentry>.
      '';
    };
  };

  convertOldKeyType = key: val: let
    warning = "Using plain strings for `deployment.keys' is"
            + " deprecated, please use `deployment.keys.${key}.text ="
            + " \"<value>\"` instead of `deployment.keys.${key} ="
            + " \"<value>\"`.";
  in if isString val then builtins.trace warning { text = val; } else val;

  keyType = mkOptionType {
    name = "string or key options";
    check = v: isString v || keyOptionsType.check v;
    merge = loc: defs: let
      convert = def: def // {
        value = convertOldKeyType (last loc) def.value;
      };
    in keyOptionsType.merge loc (map convert defs);
    inherit (keyOptionsType) getSubOptions;
  };

  keyDirType = mkOptionType {
    name = "keyDir options";
    check = v: keyDirOptionsType.check v;
    inherit (keyDirOptionsType) merge getSubOptions;
  };

in

{

  ###### interface

  options = {

    deployment.storeKeysOnMachine = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If true, secret information such as LUKS encryption
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
      apply = mapAttrs convertOldKeyType;

      description = ''
        <para>The set of keys to be deployed to the machine.  Each attribute
        maps a key name to a file that can be accessed as
        <filename>/run/keys/<replaceable>name</replaceable></filename>.
        Thus, <literal>{ password.text = "foobar"; }</literal> causes a
        file <filename>/run/keys/password</filename> to be created
        with contents <literal>foobar</literal>.  The directory
        <filename>/run/keys</filename> is only accessible to root and
        the <literal>keys</literal> group, so keep in mind to add any
        users that need to have access to a particular key to this group.</para>

        <para>Each key also gets a systemd service <literal><replaceable>name</replaceable>-key.service</literal>
        which is active while the key is present and inactive while the key
        is absent.  Thus, <literal>{ password.text = "foobar"; }</literal> gets
        a <literal>password-key.service</literal>.</para>
      '';
    };

    deployment.keyDirs = mkOption {
      default = {};
      example = { dir.path = "/foo/bar"; };
      type = types.attrsOf keyDirType;
      description = ''
        The set of key directories to be deployed to the machine. Each attribute maps
        a keyDir name to a directory that can be accessed as
        <filename>/run/keys/<replaceable>name</replaceable></filename>.
        Thus, <literal>{ dir.path = "/foo/bar"; }</literal> causes a directory
        <filename>/run/keys/dir</filename> to be created with contents of
        <literal>/foo/bar</literal>. The directory <filename>/run/keys</filename> is
        only accessible to root and the <literal>keys</literal> group, so keep in mind
        to add any users that need to have access to a particular key to this group.
      '';
    };

  };


  ###### implementation

  config = {

    warnings = mkIf config.deployment.storeKeysOnMachine [(
      "The use of `deployment.storeKeysOnMachine' imposes a security risk " +
      "because all keys will be put in the Nix store and thus are world-" +
      "readable. Also, this will have an impact on services like OpenSSH, " +
      "which require strict permissions to be set on key files, so expect " +
      "things to break."
    )];

    system.activationScripts.nixops-keys = stringAfter [ "users" "groups" ]
      ''
        mkdir -p /run/keys -m 0750
        chown root:keys /run/keys

        ${optionalString config.deployment.storeKeysOnMachine
            (concatStrings (mapAttrsToList (name: value:
              let
                # FIXME: The key file should be marked as private once
                # https://github.com/NixOS/nix/issues/8 is fixed.
                keyFile = pkgs.writeText name value.text;
              in "ln -sfn ${keyFile} /run/keys/${name}\n")
              config.deployment.keys)
            + ''
              # FIXME: delete obsolete keys?
              touch /run/keys/done
            '')
        }

        ${concatStringsSep "\n" (flip mapAttrsToList config.deployment.keys (name: value:
          # Make sure each key has correct ownership, since the configured owning
          # user or group may not have existed when first uploaded.
          ''
            [[ -f "/run/keys/${name}" ]] && chown '${value.user}:${value.group}' "/run/keys/${name}"
          ''
        ))}
      '';

    #Deploying keyDirs is not supported while storeKeysOnMachine is set to true. nixops-keys will listen for 
    #/run/keys/dirs_done only if storeKeysOnMachine is set to false
    systemd.services = (
      { nixops-keys =
        { enable = (config.deployment.keys != {} || (! config.deployment.storeKeysOnMachine && config.deployment.keyDirs != {}));
          description = "Waiting for NixOps Keys";
          wantedBy = [ "keys.target" ];
          before = [ "keys.target" ];
          unitConfig.DefaultDependencies = false; # needed to prevent a cycle
          serviceConfig.Type = "oneshot";
          serviceConfig.RemainAfterExit = true;
          script =
            ''
              ${optionalString (config.deployment.keys != {})
                ''
                  while ! [ -e /run/keys/done ]; do
                    sleep 0.1
                  done
                ''}
              ${optionalString (! config.deployment.storeKeysOnMachine && config.deployment.keyDirs != {})
                ''
                  while ! [ -e /run/keys/dirs_done ]; do
                    sleep 0.1
                  done
                ''}
            '';
        };
      }
      //
      (flip mapAttrs' config.deployment.keys (name: keyCfg:
        nameValuePair "${name}-key" {
          enable = true;
          serviceConfig.TimeoutStartSec = "infinity";
          serviceConfig.Restart = "always";
          serviceConfig.RestartSec = "100ms";
          path = [ pkgs.inotifyTools ];
          preStart = ''
            (while read f; do if [ "$f" = "${name}" ]; then break; fi; done \
              < <(inotifywait -qm --format '%f' -e create /run/keys) ) &

            if [[ -e "/run/keys/${name}" ]]; then
              echo 'flapped down'
              kill %1
              exit 0
            fi
            wait %1
          '';
          script = ''
            inotifywait -qq -e delete_self "/run/keys/${name}" &

            if [[ ! -e "/run/keys/${name}" ]]; then
              echo 'flapped up'
              exit 0
            fi
            wait %1
          '';
        }
      ))
    );

  };

}
