let

  drbdConf = nodes:
    ''
      global {
        usage-count no;
      }

      resource r0 {
        protocol C;
        syncer {
          verify-alg sha1;
        }
        floating ${nodes.webserver.config.networking.privateIPv4}:7789 {
          device    /dev/drbd1;
          disk      /dev/loop0;
          meta-disk internal;
        }
        floating ${nodes.webserver_failover.config.networking.privateIPv4}:7789 {
          device    /dev/drbd1;
          disk      /dev/loop0;
          meta-disk internal;
        }
      }
    '';

  loopUp = pkgs:
    { name = "loop-up";
      task = true;
      startOn = "mounted MOUNTPOINT=/ephemeral0";
      script = "${pkgs.utillinux}/sbin/losetup /dev/loop0 /ephemeral0/backing && start drbd-up";
    };

in {

  webserver =
    { pkgs, nodes, ... }:
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "m1.large";
      services.drbd.enable = true;
      services.drbd.config = drbdConf nodes;
      jobs.loopUp = loopUp pkgs;
    };

  webserver_failover = 
    { pkgs, nodes, ... }:
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "m1.large";
      services.drbd.enable = true;
      services.drbd.config = drbdConf nodes;
      jobs.loopUp = loopUp pkgs;
    };

}
