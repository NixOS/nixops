{ config, pkgs, lib, ... }:

with lib;

let
  keyOptionsType = types.submodule ({ config, name, ... }: {
    options.text = mkOption {
      example = "super secret stuff";
      default = null;
      type = types.nullOr types.str;
      description = ''
        When non-null, this designates the text that the key should contain. So if
        the key name is <replaceable>password</replaceable> and
        <literal>foobar</literal> is set here, the contents of the file
        <filename><replaceable>destDir</replaceable>/<replaceable>password</replaceable></filename>
        will be <literal>foobar</literal>.

        NOTE: Either <literal>text</literal> or <literal>keyFile</literal> have
        to be set.
      '';
    };

    options.keyFile = mkOption {
      default = null;
      type = types.nullOr types.path;
      description = ''
        When non-null, contents of the specified file will be deployed to the
        specified key on the target machine.  If the key name is
        <replaceable>password</replaceable> and <literal>/foo/bar</literal> is set
        here, the contents of the file
        <filename><replaceable>destDir</replaceable>/<replaceable>password</replaceable></filename>
        deployed will be the same as local file <literal>/foo/bar</literal>.

        Since no serialization/deserialization of key contents is involved, there
        are no limits on that content: null bytes, invalid Unicode,
        <literal>/dev/random</literal> output -- anything goes.

        NOTE: Either <literal>text</literal> or <literal>keyFile</literal> have
        to be set.
      '';
    };

    options.destDir = mkOption {
      default = "/run/keys";
      type = types.path;
      description = ''
        When specified, this allows changing the destDir directory of the key
        file from its default value of <filename>/run/keys</filename>.

        This directory will be created, its permissions changed to
        <literal>0750</literal> and ownership to <literal>root:keys</literal>.
      '';
    };

    options.path = mkOption {
      type = types.path;
      default = "${config.destDir}/${name}";
      internal = true;
      description = ''
        Path to the destination of the file, a shortcut to
        <literal>destDir</literal> + / + <literal>name</literal>

        Example: For key named <literal>foo</literal>,
        this option would have the value <literal>/run/keys/foo</literal>.
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
  });

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

        <para>The set of keys to be deployed to the machine.  Each attribute maps
        a key name to a file that can be accessed as
        <filename><replaceable>destDir</replaceable>/<replaceable>name</replaceable></filename>,
        where <literal>destDir</literal> defaults to
        <filename>/run/keys</filename>.  Thus, <literal>{ password.text =
        "foobar"; }</literal> causes a file
        <filename><replaceable>destDir</replaceable>/password</filename> to be
        created with contents <literal>foobar</literal>.  The directory
        <filename><replaceable>destDir</replaceable></filename> is only
        accessible to root and the <literal>keys</literal> group, so keep in mind
        to add any users that need to have access to a particular key to this
        group.</para>

        <para>Each key also gets a systemd service <literal><replaceable>name</replaceable>-key.service</literal>
        which is active while the key is present and inactive while the key
        is absent.  Thus, <literal>{ password.text = "foobar"; }</literal> gets
        a <literal>password-key.service</literal>.</para>
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

    assertions = flip mapAttrsToList config.deployment.keys (key: opts: {
      assertion = (opts.text == null && opts.keyFile != null) ||
                  (opts.text != null && opts.keyFile == null);
      message = "Deployment key '${key}' must have either a 'text' or a 'keyFile' specified.";
    });

    system.activationScripts.nixops-keys = stringAfter [ "users" "groups" ]
      ''
        mkdir -p /run/keys -m 0750
        chown root:keys /run/keys

        ${optionalString config.deployment.storeKeysOnMachine
            (concatStrings (mapAttrsToList
                            (name: value: let
                                            # FIXME: The key file should be marked as private once
                                            # https://github.com/NixOS/nix/issues/8 is fixed.
                                            keyFile = pkgs.writeText name
                                                      (if !isNull value.keyFile
                                                       then builtins.readFile value.keyFile
                                                       else value.text);
                                            destDir = toString value.destDir;
                                          in
                                          ''
                                               if test ! -d ${destDir}
                                               then
                                                   mkdir -p ${destDir} -m 0750
                                                   chown root:keys ${destDir}
                                               fi
                                               ln -sfn ${keyFile} ${destDir}/${name}
                                          '')
                           config.deployment.keys)
            + ''
              # FIXME: delete obsolete keys?
              touch /run/keys/done
            '')
        }

        ${optionalString (!config.deployment.storeKeysOnMachine)
          (concatStringsSep "\n" (flip mapAttrsToList config.deployment.keys (name: value:
            # Make sure each key has correct ownership, since the configured owning
            # user or group may not have existed when first uploaded.
            ''
              [[ -f "${value.path}" ]] && chown '${value.user}:${value.group}' "${value.path}"
            ''
        )))}
      '';

    systemd.services = (
      { nixops-keys =
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
              < <(inotifywait -qm --format '%f' -e create,move ${keyCfg.destDir}) ) &

            if [[ -e "${keyCfg.path}" ]]; then
              echo 'flapped down'
              kill %1
              exit 0
            fi
            wait %1
          '';
          script = ''
            inotifywait -qq -e delete_self "${keyCfg.path}" &

            if [[ ! -e "${keyCfg.path}" ]]; then
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
