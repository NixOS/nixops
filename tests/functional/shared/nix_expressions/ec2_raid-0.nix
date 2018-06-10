{
  machine = {
    deployment.ec2.blockDeviceMapping."/dev/xvdg".size = 1;
    deployment.ec2.blockDeviceMapping."/dev/xvdh".size = 1;

    deployment.ec2.blockDeviceMapping."/dev/xvdg".deleteOnTermination = true;
    deployment.ec2.blockDeviceMapping."/dev/xvdh".deleteOnTermination = true;

    deployment.autoRaid0.raid.devices = [ "/dev/xvdg" "/dev/xvdh" ];

    fileSystems."/data" = {
      autoFormat = true;
      device = "/dev/raid/raid";
      fsType = "ext4";
    };
  };
}
