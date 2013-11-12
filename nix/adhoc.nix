# Ad hoc cloud options.

{ config, pkgs, ... }:

{

  options = {

    deployment.adhoc.controller = mkOption {
      example = "cloud.example.org";
      type = types.str;
      description = ''
        Hostname or IP addres of the machine to which NixOps should
        connect (via SSH) to execute commands to start VMs or query
        their status.
      '';
    };

    deployment.adhoc.createVMCommand = mkOption {
      default = "create-vm";
      type = types.str;
      description = ''
        Remote command to create a NixOS virtual machine.  It should
        print an identifier denoting the VM on standard output.
      '';
    };

    deployment.adhoc.destroyVMCommand = mkOption {
      default = "destroy-vm";
      type = types.str;
      description = ''
        Remote command to destroy a previously created NixOS virtual
        machine.
      '';
    };

    deployment.adhoc.queryVMCommand = mkOption {
      default = "query-vm";
      type = types.str;
      description = ''
        Remote command to query information about a previously created
        NixOS virtual machine.  It should print the IPv6 address of
        the VM on standard output.
      '';
    };

  };

}
