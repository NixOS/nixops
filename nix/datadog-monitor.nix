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
          default = null;
          type = types.nullOr (types.str);
          description = "a message to include with a re-notification.
          Supports the '@username' notification we allow elsewhere.
          Not applicable if renotify_interval is set.";
        };
        silenced = mkOption {
          default = null;
          type = types.nullOr (types.str);
          description = "dictionary of scopes to timestamps or None.
           Each scope will be muted until the given POSIX timestamp or forever if the value is None.";
        };
        notify_no_data = mkOption {
          default = false;
          type = types.bool;
          description = "a boolean indicating whether this monitor will notify when data stops reporting.";
        };
        no_data_timeframe = mkOption {
          default = null;
          type = types.nullOr (types.int);
          description = "the number of minutes before a monitor will notify when data stops reporting.
           Must be at least 2x the monitor timeframe for metric alerts or 2 minutes for service checks.";
        };
        timeout_h = mkOption {
          default = null;
          type = types.nullOr (types.int);
          description = "the number of hours of the monitor not reporting data before it will automatically resolve from a triggered state.";
        };
        renotify_interval = mkOption {
          default = null;
          type = types.nullOr (types.int);
          description = "the number of minutes after the last notification before a monitor will re-notify on the current status.
          It will only re-notify if it's not resolved.";
        };
        require_full_window = mkOption {
          default = null;
          type = types.nullOr (types.bool);
          description = "a boolean indicating whether this monitor needs a full window of data before it's evaluated.
          We highly recommend you set this to False for sparse metrics, otherwise some evaluations will be skipped.";
        };
        notify_audit = mkOption {
          default = null;
          type = types.nullOr (types.bool);
          description = "a boolean indicating whether tagged users will be notified on changes to this monitor.";
        };
        locked = mkOption {
          default = null;
          type = types.nullOr (types.bool);
          description = "a boolean indicating whether changes to to this monitor should be restricted to the creator or admins.";
        };
        include_tags = mkOption {
          default = null;
          type = types.nullOr (types.bool);
          description = "a boolean indicating whether notifications from this monitor will automatically insert its triggering tags into the title.";
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
  config = {
    renotify_interval = mkIf (builtins.isString config.escalation_message) (throw "renotify_interval can't be used with escalation_message set.");
    _type = "datadog-monitor";
  };
}
