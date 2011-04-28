#! /var/run/current-system/sw/bin/perl -w

use XML::LibXML;

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
        `nix-instantiate --eval-only --xml --strict ./eval-machine-info.nix --argstr networkExpr $networkExpr -A machineInfo`;
    die "evaluation of $networkExpr failed" unless $? == 0;
    
    #print $machineInfoXML, "\n";

    my $dom = XML::LibXML->load_xml(string => $machineInfoXML);
    foreach my $m ($dom->findnodes('/expr/list/string')) {
        my $name = $m->findvalue('./@value');
        #print STDERR "got machine ‘$name’\n";
        push @machines, { name => $name };
    }
}


sub readState {
}


sub startMachines {
    foreach my $machine (@machines) {
        print STDERR "checking whether VM ‘$machine->{name}’ exists...\n";

        my $ipv6 = `ssh root\@stan.nixos.org query-vm $machine->{name} 2> /dev/null`;
        die "unable to query VM state: $?" unless $? == 0 || $? == 256;

        if ($? == 256) {
            print STDERR "starting missing VM ‘$machine->{name}’...\n";
            system "ssh root\@stan.nixos.org create-vm $machine->{name}";
            die "unable to start VM: $?" unless $? == 0;

            $ipv6 = `ssh root\@stan.nixos.org query-vm $machine->{name} 2> /dev/null`;
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


sub buildConfigs {
    print STDERR "building all machine configurations...\n";
    $outPath = `nix-build ./eval-machine-info.nix --argstr networkExpr $networkExpr -A machines`;
    die "unable to build all machine configurations" unless $? == 0;
    chomp $outPath;
}


sub copyClosures {
    # !!! Should copy closures in parallel.
    foreach my $machine (@machines) {
        print STDERR "copying closure to machine ‘$machine->{name}’...\n";
        my $systemPath = readlink "$outPath/$machine->{name}/system" or die;
        system "nix-copy-closure --gzip --to root\@$machine->{ipv6} $systemPath";
        die "unable to copy closure to machine ‘$machine->{name}’" unless $? == 0;
    }
}


sub activateConfigs {
    # TODO
}


main;
