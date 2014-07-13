{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);

let

  gceFirewallOptions = { config, ... }: {

    options = {

      sourceRanges = mkOption {
        default = null;
        example = [ "192.168.0.0/16" ];
        type = types.nullOr (types.listOf types.str);
        description = ''
          The address blocks that this rule applies to, expressed in
          <link xlink:href="http://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing">CIDR</link>
          format. An inbound connection is allowed if either the range or the tag of the
          source matches the <option>sourceRanges</option> or <option>sourceTags</option>.
          As a convenience, leaving this option unset is equivalent to setting it to [ "0.0.0.0/0" ].
        '';
      };

      sourceTags = mkOption {
        default = [];
        example = [ "admin" ];
        type = types.listOf types.str;
        description = ''
          A list of instance tags which this rule applies to. Can be set in addition to
          <option>sourceRanges</option>.
          An inbound connection is allowed if either the range or the tag of the
          source matches the <option>sourceRanges</option> or <option>sourceTags</option>.

          Don't forget to set <option>sourceRanges</option> to [] or at least a more
          restrictive range because the default setting makes <option>sourceTags</option>
          irrelevant.
        '';
      };

      targetTags = mkOption {
        default = [];
        example = [ "public-http" ];
        type = types.listOf types.str;
        description = ''
          A list of instance tags indicating sets of instances located on the network which
          may make network connections as specified in <option>allowed</option>. If no
          <option>targetTags</option> are specified, the firewall rule applies to all
          instances on the network.
        '';
      };

      allowed = mkOption {
        #default = {};
        example = { tcp = [ 80 ]; icmp = null; };
        type = types.attrsOf (types.nullOr (types.listOf (union types.str types.int) ));
        description = ''
          Allowed protocols and ports. Setting protocol to null for example "icmp = null"
          allows all connections made using the protocol to proceed.";
        '';
      };

    };

    config = {};

  };

in
{

  options = (import ./gce-credentials.nix pkgs "network") // {

    name = mkOption {
      example = "my-custom-network";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the GCE Network. This is the <literal>Name</literal> tag of the network.";
    };

    addressRange = mkOption {
      example = "192.168.0.0/16";
      type = types.str;
      description = ''
        The range of internal addresses that are legal on this network.
        This range is a <link xlink:href="http://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing">CIDR</link>
        specification.
      '';
    };

    firewall = mkOption {
        default = {
          allow-ssh.allowed.tcp = [ 22 ];
        };
        example = {
          allow-http = {
            sourceRanges =  ["0.0.0.0/0"];
            allowed.tcp = [ 80 ];
          };
        };
        type = types.attrsOf types.optionSet;
        options = gceFirewallOptions;
        description = ''
          Firewall rules.
        '';
      };

  };

  config = {
    _type = "gce-network";
    firewall.allow-ssh.allowed.tcp = [ 22 ];
  };

}
