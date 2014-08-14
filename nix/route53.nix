# Configuration specific to the Amazon Route 53 service.

{ config, pkgs, lib ? pkgs.lib, ... }:

with lib;

{

  ###### interface

  options = {

    deployment.route53.accessKeyId = mkOption {
      default = "";
      example = "AKIAIEMEJZVMPOHZWKZQ";
      type = types.str;
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key.  If it does not appear in that file, the
        environment variables environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    deployment.route53.hostName = mkOption {
      default = "";
      example = "test.x.logicblox.com";
      type = types.str;
      description = ''
        The DNS hostname to bind the public IP address to.
      '';
    };

    deployment.route53.ttl = mkOption {
      default = 300;
      example = 300;
      type = types.int;
      description = ''
        The time to live (TTL) for the A record created for the
        specified DNS hostname.
      '';
    };

  };


  ###### implementation

  config = mkIf (config.deployment.targetEnv == "ec2") {};

}
