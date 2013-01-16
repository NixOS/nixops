# Module to automatically create LUKS-encrypted devices.

{ config, pkgs, utils, ... }:

with pkgs.lib;
with utils;

{

  ###### interface

  options = {

    deployment.autoLuks = mkOption {
      default = { };
      example = { secretdisk = { device = "/dev/xvdf"; passphrase = "foobar"; }; };
      type = types.attrsOf types.optionSet;
      description = ''
        The LUKS volumes to be created.  The name of each attribute
        set specifies the name of the LUKS volume; thus, the resulting
        device will be named
        <filename>/dev/mapper/<replaceable>name</replaceable></filename>.
      '';

      options.device = mkOption {
        example = "/dev/xvdg";
        type = types.uniq types.string;
        description = ''
          The underlying (encrypted) device.
        '';
      };

      options.cipher = mkOption {
        default = "aes-cbc-essiv:sha256";
        type = types.uniq types.string;
        description = ''
          The cipher used to encrypt the volume.
        '';
      };

      options.keySize = mkOption {
        default = 128;
        type = types.uniq types.int;
        description = ''
          The size in bits of the encryption key.
        '';
      };

      options.passphrase = mkOption {
        default = "";
        type = types.uniq types.string;
        description = ''
          The passphrase (key file) used to decrypt the key to access
          the volume.  If left empty, a passphrase is generated
          automatically; this passphrase is lost when you destroy the
          machine or underlying device, unless you copy it from
          Charon's state file.  Note that unless
          <option>deployment.storeKeysOnMachine</option> is set to
          <literal>false</literal>, the passphrase is stored in the
          Nix store of the instance, so an attacker who gains access
          to the disk containing the store can subsequently decrypt
          the encrypted volume.
        '';
      };

      options.autoFormat = mkOption {
        default = false;
        type = types.bool;
        description = ''
          If the underlying device does not currently contain a
          filesystem (as determined by <command>blkid</command>, then
          automatically initialise it using <command>cryptsetup
          luksFormat</command>.
        '';
      };

    };

  };


  ###### implementation

  config = {

    systemd.services =
      let

        luksFormat = name: attrs:
          let
            device' = escapeSystemdPath attrs.device + ".device";

            mapperDevice = "/dev/mapper/${name}";
            mapperDevice' = escapeSystemdPath mapperDevice;
            mapperDevice'' = mapperDevice' + ".device";

            keyFile = "/run/keys/luks-${name}";

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
      (name: attrs: nameValuePair "luks-${name}" attrs.passphrase)
      config.deployment.autoLuks;

  };

}
