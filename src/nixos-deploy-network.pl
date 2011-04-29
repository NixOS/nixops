#! /var/run/current-system/sw/bin/perl -w

use utf8;
use XML::LibXML;

binmode(STDERR, ":utf8");

my $networkExpr;
my @machines = ();
my $outPath;


sub main {
    # Parse the command line.
    processArgs();
    
    # Evaluate the user's network specification to determine machine
    # names and the desired deployment characteristics.
    evalMachineInfo();

    # Read the state file to obtain info about previously started VMs.
    readState();

    # Create missing VMs.
    startMachines();

    # Evaluate and build each machine configuration locally.
    buildConfigs();

    # Copy the closures of each machine configuration to the
    # corresponding target machine.
    copyClosures();

    # Activate the new configuration on each machine, and do a
    # rollback if any fails.
    activateConfigs();
}


sub processArgs {
    $networkExpr = $ARGV[0];
    die unless defined $networkExpr;
}


sub evalMachineInfo {
    my $machineInfoXML =
        `nix-instantiate --eval-only --xml --strict ./eval-machine-info.nix --arg networkExprs '[ $networkExpr ]' -A machineInfo`;
    die "evaluation of $networkExpr failed" unless $? == 0;
    
    #print $machineInfoXML, "\n";

    my $dom = XML::LibXML->load_xml(string => $machineInfoXML);
    foreach my $m ($dom->findnodes('/expr/attrs/attr')) {
        my $name = $m->findvalue('./@name') || die;
        #print STDERR "got machine ‘$name’\n";
        my $targetEnv = $m->findvalue('./attrs/attr[@name = "targetEnv"]/string/@value') || die;
        my $info =
            { name => $name
            , targetEnv => $targetEnv
            };
        if ($targetEnv eq "none") {
            $info->{targetHost} =
                $m->findvalue('./attrs/attr[@name = "targetHost"]/string/@value') || die;
        } elsif ($targetEnv eq "adhoc") {
            $info->{adhoc} =
                { controller => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "controller"]/string/@value') || die
                , startVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "startVMCommand"]/string/@value') || die
                , queryVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "queryVMCommand"]/string/@value') || die
                };
        } else {
            die "machine ‘$name’ has an unknown target environment type ‘$targetEnv’";
        }
        push @machines, $info;
    }
}


sub readState {
}


sub startMachines {
    foreach my $machine (@machines) {
        
        if ($machine->{targetEnv} eq "none") {
            # Nothing to do here.
        }
        
        elsif ($machine->{targetEnv} eq "adhoc") {
        
            print STDERR "checking whether VM ‘$machine->{name}’ exists...\n";

            my $ipv6 = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{queryVMCommand} $machine->{name} 2> /dev/null`;
            die "unable to query VM state: $?" unless $? == 0 || $? == 256;

            if ($? == 256) {
                print STDERR "starting missing VM ‘$machine->{name}’...\n";
                system "ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{createVMCommand} $machine->{name}";
                die "unable to start VM: $?" unless $? == 0;

                $ipv6 = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{queryVMCommand} $machine->{name} 2> /dev/null`;
                die "unable to query VM state: $?" unless $? == 0;
            }

            chomp $ipv6;

            print STDERR "IPv6 address is $ipv6\n";

            print STDERR "checking whether VM ‘$machine->{name}’ is reachable via SSH...\n";

            system "ssh -o StrictHostKeyChecking=no root\@$ipv6 true < /dev/null 2> /dev/null";
            die "cannot SSH to VM: $?" unless $? == 0;

            $machine->{ipv6} = $ipv6;
        }
    }

    # Figure out how we're gonna SSH to each machine.  Prefer IPv6
    # addresses over hostnames.
    foreach my $machine (@machines) {
        $machine->{sshName} = $machine->{ipv6} || $machine->{targetHost} || die "don't know how to reach ‘$machine->{name}’";
    }
    
    # So now that we know the hostnames / IP addresses of all
    # machines, generate a Nix expression containing the physical
    # network configuration that can be stacked on top of the
    # user-supplied network configuration.
    my $hosts = "";
    foreach my $machine (@machines) {
        $hosts .= "$machine->{ipv6} $machine->{name}\\n";
    }
    
    open STATE, ">state.nix" or die;
    print STATE "{\n";
    foreach my $machine (@machines) {
        print STATE "  $machine->{name} = { config, pkgs, ... }:\n";
        print STATE "    {\n";
        print STATE "      networking.extraHosts = \"$hosts\";\n";
        print STATE "    };\n";
    }
    print STATE "}\n";
    close STATE;
}


sub buildConfigs {
    print STDERR "building all machine configurations...\n";
    $outPath = `nix-build ./eval-machine-info.nix --arg networkExprs '[ $networkExpr ./state.nix ]' -A machines`;
    die "unable to build all machine configurations" unless $? == 0;
    chomp $outPath;
}


sub copyClosures {
    # !!! Should copy closures in parallel.
    foreach my $machine (@machines) {
        print STDERR "copying closure to machine ‘$machine->{name}’...\n";
        my $toplevel = readlink "$outPath/$machine->{name}" or die;
        $machine->{toplevel} = $toplevel;
        system "nix-copy-closure --gzip --to root\@$machine->{sshName} $toplevel";
        die "unable to copy closure to machine ‘$machine->{name}’" unless $? == 0;
    }
}


sub activateConfigs {
    foreach my $machine (@machines) {
        print STDERR "activating new configuration on machine ‘$machine->{name}’...\n";
        system "ssh -o StrictHostKeyChecking=no root\@$machine->{sshName} nix-env -p /nix/var/nix/profiles/system --set $machine->{toplevel} \\; /nix/var/nix/profiles/system/bin/switch-to-configuration switch";
        if ($? != 0) {
            # !!! do a rollback
            die "unable to activate new configuration on machine ‘$machine->{name}’";
        }
    }
}


main;
