let 
  lib = (import <nixpkgs>{}).lib;
in
{
  resources = {
    commandOutput.thing = {
      script = lib.mkForce ''
        #!/bin/sh
        echo -n '"123456"'
      '';
    };
  };
}
