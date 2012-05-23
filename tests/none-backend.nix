{ system, charon }:

with import <nixos/lib/testing.nix> { inherit system; };

makeTest ({ pkgs, ... }:

let

  # Physical Charon model.
  physical = pkgs.writeText "physical.nix"
    ''
      { network.description = "Testing";

        target1 =
          { require =
              [ <nixos/modules/virtualisation/qemu-vm.nix>
                <nixos/modules/testing/test-instrumentation.nix>
              ];
            deployment.targetEnv = "none";
            deployment.targetHost = "target1";
            services.nixosManual.enable = false;
            boot.loader.grub.enable = false;
          };
      
      }
    '';

  # Logical Charon model.
  logical = pkgs.writeText "physical.nix"
    ''
      { network.description = "Testing";

        target1 =
          { config, pkgs, ... }:
          { services.openssh.enable = true;
            environment.systemPackages = [ pkgs.vim ];
          };

        /*      
        target2 =
          { config, pkgs, ... }:
          { services.openssh.enable = true;
          };
        */
      }
    '';

  env = "NIX_PATH=nixos=${<nixos>}:nixpkgs=${<nixpkgs>}";

in

{

  nodes =
    { coordinator =
        { config, pkgs, ... }:
        { environment.systemPackages = [ charon pkgs.stdenv pkgs.vim ];
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

      # Test some trivial commands.
      subtest "trivia", sub {
        $coordinator->succeed("charon --version 2>&1 | grep Charon");
        $coordinator->succeed("charon --help");
      };

      # Set up the state file.
      $coordinator->succeed("charon create ${logical} ${physical}");

      # Test ‘charon info’.
      subtest "info-before", sub {
        $coordinator->succeed("${env} charon info >&2");
      };
      
      # Do a deployment.
      subtest "deploy", sub {
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
    '';
  
})
