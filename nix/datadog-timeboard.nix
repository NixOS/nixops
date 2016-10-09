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
        title = mkOption {
          type = types.str;
          description = "The title of the timeboard.";
        };
        description = mkOption {
          type = types.str;
          description = "A description of the timeboard's content.";
        };
        graphs = mkOption {
          default = {};
          type = types.listOf types.optionSet;
          description = "A list of graph definitions";
          options = {
            title = mkOption {
              description = "The name of the graph.";
              type = types.str;
            };
            definition = mkOption {
                description = "The graph definition.";
                type = type.str;
            };
          };
        };
        templateVariables = mkOption {
          default = {};
          type = types.listOf types.optionSet;
          description = "A list of template variables for using Dashboard templating.";
          options = {
            name = mkOption {
              type = types.str;
              description = "The name of the variable.";
            };
            prefix = mkOption {
              type = types.str;
              description = "The tag prefix associated with the variable. Only tags with this prefix will appear in the variable dropdown.";
            };
            default = mkOption {
              type = types.str;
              description = "The default value for the template variable on dashboard load";
            };
          };
        };

  config._type = "datadog-timeboard";
}
