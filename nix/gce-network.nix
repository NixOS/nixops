{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

let

  # FIXME: move to nixpkgs/lib/types.nix.
  union = t1: t2: mkOptionType {
    name = "${t1.name} or ${t2.name}";
    check = x: t1.check x || t2.check x;
    merge = mergeOneOption;
  };

  gceFirewallOptions = { config, ... }: {

    options = {

      sourceRanges = mkOption {
        default = [];
        example = [ "192.168.0.0/16" ];
        type = types.listOf types.str;
        description = ''
          The address blocks that this rule applies to, expressed in
          <link xlink:href="http://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing">CIDR</link>
          format. An inbound connection is allowed if either the range or the tag of the
          source matches the <option>sourceRanges</option> or <option>sourceTags</option>.
          Leaving this list empty is equivalent to setting it to [ "0.0.0.0/0" ];
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

  options = {

    name = mkOption {
      example = "My Custom Network";
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
          allow-ssh = {
            sourceRanges =  ["0.0.0.0/0"];
            allowed.tcp = [ 22 ];
          };
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

    serviceAccount = mkOption {
      default = "";
      example = "12345-asdf@developer.gserviceaccount.com";
      type = types.str;
      description = ''
        The GCE Service Account Email. If left empty, it defaults to the
        contents of the environment variable <envar>GCE_SERVICE_ACCOUNT</envar>.
      '';
    };

    accessKey = mkOption {
      default = "";
      example = "/path/to/secret/key.pem";
      type = types.str;
      description = ''
        The path to GCE Service Account key. If left empty, it defaults to the
        contents of the environment variable <envar>ACCESS_KEY_PATH</envar>.
      '';
    };

    project = mkOption {
      default = "";
      example = "myproject";
      type = types.str;
      description = ''
        The GCE project which should own the network. If left empty, it defaults to the
        contents of the environment variable <envar>GCE_PROJECT</envar>.
      '';
    };

  };

  config._type = "gce-network";

}
