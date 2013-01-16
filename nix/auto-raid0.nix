# Module to automatically combine devices into a RAID-0 volume
# (actually an LVM logical volume).

{ config, pkgs, utils, ... }:

with pkgs.lib;
with utils;

{

  ###### interface

  options = {

    deployment.autoRaid0 = mkOption {
      default = { };
      example = { bigdisk.devices = [ "/dev/xvdg" "/dev/xvdh" ]; };
      type = types.attrsOf types.optionSet;
      description = ''
        The RAID-0 volumes to be created.  The name of each attribute
        set specifies the name of both the volume group and the
        logical volume; thus, the resulting device will be named
        <filename>/dev/<replaceable>name</replaceable>/<replaceable>name</replaceable></filename>.
      '';

      options.devices = mkOption {
        example = [ "/dev/xvdg" "/dev/xvdh" ];
        type = types.list types.string;
        description = "The underlying devices to be combined into a RAID-0 volume.";
      };

    };

  };


  ###### implementation

  config = {

    systemd.services =
      let

        createRaid0 = name: attrs:
          let
            devices' = map (d: escapeSystemdPath d + ".device") attrs.devices;
            mapperDevice = "/dev/${name}/${name}";
            mapperDevice' = escapeSystemdPath mapperDevice;
            mapperDevice'' = mapperDevice' + ".device";
            vg = name;
          in nameValuePair "create-raid0-${name}"
          { description = "Creation of RAID-0 Volume ${mapperDevice}";
            wantedBy = [ mapperDevice'' ];
            before = [ mapperDevice'' "mkfs-${mapperDevice'}.service" ];
            requires = devices';
            after = devices';
            path = [ pkgs.utillinux pkgs.lvm2 ];
            unitConfig.DefaultDependencies = false; # needed to prevent a cycle
            serviceConfig.Type = "oneshot";
            script =
              ''
                # First, run pvcreate on the underlying devices.
                ${concatMapStrings (dev: ''
                  [ -e "${dev}" ]
                  type=$(blkid -p -s TYPE -o value "${dev}") || res=$?
                  if [ "$type" = LVM2_member ]; then
                    echo "skipping previously initialised physical volume ${dev}"
                  elif [ -z "$type" -a \( -z "$res" -o "$res" = 2 \) ]; then
                    echo "initialising physical volume ${dev}..."
                    pvcreate "${dev}"
                  else
                    echo "refusing to initialise non-empty physical volume ${dev}!"
                    exit 1
                  fi
                '') attrs.devices}

                # Second, create the volume group.
                if vgs "${vg}"; then
                  echo "volume group ${vg} already exists"
                  # FIXME: add new physical volumes to the volume group.
                else
                  echo "creating volume group ${vg}..."
                  vgcreate "${vg}" ${toString attrs.devices}
                fi

                # Third, create the logical volume.
                if lvs "${vg}" | grep -q "${vg}"; then
                  echo "logical volume ${vg} already exists"
                  # FIXME: resize the logical volume.
                else
                  echo "creating logical volume ${vg}..."
                  lvcreate "${vg}" --name "${name}" --extents '100%FREE' \
                    --stripes ${toString (length attrs.devices)}
                fi

                vgchange -ay "${vg}"

                if ! [ -e "${mapperDevice}" ]; then
                  echo "device ${mapperDevice} did not appear!"
                  exit 1
                fi
              '';
          };

      in mapAttrs' createRaid0 config.deployment.autoRaid0;

  };

}
