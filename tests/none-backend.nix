{ system, charon }:

with import <nixos/lib/testing.nix> { inherit system; };
with pkgs.lib;

makeTest ({ pkgs, ... }:

let

  # Physical Charon model.
  physical = pkgs.writeText "physical.nix"
    ''
      rec {
        network.description = "Testing";

        target1 =
          { require =
              [ <nixos/modules/virtualisation/qemu-vm.nix>
                <nixos/modules/testing/test-instrumentation.nix>
              ];
            deployment.targetEnv = "none";
            services.nixosManual.enable = false;
            boot.loader.grub.enable = false;
          };

        target2 = target1;
      }
    '';

  # Logical Charon model.
  logical = n: pkgs.writeText "logical.nix"
    ''
      { network.description = "Testing";

        target1 =
          { config, pkgs, ... }:
          { services.openssh.enable = true;
            users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ ./id_test.pub ];
            ${optionalString (n == 1) ''
              environment.systemPackages = [ pkgs.vim ];
            ''}
            ${optionalString (n == 2) ''
              services.httpd.enable = true;
              services.httpd.adminAddr = "e.dolstra@tudelft.nl";
            ''}
          };

        target2 =
          { config, pkgs, ... }:
          { services.openssh.enable = true;
            users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ ./id_test.pub ];
          };
      }
    '';

  env = "NIX_PATH=nixos=${<nixos>}:nixpkgs=${<nixpkgs>}";

in

{

  nodes =
    { coordinator =
        { config, pkgs, ... }:
        { environment.systemPackages = [ charon pkgs.stdenv pkgs.vim pkgs.apacheHttpd ];
          virtualisation.writableStore = true;
        };

      target1 = 
        { config, pkgs, ... }:
        { services.openssh.enable = true;
          virtualisation.writableStore = true;
          users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ ./id_test.pub ];
        };
        
      target2 = 
        { config, pkgs, ... }:
        { services.openssh.enable = true;
          virtualisation.writableStore = true;
          users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ ./id_test.pub ];
        };
    };

  testScript = { nodes }:
    ''
      # Start all machines.
      startAll;
      $coordinator->waitForJob("network-interfaces");
      $target1->waitForJob("sshd");
      $target2->waitForJob("sshd");

      # Test ssh connectivity
      $coordinator->succeed("mkdir -m 0700 -p ~/.ssh; cp ${./id_test} ~/.ssh/id_dsa; chmod 600 ~/.ssh/id_dsa");
      $coordinator->succeed("ssh -o StrictHostKeyChecking=no -v target1 ls / >&2");
      $coordinator->succeed("ssh -o StrictHostKeyChecking=no -v target2 ls / >&2");

      # Test some trivial commands.
      subtest "trivia", sub {
        $coordinator->succeed("charon --version 2>&1 | grep Charon");
        $coordinator->succeed("charon --help");
      };

      # Set up the state file.
      $coordinator->succeed("cp ${physical} physical.nix");
      $coordinator->succeed("cp ${logical 1} logical.nix");
      $coordinator->succeed("cp ${./id_test.pub} id_test.pub");
      $coordinator->succeed("charon create ./physical.nix ./logical.nix");

      # Test ‘charon info’.
      subtest "info-before", sub {
        $coordinator->succeed("${env} charon info >&2");
      };
      
      # Do a deployment.
      subtest "deploy-1", sub {
        $target1->fail("vim --version");
        $coordinator->succeed("${env} charon deploy --build-only");
        $coordinator->succeed("${env} charon deploy");
        $target1->succeed("vim --version >&2");
      };

      # Test ‘charon info’.
      subtest "info-after", sub {
        $coordinator->succeed("${env} charon info >&2");
      };
      
      # Test ‘charon ssh’.
      subtest "ssh", sub {
        $coordinator->succeed("${env} charon ssh target1 -- -v ls / >&2");
      };
      
      # Test ‘charon check’.
      subtest "check", sub {
        $coordinator->succeed("${env} charon check");
      };

      # Do another deployment.
      subtest "deploy-2", sub {
        $coordinator->succeed("cp ${logical 2} logical.nix");
        $coordinator->succeed("${env} charon deploy");
        $target1->fail("vim --version >&2");
        $target1->succeed("curl --fail -v http://target1/ >&2");
      };
      
    '';
  
})
