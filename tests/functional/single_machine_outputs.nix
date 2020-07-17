{
  network = {};
  resources = {
    commandOutput.thing = {
      script = ''
        #!/bin/sh
        echo -n '"12345"'
      '';
    };
  };
  machine = {resources, pkgs, ...} : {
    deployment.targetEnv = "none";
    environment.etc."test.txt".text = resources.commandOutput.thing.value;
  };
}
