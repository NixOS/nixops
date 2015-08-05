{ config, lib, pkgs, uuid, name, ... }:

with lib;
with import ./lib.nix lib;

{

  options = (import ./gce-credentials.nix lib "forwarding rule") // {

    name = mkOption {
      example = "my-public-ip";
      default = "n-${shorten_uuid uuid}-${name}";
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
      type = types.nullOr ( types.either types.str (resource "gce-static-ip") );
      description = ''
        GCE Static IP address resource to bind to or the name of
        an IP address not managed by NixOps. If left unset,
        an ephemeral(random) IP address will be assigned on deployment.
      '';
    };

    publicIPv4 = mkOption {
      default = null;
      type = types.uniq (types.nullOr types.str);
      description = ''
        The assigned IP address of this forwarding rule.
        This is set by NixOps to the ephemeral IP address of the resource if
        ipAddress wasn't set, otherwise it should be the same as ipAddress.
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
      type = types.either types.str (resource "gce-target-pool");
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
