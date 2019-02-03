# Dummy module necessary to allow the manual to be generated.  The EC2
# module extends the fileSystems option, so we need a type/description
# for that option.  But providing it in the EC2 module would cause an
# error because multiple definitions of the type/description are not
# allowed.  So this module, which defines them, is included only for
# the generation of the manual.

{ config, lib, ... }:

with lib;

{

  options = {
    fileSystems = mkOption {
      type = with types; loaOf (submodule {});
      description = ''
        NixOps extends NixOS' <option>fileSystem</option> option to
        allow convenient attaching of EC2 volumes.
      '';
    };
  };

}
