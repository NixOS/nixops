{
  systemd.targets = {
    deploy-prepare = {
      description = "Started immediately before switch-to-configuration.";
      unitConfig = {
        Conflicts = [ "deploy-healthy.target" "deploy-complete.target" ];
        X-StopOnReconfiguration = true;
      };
    };

    deploy-healthy = {
      description = "Started after confirming switch-to-configuration was successful.";
      unitConfig = {
        Conflicts = [ "deploy-prepare.target" ];
        X-StopOnReconfiguration = true;
      };
    };

    deploy-complete = {
      description = "Started after confirming switch-to-configuration was successful on the entire deployment.";
      unitConfig = {
        Conflicts = [ "deploy-prepare.target" ];
        X-StopOnReconfiguration = true;
      };
    };

  };
}
