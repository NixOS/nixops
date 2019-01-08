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
            description = "The Datadog APP Key.";
        };
        name = mkOption {
          default = "datadog-monitor-${uuid}-${name}";
          type = types.str;
          description = "Name of the alert which will show up in the subject line of the email.";
        };
        type = mkOption {
          type = types.str;
          description = "Type of the datadog resource chosen from: \"metric alert\" \"service check\" \"event alert\".";
        };
        query = mkOption {
          type = types.str;
          description = ''
            The query that defines the monitor.
            <para>
            See the datadog API documentation for more details about query creation
            <link xlink:href='http://docs.datadoghq.com/api/#monitors'/>
            </para>
          '';
        };
        message = mkOption {
          type = types.str;
          description = "Message to send for a set of users.";
        };
        monitorOptions = mkOption {
          type = types.str;
          description = ''
            A dictionary of options for the monitor.
            <para>
            See the API documentation for more details about the available options
            <link xlink:href='http://docs.datadoghq.com/api/#monitors'/>
            </para>
          '';
        };
        silenced = mkOption {
          default = null;
          type = types.nullOr (types.str);
          description = ''
            dictionary of scopes to timestamps or None.
            Each scope will be muted until the given POSIX timestamp or forever if the value is None.
            <para>
            Examples:
            <para>
            To mute the alert completely:
            {'*': None}
            </para>
            <para>
            To mute role:db for a short time:
            {'role:db': 1412798116}
            </para>
            </para>
          '';
        };
        monitorTags = mkOption {
          type = types.listOf types.str;
          default = [];
          description = ''
            A list of tags to associate with your monitor.
          '';
        };
  };
  config._type = "datadog-monitor";
}
