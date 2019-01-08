{ config, pkgs, lib, ... }:

with lib;

{

  ###### interface

  options = {

    networking.p2pTunnels.ssh = mkOption {
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
      type = with types; attrsOf (submodule {
        options = {
          target = mkOption {
            type = types.str;
            description = "Host name or IP address of the remote machine.";
          };
          targetPort = mkOption {
            type = types.int;
            description = "Port number that SSH listens to on the remote machine.";
          };
          privateKey = mkOption {
            type = types.path;
            description = "Path to the private key file used to connect to the remote machine.";
          };
          localTunnel = mkOption {
            type = types.int;
            description = "Local tunnel device number.";
          };
          remoteTunnel = mkOption {
            type = types.int;
            description = "Remote tunnel device number.";
          };
          localIPv4 = mkOption {
            type = types.str;
            description = "IPv4 address of the local endpoint of the tunnel.";
          };
          remoteIPv4 = mkOption {
            type = types.str;
            description = "IPv4 address of the remote endpoint of the tunnel.";
          };
        };
      });
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

    systemd.services = flip mapAttrs' config.networking.p2pTunnels.ssh (n: v: nameValuePair "ssh-tunnel-${n}" {
      wantedBy = [ "multi-user.target" "encrypted-links.target" ];
      partOf = [ "encrypted-links.target" ];
      after = [ "network-interfaces.target" ];
      path = [ pkgs.iproute pkgs.openssh ];
      # FIXME: ensure that the remote tunnel device is free

      script = let
        mkAddrConf = tun: localIP: remoteIP: concatStringsSep " && " [
          "ip addr add ${localIP}/32 peer ${remoteIP} dev tun${toString tun}"
          "ip link set tun${toString tun} up"
        ];

        localCommand = mkAddrConf v.localTunnel v.localIPv4 v.remoteIPv4;
        remoteCommand = mkAddrConf v.remoteTunnel v.remoteIPv4 v.localIPv4;

      in "ssh -i ${v.privateKey} -x"
       + " -o StrictHostKeyChecking=accept-new"
       + " -o PermitLocalCommand=yes"
       + " -o ServerAliveInterval=20"
       + " -o LocalCommand='${localCommand}'"
       + " -w ${toString v.localTunnel}:${toString v.remoteTunnel}"
       + " ${v.target} -p ${toString v.targetPort}"
       + " '${remoteCommand}'";

      serviceConfig =
        { Restart = "always";
          RestartSec = 20;
        };
    });

  };

}
