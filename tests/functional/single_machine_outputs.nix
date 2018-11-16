{
  resources = {
    output.thing = {
      script = ''
        #!/bin/sh
        echo -n '"12345"'
      '';
    };
  };
  machine = {resources, ...} : {
    imports = [ <nixpkgs/nixos/modules/profiles/minimal.nix> ];
    deployment = {
      keys."secret.key".text = resources.output.thing.value;
    };
  };
}
