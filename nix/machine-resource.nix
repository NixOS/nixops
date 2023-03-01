
# Machine resource

{ config, lib, uuid, name, ... }:

with lib;

{
  # A freeformType is probably not helpful because it may traverse into a
  # machine config, triggering errors in attributes that should never be accessed,
  # which results in very obscure errors.
  # freeformType = lib.types.raw or lib.types.unspecified;
  options = {

  };
}
