{ config, lib, pkgs, uuid, name, ... }:

with lib;
with import ./lib.nix lib;
{

  options = (import ./gce-credentials.nix lib "route") // {

      name = mkOption {
        example = "my-route";
        type = types.str;
        default = "route-${uuid}-${name}";
        description = "Name of the route";
      };

      description = mkOption {
        example = "my-custom-route";
        default = null;
        type = types.nullOr types.str;
        description = "Textual description of the route";
      };

      network = mkOption {
        example = "my-custom-network";
        default = "default";
        type = types.str;
        description = ''
          Name of the network, defaults to <literal>default</literal>.
        '';
      };

      destination = mkOption {
        example = "1.1.1.1/32";
        type = types.nullOr (types.either types.str (resource "machine"));
        apply = x: if x == null || (builtins.isString x) then x else "res-" + x._name;
        description = ''
          The destination IP range that this route applies to. If the
          destination IP of a packet falls in this range, it matches
          this route.
        '';
      };

      priority = mkOption {
        default = 1000;
        example = 800;
        type = types.int;
        description = ''
          Priority is used to break ties when there is more than one
          matching route of maximum length.
        '';
      };

      nextHop = mkOption {
        default = null;
        example = "NAT-gateway";
        type = types.nullOr (types.either types.str (resource "machine"));
        apply = x: if x == null || (builtins.isString x) then x else "res-" + x._name;
        description = ''
          Next traffic hop, Leave it empty for the default internet gateway.
        '';
      };

      tags = mkOption {
        default = null;
        type = types.nullOr (types.listOf types.str);
        description = ''
          The route applies to all instances with any of these tags,
          or to all instances in the network if no tags are specified
        '';
      };
    };

  config = {
    _type = "gce-route";
  };

}
