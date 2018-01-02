{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the DHCP options set.";
    };
    
    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC used to associate the DHCP options to.
      '';
    };

    domainNameServers = mkOption {
      default = null;
      type = types.nullOr (types.listOf types.str);
      description = ''
        The IP addresses of up to 4 domain name servers, or AmazonProvidedDNS. 
      '';
    };

    domainName = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        If you're using AmazonProvidedDNS in us-east-1, specify ec2.internal.
        If you're using another region specify region.compute.internal (e.g 
        ap-northeast-1.compute.internal). Otherwise specify a domain name e.g
        MyCompany.com. This value is used to complete unqualified DNS hostnames.
      '';
    };

    ntpServers = mkOption {
      default = null;
      type = types.nullOr (types.listOf types.str);
      description = ''
        The IP addresses of up to 4 Network Time Protocol (NTP) servers. 
      '';
    };

    netbiosNameServers = mkOption {
      default = null;
      type = types.nullOr (types.listOf types.str);
      description = ''
        The IP addresses of up to 4 NetBIOS name servers. 
      '';
    };

    netbiosNodeType = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = ''
        The NetBIOS node type (1,2,4 or 8).
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; };
}
