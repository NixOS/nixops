#! /var/run/current-system/sw/bin/perl -w

use utf8;
use XML::LibXML;
use Cwd;
use File::Basename;
use JSON;

binmode(STDERR, ":utf8");

# !!! Cleanly separate $state->{machines} (the deployment state) and
# @machines (the deployment specification).
            
my @networkExprs;
my @machines = ();
my $outPath;
my $state;
my $stateFile = "./state.json";

my $myDir = dirname(Cwd::abs_path($0));


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
    @networkExprs = @ARGV;
    die unless scalar @networkExprs > 0;
}


sub evalMachineInfo {
    my $machineInfoXML =
        `nix-instantiate --eval-only --xml --strict $myDir/eval-machine-info.nix --arg networkExprs '[ @networkExprs ]' -A machineInfo`;
    die "evaluation of @networkExprs failed" unless $? == 0;
    
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
                , createVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "createVMCommand"]/string/@value') || die
                , queryVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "queryVMCommand"]/string/@value') || die
                };
        } else {
            die "machine ‘$name’ has an unknown target environment type ‘$targetEnv’";
        }
        push @machines, $info;
    }
}


sub readState {
    local $/;
    if (-e $stateFile) {
        open(my $fh, '<', $stateFile) or die "$!";
        $state = decode_json <$fh>;
    } else {
        $state = { machines => {} };
    }
}


sub writeState {
    open(my $fh, '>', "$stateFile.new") or die "$!";
    print $fh encode_json($state);
    close $fh;
    rename "$stateFile.new", $stateFile or die;
}


sub startMachines {
    foreach my $machine (@machines) {

        my $prevMachine = $state->{machines}->{$machine->{name}};
        
        if (defined $prevMachine) {
            # So we already created/used a machine in a previous
            # execution.  If it matches the current deployment
            # parameters, we're done; otherwise, we have to kill the
            # old machine (if permitted) and create a new one.
            if ($machine->{targetEnv} eq $prevMachine->{targetEnv}) {
                # !!! Also check that parameters like the EC2 are the
                # same.
                $machine->{ipv6} = $prevMachine->{ipv6}; # !!! hack
                print STDERR "machine ‘$machine->{name}’ already exists\n";
                next;
            }
            # !!! Handle killing cloud VMs, etc.  When killing a VM,
            # make sure it's not marked as precious.
            die "machine ‘$machine->{name}’ was previously created with incompatible deployment parameters\n";
        }
        
        if ($machine->{targetEnv} eq "none") {
            # Nothing to do here.
        }
        
        elsif ($machine->{targetEnv} eq "adhoc") {
        
            print STDERR "starting missing VM ‘$machine->{name}’...\n";
            my $vmId = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{createVMCommand}`;
            die "unable to start VM: $?" unless $? == 0;
            chomp $vmId;

            $machine->{vmId} = $vmId;

            $ipv6 = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{queryVMCommand} $machine->{vmId} 2> /dev/null`;
            die "unable to query VM state: $?" unless $? == 0;

            chomp $ipv6;
            $machine->{ipv6} = $ipv6;
            print STDERR "IPv6 address is $ipv6\n";

            $state->{machines}->{$machine->{name}} =
                { targetEnv => $machine->{targetEnv}
                , vmId => $machine->{vmId}
                , ipv6 => $machine->{ipv6}
                };

            writeState;
            
            print STDERR "checking whether VM ‘$machine->{name}’ is reachable via SSH...\n";

            system "ssh -o StrictHostKeyChecking=no root\@$ipv6 true < /dev/null 2> /dev/null";
            die "cannot SSH to VM: $?" unless $? == 0;

        }
    }

    # !!! Kill all machines in $state that no longer exist in $machines.

    writeState;
            
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
        $hosts .= "$machine->{ipv6} $machine->{name}\\n" if defined $machine->{ipv6};
    }
    
    open STATE, ">physical.nix" or die;
    print STATE "{\n";
    foreach my $machine (@machines) {
        print STATE "  $machine->{name} = { config, pkgs, ... }:\n";
        print STATE "    {\n";
        if ($machine->{targetEnv} eq "adhoc") {
            print STATE "      require = [ $myDir/adhoc-cloud-vm.nix ];\n";
        }
        print STATE "      networking.extraHosts = \"$hosts\";\n";
        print STATE "    };\n";
    }
    print STATE "}\n";
    close STATE;
}


sub buildConfigs {
    print STDERR "building all machine configurations...\n";
    $outPath = `nix-build $myDir/eval-machine-info.nix --arg networkExprs '[ @networkExprs ./physical.nix ]' -A machines`;
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
