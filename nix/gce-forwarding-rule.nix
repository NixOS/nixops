{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
let
  resource = type: mkOptionType {
    name = "resource of type ‘${type}’";
    check = x: x._type or "" == type;
    merge = mergeOneOption;
  };

  # FIXME: move to nixpkgs/lib/types.nix.
  union = t1: t2: mkOptionType {
    name = "${t1.name} or ${t2.name}";
    check = x: t1.check x || t2.check x;
    merge = mergeOneOption;
  };
in
{

  options = (import ./gce-credentials.nix pkgs "forwarding rule") // {

    name = mkOption {
      example = "my-public-ip";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the GCE Forwarding Rule. This is the <literal>Name</literal> tag of the rule.";
    };

    region = mkOption {
      example = "europe-west1";
      type = types.str;
      description = "The GCE region to which the forwarding rule should belong.";
    };

    ipAddress = mkOption {
      default = null;
      example = "resources.gceStaticIPs.exampleIP";
      type = types.nullOr ( union types.str (resource "gce-static-ip") );
      description = ''
        GCE Static IP address resource to bind to or the name of
        an IP address not managed by NixOps. If left unset,
        an ephemeral(random) IP address will be assigned on deployment.
      '';
    };

    protocol = mkOption {
      example = "TCP";
      type = types.addCheck types.str
            (v: elem v [ "AH" "ESP" "SCTP" "TCP" "UDP" ]);
      description = ''
        The IP protocol to which this rule applies.

        Acceptable values are:
          "AH": Specifies the IP Authentication Header protocol.
          "ESP": Specifies the IP Encapsulating Security Payload protocol.
          "SCTP": Specifies the Stream Control Transmission Protocol.
          "TCP": Specifies the Transmission Control Protocol.
          "UDP": Specifies the User Datagram Protocol.
      '';
    };

    targetPool = mkOption {
      example = "resources.gceStaticIPs.exampleIP";
      type = union types.str (resource "gce-target-pool");
      description = ''
        GCE Target Pool resource to receive the matched traffic
        or the name of a target pool not managed by NixOps.
      '';
    };

    portRange = mkOption {
      default = null;
      example = "1-1000";
      type = types.nullOr types.str;
      description = ''
        If protocol is TCP or UDP, packets addressed to ports
        in the specified range will be forwarded to the target.

        Leave unset to forward all ports.
      '';
    };

    description = mkOption {
      default = null;
      example = "load balancer for the public site";
      type = types.nullOr types.str;
      description = "An optional textual description of the Fowarding Rule.";
    };

  };

  config._type = "gce-forwarding-rule";

}
