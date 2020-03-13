{
  systemd.targets = {
    deploy-machine-commit = {
      description = "Healthy Deployment";
      unitConfig = {
        OnFailure = [ "deploy-failed.target" ];
        Conflicts = [ "deploy-prepare.target" "deploy-failed.target" ];
        X-StopOnReconfiguration = true;
      };
    };

    deploy-machine-abort = {
      description = "Failed Deployment";
      unitConfig = {
        Conflicts = [ "deploy-prepare.target" ];
        X-StopOnReconfiguration = true;
      };
    };

    deploy-network-commit = {
      description = "Deployment Complete Across All Machines";
      unitConfig = {
        Conflicts = [ "deploy-prepare.target" ];
        X-StopOnReconfiguration = true;
      };
    };

    #                      Why is this last?
    #
    # When deploy-machine-request runs, it is at the _end_ of the
    # lifecycle of the previously deployed system.
    deploy-machine-request = {
      description = "Deployment Requested";
      unitConfig = {
        Conflicts = [ "deploy-healthy.target" "deploy-complete.target" "deploy-failed.target" ];
        X-StopOnReconfiguration = true;
      };
    };
  };
}
