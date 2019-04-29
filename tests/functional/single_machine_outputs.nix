{
  resources = {
    commandOutput.thing = {
      script = ''
        #!/bin/sh
        echo -n '"12345"'
      '';
    };
  };
  machine = {resources, pkgs, ...} : {
    imports = [ <nixpkgs/nixos/modules/profiles/minimal.nix> ];
    environment.etc."test.txt".text = resources.commandOutput.thing.value;
  };
}
