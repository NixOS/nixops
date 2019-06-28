
{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    alias = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Alias of the CMK.";
    };

    keyId = mkOption {
      default = "";
      type = types.str;
      description = "The globally unique identifier for the CMK. This is set by NixOps";
    };

    policy = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The key policy to attach to the CMK.
      '';
    };

    description = mkOption {
      default = "CMK created by nixops";
      type = types.str;
      description = "A description of the CMK.";
    };
    
    origin = mkOption {
      default = "AWS_KMS";
      type = types.enum [ "AWS_KMS" "EXTERNAL" "AWS_CLOUDHSM" ];
      description = ''
        The source of the key material for the CMK. You cannot change the origin after you create the CMK.
      ''; 
    };
    
    customKeyStoreId = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        Creates the CMK in the specified custom key store and the key
        material in its associated AWS CloudHSM cluster. To create a CMK
        in a custom key store, you must also specify the Origin parameter
        with a value of "AWS_CLOUDHSM" . 
      '';
    };

    deletionWaitPeriod = mkOption {
      default = 0;
      type = types.int;
      description = ''
        The waiting period, specified in number of days. After
        the waiting period ends, AWS KMS deletes the customer master key (CMK).
        Valid values are between 7 and 30
        Use 0 to indicate that you do not want to delete the key
      '';
    };

    externalKey = mkOption {
      description = "Options related to CMK when the origin is set to external.";
      default = null;
      type = with types; nullOr (submodule {
        options = {
          wrappingAlgorithm = mkOption {
            default = "RSAES_OAEP_SHA_256";
            type = types.enum [ "RSAES_PKCS1_V1_5" "RSAES_OAEP_SHA_1" "RSAES_OAEP_SHA_256" ];
            description = ''
              The algorithm you will use to encrypt the key material before
              importing it with ImportKeyMaterial.
            '';
          };
          wrappingKeySpec = mkOption {
            default = "RSA_2048";
            type = types.enum [ "RSA_2048" ];
            description = ''
              The type of wrapping key (public key) to return in the response.
              Only 2048-bit RSA public keys are supported for the moment.
            '';
          };

          keyMaterialExpire = mkOption {
            default = false;
            type = types.bool;
            description = "Specifies whether the key material expires.";
          };

          keyMaterial = mkOption {
            default = null;
            type = types.nullOr types.str;
            description = ''
              Key material that will be wrapped and uploaded to KMS.
              This is set by nixops
            '';
          };
        };
      });
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "cmk";
}
