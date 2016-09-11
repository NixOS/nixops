{ config, lib, uuid, name, ... }:

with lib;

{
  options = {

        api_key = mkOption {
            default = "";
            type = types.str;
            description = "The Datadog API Key.";
        };
        app_key = mkOption {
            default = "";
            type = types.str;
            description = "The Datadog App Key.";
        };
         name = mkOption {
          default = "datadog-monitor-${uuid}-${name}";
          type = types.str;
          description = "Name of the datadog resource.";
        };
        type = mkOption {
          type = types.str;
          description = "Type of the datadog resource.";
        };
        query = mkOption {
          type = types.str;
          description = "The query that defines the monitor";
        };
        message = mkOption {
          type = types.str;
          description = "Message to send for a set of users.";
        };
        escalation_message = mkOption {
          type = types.str;
          description = "Re-notification in case the monitor wasn't marked as resolved.";
        };
        thresholds =
        {
            ok = mkOption {
              default = null;
              type = types.nullOr (types.int);
              description = "";
            };
            warning = mkOption {
              default = null;
              type = types.nullOr (types.int);
              description = "";
            };
            critical = mkOption {
              default = null;
              type = types.nullOr (types.int);
              description = "";
            };
          };
        };

  config._type = "datadog-monitor";
}
