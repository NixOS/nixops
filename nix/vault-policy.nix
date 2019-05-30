{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./vault-common-auth-options.nix ];

  options = {

    name = mkOption {
      default = "vault-policy-${uuid}-${name}";
      type = types.str;
      description = "vault policy name";
    };

    policies = mkOption {
      default = [];
      description = "A list of paths and its associated rules";
      type = with types; listOf (submodule {
        options = {
          path = mkOption {
            type = types.str;
            description = ''
              The vault path to apply the rules to.
              Policy paths are matched using the most specific path match.
            '';
            example = ''
              "secret/foo*"
            '';
          };
          capabilities = mkOption {
            default = [ "deny" ];
            type = types.listOf (types.enum [ "create" "read" "update" "delete" "list" "sudo" "deny" ]);
            description = ''
              Provide fine-grained control over permitted (or denied) 
              operations for associated path
            '';
          };
        };
      });
    };
  };

  config._type = "vault-policy";
}
