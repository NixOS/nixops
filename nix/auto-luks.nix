# Module to automatically create LUKS-encrypted devices.

{ config, lib, pkgs, utils, ... }:

with lib;
with utils;

{

  ###### interface

  options = {

    deployment.autoLuks = mkOption {
      default = { };
      example = { secretdisk = { device = "/dev/xvdf"; passphrase = "foobar"; }; };
      type = with types; attrsOf (submodule {
        options = {
          device = mkOption {
            example = "/dev/xvdg";
            type = types.str;
            description = ''
              The underlying (encrypted) device.
            '';
          };

          cipher = mkOption {
            default = "aes-cbc-essiv:sha256";
            type = types.str;
            description = ''
              The cipher used to encrypt the volume.
            '';
          };

          keySize = mkOption {
            default = 128;
            type = types.int;
            description = ''
              The size in bits of the encryption key.
            '';
          };

          passphrase = mkOption {
            default = "";
            type = types.str;
            description = ''
              The passphrase (key file) used to decrypt the key to access
              the volume.  If left empty, a passphrase is generated
              automatically; this passphrase is lost when you destroy the
              machine or underlying device, unless you copy it from
              NixOps's state file.  Note that unless
              <option>deployment.storeKeysOnMachine</option> is set to
              <literal>false</literal>, the passphrase is stored in the
              Nix store of the instance, so an attacker who gains access
              to the disk containing the store can subsequently decrypt
              the encrypted volume.
            '';
          };

          autoFormat = mkOption {
            default = false;
            type = types.bool;
            description = ''
              If the underlying device does not currently contain a
              filesystem (as determined by <command>blkid</command>, then
              automatically initialise it using <command>cryptsetup
              luksFormat</command>.
            '';
          };

          mountPoint = mkOption {
            type = types.either (types.enum ["none"]) types.str;
            description = ''
              This option is required so the autoLuks module knows where the
              device will be mounted at.  With this option we inject the
              required <literal>_netdev</literal> mount option. Without the
              mount option the <literal>local-fs.target</literal> would fail.

              Set to the path used in the corresponding
              <literal>fileSystems.<replaceable>path</replaceable></literal>
              option or to <literal>null</literal> if you know what you are doing.

              If you do not use the device on a mount point pass <literal>none</literal>.

              WARNING: failing to provide the correct value here might render
              the system unbootable.
            '';
          };
        };
      });
      description = ''
        The LUKS volumes to be created.  The name of each attribute
        set specifies the name of the LUKS volume; thus, the resulting
        device will be named
        <filename>/dev/mapper/<replaceable>name</replaceable></filename>.
      '';


    };

  };


  ###### implementation

  config = {

    fileSystems =
      let
        mkFileSystemEntry = _: attrs: nameValuePair attrs.mountPoint { options = [ "_netdev" ]; };
      in mapAttrs' mkFileSystemEntry
          (filterAttrs (_: attrs: attrs.mountPoint != "none") config.deployment.autoLuks);

    systemd.services =
      let

        luksFormat = name: attrs:
          let
            device' = escapeSystemdPath attrs.device + ".device";

            mapperDevice = "/dev/mapper/${name}";
            mapperDevice' = escapeSystemdPath mapperDevice;
            mapperDevice'' = mapperDevice' + ".device";

            keyFile = config.deployment.keys."luks-${name}".path;

          in assert attrs.passphrase != ""; nameValuePair "cryptsetup-${name}"

          { description = "Cryptographic Setup of Device ${mapperDevice}";
            wantedBy = [ mapperDevice'' ];
            before = [ mapperDevice'' "mkfs-${mapperDevice'}.service" ];
            requires = [ device' "keys.target" ];
            after = [ device' "keys.target" ];
            path = [ pkgs.cryptsetup pkgs.utillinux ];
            unitConfig.DefaultDependencies = false; # needed to prevent a cycle
            serviceConfig.Type = "oneshot";
            script =
              ''
                # Do LUKS formatting if the device is empty.
                ${optionalString attrs.autoFormat ''
                  [ -e "${attrs.device}" ]
                  type=$(blkid -p -s TYPE -o value "${attrs.device}") || res=$?
                  if [ -z "$type" -a \( -z "$res" -o "$res" = 2 \) ]; then
                    echo "initialising encryption on device ‘${attrs.device}’..."
                    cryptsetup luksFormat "${attrs.device}" --key-file=${keyFile} \
                      --cipher ${attrs.cipher} --key-size ${toString attrs.keySize}
                  fi
                ''}

                # Activate the LUKS device.
                if [ ! -e "${mapperDevice}" ]; then
                  cryptsetup luksOpen "${attrs.device}" "${name}" --key-file=${keyFile}
                fi
              '';
          };

      in mapAttrs' luksFormat config.deployment.autoLuks;

    deployment.keys = mapAttrs'
      (name: attrs: nameValuePair "luks-${name}" { text = attrs.passphrase; } )
      config.deployment.autoLuks;

  };

}
