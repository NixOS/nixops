{
  machine =
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1";
      deployment.ec2.instanceType = "m1.small";
      deployment.ec2.ebsBoot = true;
      
      fileSystems =
        [ # Mount a 1 GiB EBS volume on /data.  It's created and
          # formatted when the machine is deployed, and destroyed when
          # the machine is destroyed.
          { mountPoint = "/data";
            autocreate = true;
            autoFormat = true;
            fsType = "btrfs"; # default is "ext4"
            device = "/dev/mapper/xvdf";
            ec2.size = 1;
            ec2.encrypt = true;
            ec2.passphrase = "fubar";
          }

          # Or to mount an existing volume or snapshot:
          /*
          { mountPoint = "/data2";
            autocreate = true;
            device = "/dev/xvdg";
            ec2.disk = "snap-b82666d1"; # or "vol-5aa77f32"
          }
          */
        ];
    };
}
