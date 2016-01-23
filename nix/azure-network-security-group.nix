{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
let

  securityRuleOptions = { config, ... }: {
    options = {
      description = mkOption {
        default = "";
        example = "Allow SSH";
        type = types.str;
        description = "A description for this rule. Restricted to 140 characters.";
      };

      protocol = mkOption {
        example = "Udp";
        type = types.enum [ "Tcp" "Udp" "*" ];
        description = "Network protocol this rule applies to. Can be Tcp, Udp or * to match both.";
      };

      sourcePortRange = mkOption {
        example = "22";
        type = types.str;
        description = "Source Port or Range. Integer or range between 0 and 65535 or * to match any.";
      };

      destinationPortRange = mkOption {
        example = "22";
        type = types.str;
        description = "Destination Port or Range. Integer or range between 0 and 65535 or * to match any.";
      };

      sourceAddressPrefix = mkOption {
        example = "Internet";
        type = types.str;
        description = ''
          CIDR or source IP range or * to match any IP.
          Tags such as "VirtualNetwork", "AzureLoadBalancer" and "Internet"
          can also be used.
        '';
      };

      destinationAddressPrefix = mkOption {
        example = "Internet";
        type = types.str;
        description = ''
          CIDR or destination IP range or * to match any IP.
          Tags such as "VirtualNetwork", "AzureLoadBalancer" and "Internet"
          can also be used.
        '';
      };

      access = mkOption {
        example = "Allow";
        type = types.enum [ "Allow" "Deny" ];
        description = ''
          Specifies whether network traffic is allowed or denied.
          Possible values are "Allow" and "Deny".
        '';
      };

      priority = mkOption {
        example = 2000;
        type = types.int;
        description = ''
          Specifies the priority of the rule.
          The value can be between 100 and 4096.
          The priority number must be unique for
          each rule in the collection.
          The lower the priority number,
          the higher the priority of the rule.
        '';
      };

      direction = mkOption {
        example = "Inbound";
        type = types.enum [ "Inbound" "Outbound" ];
        description = ''
          The direction specifies if rule will be evaluated
          on incoming or outgoing traffic.
          Possible values are "Inbound" and "Outbound".
        '';
      };

    };
    config = {};
  };


in
{

  options = (import ./azure-mgmt-credentials.nix lib "network security group") // {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      example = "my-security-group";
      type = types.str;
      description = "Name of the Azure network security group.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = ''
        The name or resource of an Azure resource group
        to create the network security group in.
      '';
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = ''
        The Azure data center location where the
        network security group should be created.
      '';
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the network security group.";
    };

    securityRules = mkOption {
      default = {};
      example = {
        allow-ssh = {
          description = "Allow SSH";
          protocol = "Tcp";
          sourcePortRange = "*";
          destinationPortRange = "22";
          sourceAddressPrefix = "Internet";
          destinationAddressPrefix = "*";
          access = "Allow";
          priority = 2000;
          direction = "Inbound";
        };
      };
      type = types.attrsOf types.optionSet;
      options = securityRuleOptions;
      description = "An attribute set of security rules.";
    };

  };

  config = {
    _type = "azure-network-security-group";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
