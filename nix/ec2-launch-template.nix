{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the launch template.";
    };

    description = mkOption {
      default = "";
      type = types.str;
      description = "The description of the launch template";
    };

    VersionDescription = mkOption {
      default = "";
      type = types.str;
      description = "A description for the version of the launch template";
    };
    
    LaunchTemplateData = mkOption {
      type = types.str;
      description = ''
        The launch template definition.
        <para>
        See aws launch template documentation for more details
        <link xlink:href='https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.create_launch_template'/>
        </para>
        '';.
    };
  }

  config._type = "launchTemplate";
}