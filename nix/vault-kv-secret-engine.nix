# only kv2 is supported
{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./vault-common-auth-options.nix ];

  options = {

    name = mkOption {
      default = "vault-kv-secret-${uuid}-${name}";
      type = types.str;
      description = "vault kv2 secret engine name";
    };
    # we can comment this though !!! and hardcode it
    type = mkOption {
      default = "kv";
      type = types.str;
      description = "secret engine type, this should always be se to kv";
    };
    description = mkOption {
      default = "";
      type = types.str;
    };
    local = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Specifies if the secrets engine is a local mount only.
        Local mounts are not replicated nor (if a secondary)
        removed by replication. (this is relevant only for Vault entreprise)
      '';
    };
    sealWrap = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Enable seal wrapping for the mount, causing values 
        stored by the mount to be wrapped by the seal's encryption
        capability. (this is relevant only for Vault entreprise)
      '';
    };
    defaultLeaseTtl = mkOption {
      default = "";
      type = types.str;
      description = ''
        The default lease duration, specified as a string duration
        like "5s" or "30m".
      '';
    };
    maxLeaseTtl = mkOption {
      default = "";
      type = types.str;
      description = ''
        The maximum lease duration, specified as a string duration
        like "5s" or "30m".
      '';
    };
    forceNoCache = mkOption {
      default = false;
      type = types.bool;
      description = "Disable caching";
    };
    auditNonHmacRequestKeys = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        Comma-separated list of keysthat will not be HMAC'd by audit
        devices in the request data object.
      '';
    };
    auditNonHmacResponseKeys = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        Comma-separated list of keys that will not be HMAC'd by audit
        devices in the response data object.
      '';
    };
    listingVisibility = mkOption {
      default = "hidden";
      type = types.enum ["hidden" "unauth"];
      description = ''
        Specifies whether to show this mount in the UI-specific listing
        endpoint. Valid values are "unauth" or "hidden". If not set,
        behaves like "hidden"
      '';
    };
    passthroughRequestHeaders = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        Comma-separated list of headers to whitelist and pass from the
        request to the plugin.
      '';
    };
    allowedResponseHeaders = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        Comma-separated list of headers to whitelist, allowing a plugin
        to include them in the response.
      '';
    };
    # maybe hardcode this as well
    version = mkOption {
      default = 2;
      type = types.int;
      description = ''
        The version of the KV to mount. Set to "2" for mount KV v2.
      '';
    };
    secrets = mkOption {
      description = "List of secrets";
      default = [];
      type = with types; listOf (submodule {
        options = {
          path = mkOption {
            type = types.str;
            description = "The path of the secret in the created secret engine";
          };
          maxVersions = mkOption {
            default = 10;
            type = types.int;
            description = "The number of versions to keep per key.";
          };
          data = mkOption {
            description = "List of key value pairs in the secret path";
            type = with types; listOf (submodule {
              options = {
                key = mkOption {
                  type = types.str;
                  description = "secret key";
                };
                value = mkOption {
                  type = with types; either str (path);
                  description = "secret values";
                };
              };
            });
          };
        };
      });
    };
  };

  config._type = "vault-kv-secret-engine";
}