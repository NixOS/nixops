{
  machine = {
    deployment.ec2.blockDeviceMapping."/dev/nvme1n1".size = 1;
    deployment.ec2.blockDeviceMapping."/dev/nvme2n1".size = 1;

    deployment.ec2.blockDeviceMapping."/dev/nvme1n1".deleteOnTermination = true;
    deployment.ec2.blockDeviceMapping."/dev/nvme2n1".deleteOnTermination = true;

    deployment.autoRaid0.raid.devices = [ "/dev/nvme1n1" "/dev/nvme2n1" ];

    fileSystems."/data" = {
      autoFormat = true;
      device = "/dev/raid/raid";
      fsType = "ext4";
    };
  };
}
