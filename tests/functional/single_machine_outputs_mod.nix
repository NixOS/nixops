let 
  lib = (import <nixpkgs>{}).lib;
in
{
  resources = {
    output.thing = {
      script = lib.mkForce ''
        #!/bin/sh
        echo -n '"123456"'
      '';
    };
  };
}
