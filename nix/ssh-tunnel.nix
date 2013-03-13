{ config, pkgs, ... }:

with pkgs.lib;

{

  ###### interface

  options = {

    networking.p2pTunnels = mkOption {
      default = { };
      example =
        { tunnel1 =
            { target = "192.0.2.1";
              privateKey = "/root/.ssh/id_vpn";
              localTunnel = 0;
              remoteTunnel = 1;
              localIPv4 = "172.16.12.1";
              remoteIPv4 = "172.16.12.2";
            };
        };
      type = types.attrsOf types.optionSet;
      options = {
        target = mkOption {
          type = types.uniq types.string;
          description = "Host name or IP address of the remote machine.";
        };
        privateKey = mkOption {
          type = types.uniq types.path;
          description = "Path to the private key file used to connect to the remote machine.";
        };
        localTunnel = mkOption {
          type = types.uniq types.int;
          description = "Local tunnel device number.";
        };
        remoteTunnel = mkOption {
          type = types.uniq types.int;
          description = "Remote tunnel device number.";
        };
        localIPv4 = mkOption {
          type = types.uniq types.string;
          description = "IPv4 address of the local endpoint of the tunnel.";
        };
        remoteIPv4 = mkOption {
          type = types.uniq types.string;
          description = "IPv4 address of the remote endpoint of the tunnel.";
        };
      };
      description = ''
        A set of peer-to-peer tunnels set up automatically over SSH.
      '';
    };

  };


  ###### implementation

  config = {

    # Convenience target to stop/start all tunnels.
    systemd.targets.encrypted-links =
      { description = "All Encrypted Links";
        wantedBy = [ "network.target" ];
      };

    jobs = flip mapAttrs' config.networking.p2pTunnels (n: v: nameValuePair "ssh-tunnel-${n}" {
      wantedBy = [ "multi-user.target" "encrypted-links.target" ];
      partOf = [ "encrypted-links.target" ];
      startOn = "started network-interfaces";
      stopOn = "stopping network-interfaces";
      path = [ pkgs.nettools pkgs.openssh ];
      preStart = "sleep 1"; # FIXME: hack to work around Upstart
      # FIXME: ensure that the remote tunnel device is free
      exec =
        "ssh -i ${v.privateKey} -x"
        + " -o StrictHostKeyChecking=no -o PermitLocalCommand=yes -o ServerAliveInterval=20"
        + " -o LocalCommand='ifconfig tun${toString v.localTunnel} ${v.localIPv4} pointopoint ${v.remoteIPv4} netmask 255.255.255.255; route add ${v.remoteIPv4}/32 dev tun${toString v.localTunnel}'"
        + " -w ${toString v.localTunnel}:${toString v.remoteTunnel} ${v.target}"
        + " 'ifconfig tun${toString v.remoteTunnel} ${v.remoteIPv4} pointopoint ${v.localIPv4} netmask 255.255.255.255; route add ${v.localIPv4}/32 dev tun${toString v.remoteTunnel}'";
    });

  };

}
