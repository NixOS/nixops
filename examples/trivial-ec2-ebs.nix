{
  machine =
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1";
      deployment.ec2.instanceType = "m1.small";
      deployment.ec2.ebsBoot = true;

      # Mount a 1 GiB EBS volume on /data.  It's created and formatted
      # when the machine is deployed, and destroyed when the machine
      # is destroyed.
      fileSystems."/data" =
        { autoFormat = true;
          fsType = "btrfs";
          device = "/dev/xvdf";
          ec2.size = 1;
        };

      # Mount an encrypted 1 GiB volume on /secret.
      fileSystems."/secret" =
        { autoFormat = true;
          fsType = "ext4";
          device = "/dev/mapper/xvdg"; # <-- note you need to use /dev/mapper here
          ec2.size = 1;
          ec2.encrypt = true;
          # You can specify a passphrase (encryption key), or let
          # NixOps generate one.  It's stored on the root volume of
          # the instance, unless you set the option
          # ‘deployment.storeKeysOnMachine’.  In that case, unattended
          # reboots will block until you run the command ‘nixops
          # send-keys’.
          #ec2.passphrase = "fubar";
        };

      # You can attach existing volumes.  These are not deleted
      # automatically.
      #deployment.ec2.blockDeviceMapping."/dev/xvdh".disk = "vol-66568d4b";

      # You can create volumes from snapshots.  These are deleted
      # automatically.
      #deployment.ec2.blockDeviceMapping."/dev/xvdi".disk = "snap-49953c22";

      # You can also specify ephemeral device mappings, but that's
      # rarely useful.
      #deployment.ec2.blockDeviceMapping."/dev/xvdd".disk = "ephemeral0";

      fileSystems."/data-ssd" =
        { autoFormat = true;
          fsType = "ext4";
          device = "/dev/xvdj";
          ec2.size = 1;
          ec2.volumeType = "gp2";
        };
    };
}
