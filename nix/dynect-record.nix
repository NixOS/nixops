{ config, pkgs, lib, uuid, name, ...}:
with lib;
with (import ./lib.nix lib);
let
  aRecordSubModule =
  { options, ... }:
  { options = {
      address = mkOption {
        type = types.str;
        description = "IPv4 Address.";
        example = "127.0.0.1";
      };
    };
  };
in
{
  options = {
    name = mkOption {
      default = "nixops-${uuid}-${name}";
      example = "";
      type = types.str;
      description = "Name of the record";
    };

    fqdn = mkOption {
      type = types.str;
      description = "Name of node where the record will be added.";
      example = "www.example.com";
    };

    zone = mkOption {
      type = types.str;
      description = "Name of zone where the record will be added.";
      example = "example.com";
    };

    ttl = mkOption {
      default = 0;
      example = 3600;
      type = types.int;
      description = "TTL for the record in seconds. Set to 0 to use zone default.";
    };

    aRecord = mkOption {
      default = null;
      type = types.nullOr ( types.submodule ( aRecordSubModule ) );
      example = {
        address = "127.0.0.1";
      };
      description = "aRecord type";
    };
  };

  config._type = "dynect-record";
}
