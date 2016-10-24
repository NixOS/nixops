{ config, lib, uuid, name, ... }:

with lib;

{
  options = {

        apiKey = mkOption {
            default = "";
            type = types.str;
            description = "The Datadog API Key.";
        };
        appKey = mkOption {
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
        monitorOptions = mkOption {
          type = types.str;
          description = "A dictionary of options for the monitor.";
        };
        silenced = mkOption {
          default = null;
          type = types.nullOr (types.str);
          description = "dictionary of scopes to timestamps or None.
           Each scope will be muted until the given POSIX timestamp or forever if the value is None.";
        };
  };
  config._type = "datadog-monitor";
}
