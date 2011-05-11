#! /var/run/current-system/sw/bin/perl -w

use strict;
use utf8;
use XML::LibXML;
use Cwd;
use File::Basename;
use JSON;
use Getopt::Long qw(:config posix_default gnu_getopt no_ignore_case auto_version);
use Text::Table;
use List::MoreUtils qw(uniq);

$main::VERSION = "0.1";


binmode(STDERR, ":utf8");

my @networkExprs;

# The deployment specification, obtained by evaluating the Nix
# expressions specified by the user.  $spec->{machines} is a mapping
# from machine names (i.e. attribute names in the input) to a hash
# containing the desired deployment characteristics of the
# corresponding machine.  E.g., $spec->{machines}->{foo}->{targetEnv}
# contains the target environment type of machine ‘foo’ (e.g., ‘ec2’).
my $spec;

# The current deployment state, containing information about
# previously created or initialised (virtual) machines.  In
# particular, $state->{machines} is a mapping from machine names to a
# hash containing info about the corresponding machine, such as its IP
# address.  E.g., $state->{machines}->{foo}->{ipv6} contains the IPv6
# address of machine ‘foo’.
my $state;

my $stateFile = "./state.json";

my $myDir = dirname(Cwd::abs_path($0));

# Whether to kill previously created VMs that no longer appear in the
# specification.
my $killObsolete = 0;


sub main {
    my $op = \&opDeploy;
    
    exit 1 unless GetOptions(
        "state|s=s" => \$stateFile,
        "info|i" => sub { $op = \&opInfo; },
        "check|c" => sub { $op = \&opCheck; },
        "destroy" => sub { $op = \&opDestroy; },
        "kill-obsolete|k!" => \$killObsolete,
        );
    
    @networkExprs = @ARGV;

    &$op();
}


# ‘--info’ shows the current deployment specification and state.
sub opInfo {
    eval { evalMachineInfo(); }; warn $@ if $@;
    eval { readState(); }; warn $@ if $@;

    my @lines;
    foreach my $name (uniq (sort (keys %{$spec->{machines}}, keys %{$state->{machines}}))) {
        my $m = $spec->{machines}->{$name};
        my $r = $state->{machines}->{$name};
        my $status =
            defined $m
            ? (defined $r
               ? (defined $r->{vmsPath}
                  ? ($r->{vmsPath} eq $state->{vmsPath}
                     ? "Up"
                     : "Incomplete")
                  : "Started")
               : "New")
            : "Obsolete";
        push @lines,
            [ $name
            , $status
            , $m->{targetEnv} || $r->{targetEnv}
            , $r->{vmId}
            , $r->{ipv6}
            ];
    }

    my $table = Text::Table->new(
        { title => "Name", align => "left" }, \ " | ",
        { title => "Status", align => "left" }, \ " | ",
        { title => "Type", align => "left" }, \ " | ",
        { title => "VM Id", align => "left" }, \ " | ",
        { title => "IPv6", align => "left" },
        );
    $table->load(@lines);

    print $table->title;
    print $table->rule('-', '+');
    print $table->body;
}


# ‘--check’ checks whether every machine is reachable via SSH.  It
# also prints the load on every machine.
sub opCheck {
    readState();
    
    foreach my $name (sort (keys %{$state->{machines}})) {
        my $machine = $state->{machines}->{$name};
        print STDERR "$name... ";

        my $load = `ssh -o StrictHostKeyChecking=no root\@$machine->{sshName} cat /proc/loadavg 2>/dev/null`;
        if ($? == 0) {
            my @load = split / /, $load;
            print STDERR "ok [$load[0] $load[1] $load[2]]\n";
        } else {
            print STDERR "fail\n";
        }
    }
}


sub opDeploy {
    # Evaluate the user's network specification to determine machine
    # names and the desired deployment characteristics.
    evalMachineInfo();

    # Read the state file to obtain info about previously started VMs.
    readState();

    # Create missing VMs.
    startMachines();

    # Evaluate and build each machine configuration locally.
    my $vmsPath = buildConfigs();

    # Copy the closures of each machine configuration to the
    # corresponding target machine.
    copyClosures($vmsPath);

    # Activate the new configuration on each machine, and do a
    # rollback if any fails.
    activateConfigs($vmsPath);
}


# ‘--destroy’ destroys all VMs listed in the deployment state record,
# i.e., the entire network previously deployed by
# nixos-deploy-network.
sub opDestroy {
    readState();
    
    foreach my $name (keys %{$state->{machines}}) {
        my $machine = $state->{machines}->{$name};
        killMachine($name, $machine);
    }
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
                , destroyVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "destroyVMCommand"]/string/@value') || die
                , queryVMCommand => $m->findvalue('./attrs/attr[@name = "adhoc"]/attrs/attr[@name = "queryVMCommand"]/string/@value') || die
                };
        } else {
            die "machine ‘$name’ has an unknown target environment type ‘$targetEnv’";
        }
        $spec->{machines}->{$name} = $info;
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


sub killMachine {
    my ($name, $machine) = @_;
    
    if ($machine->{targetEnv} eq "none") {
        print STDERR "removing obsolete machine ‘$name’ from the deployment state...\n";
        # !!! Maybe we actually want to reconfigure the machine in
        # some way to ensure that it's no longer providing any
        # services (except SSH so that the machine can be used in a
        # future configuration).
    }

    elsif ($machine->{targetEnv} eq "adhoc") {
        print STDERR "killing VM ‘$name’...\n";
        system "ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{destroyVMCommand} $machine->{vmId}";
        warn "unable to kill VM: $?" unless $? == 0;
    }

    else {
        die "don't know how to kill machine ‘$name’";
    }

    delete $state->{machines}->{$name};
    writeState;
}


sub startMachines {
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $spec->{machines}->{$name};
        my $prevMachine = $state->{machines}->{$name};
        
        if (defined $prevMachine) {
            # So we already created/used a machine in a previous
            # execution.  If it matches the current deployment
            # parameters, we're done; otherwise, we have to kill the
            # old machine (if permitted) and create a new one.
            if ($machine->{targetEnv} eq $prevMachine->{targetEnv}) {
                # !!! Also check that parameters like the EC2 are the
                # same.
                #print STDERR "machine ‘$name’ already exists\n";
                delete $prevMachine->{obsolete}; # might be an obsolete VM that became active again
                next;
            }
            # !!! Handle killing cloud VMs, etc.  When killing a VM,
            # make sure it's not marked as precious.
            die "machine ‘$name’ was previously created with incompatible deployment parameters\n";
        }
        
        if ($machine->{targetEnv} eq "none") {
            # Not much to do here.

            print STDERR "checking whether machine ‘$name’ is reachable via SSH...\n";

            # !!! should use sshName.
            system "ssh -o StrictHostKeyChecking=no root\@$machine->{targetHost} true < /dev/null 2> /dev/null";
            die "cannot SSH to machine: $?" unless $? == 0;

            $state->{machines}->{$name} =
                { targetEnv => $machine->{targetEnv}
                , targetHost => $machine->{targetHost}
                , timeRegistered => time()
                };
            
            writeState;
        }
        
        elsif ($machine->{targetEnv} eq "adhoc") {

            print STDERR "starting missing VM ‘$name’...\n";
            my $vmId = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{createVMCommand} $ENV{USER}-$name`;
            die "unable to start VM: $?" unless $? == 0;
            chomp $vmId;

            my $ipv6 = `ssh $machine->{adhoc}->{controller} $machine->{adhoc}->{queryVMCommand} $vmId 2> /dev/null`;
            die "unable to query VM state: $?" unless $? == 0;
            chomp $ipv6;
            print STDERR "IPv6 address is $ipv6\n";

            $state->{machines}->{$name} =
                { targetEnv => $machine->{targetEnv}
                , vmId => $vmId
                , ipv6 => $ipv6
                , timeCreated => time()
                , # Need to remember these so that we know how to kill
                  # the VM later, among other things.
                  adhoc => $machine->{adhoc}
                };

            writeState;
            
            print STDERR "checking whether VM ‘$name’ is reachable via SSH...\n";

            system "ssh -o StrictHostKeyChecking=no root\@$ipv6 true < /dev/null 2> /dev/null";
            die "cannot SSH to VM: $?" unless $? == 0;

        }
    }

    writeState; # !!! needed?
    
    # Kill all VMs in $state that no longer exist in $spec.
    foreach my $name (keys %{$state->{machines}}) {
        next if defined $spec->{machines}->{$name};
        my $machine = $state->{machines}->{$name};
        if ($killObsolete) {
            killMachine($name, $machine);
        } else {
            print STDERR "warning: VM ‘$name’ is obsolete; use ‘--kill-obsolete’ to get rid of it\n";
            $machine->{obsolete} = 1;
            writeState;
        }
    }
    
    # Figure out how we're gonna SSH to each machine.  Prefer IPv6
    # addresses over hostnames.
    while (my ($name, $machine) = each %{$state->{machines}}) {
        $machine->{sshName} = $machine->{ipv6} || $machine->{targetHost} || die "don't know how to reach ‘$name’";
    }
    
    # So now that we know the hostnames / IP addresses of all
    # machines, generate a Nix expression containing the physical
    # network configuration that can be stacked on top of the
    # user-supplied network configuration.
    my $hosts = "";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        $hosts .= "$machine->{ipv6} $name\\n" if defined $machine->{ipv6};
    }
    
    open STATE, ">physical.nix" or die;
    print STATE "{\n";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        print STATE "  $name = { config, pkgs, ... }:\n";
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
    my $vmsPath = `nix-build $myDir/eval-machine-info.nix --arg networkExprs '[ @networkExprs ./physical.nix ]' -A machines`;
    die "unable to build all machine configurations" unless $? == 0;
    chomp $vmsPath;
    return $vmsPath;
}


sub copyClosures {
    my ($vmsPath) = @_;
    # !!! Should copy closures in parallel.
    foreach my $name (keys %{$spec->{machines}}) {
        print STDERR "copying closure to machine ‘$name’...\n";
        my $machine = $state->{machines}->{$name};
        my $toplevel = readlink "$vmsPath/$name" or die;
        $machine->{lastCopied} = $toplevel; # !!! rewrite state file?
        system "nix-copy-closure --gzip --to root\@$machine->{sshName} $toplevel";
        die "unable to copy closure to machine ‘$name’" unless $? == 0;
    }
}


sub activateConfigs {
    my ($vmsPath) = @_;

    # Store the store path to the VMs in the deployment state.  This
    # allows ‘--info’ to show whether machines have an outdated
    # configuration.
    $state->{vmsPath} = $vmsPath;

    foreach my $name (keys %{$spec->{machines}}) {
        print STDERR "activating new configuration on machine ‘$name’...\n";
        my $machine = $state->{machines}->{$name};

        my $toplevel = readlink "$vmsPath/$name" or die;
        system "ssh -o StrictHostKeyChecking=no root\@$machine->{sshName} nix-env -p /nix/var/nix/profiles/system --set $toplevel \\; /nix/var/nix/profiles/system/bin/switch-to-configuration switch";
        if ($? != 0) {
            # !!! do a rollback
            die "unable to activate new configuration on machine ‘$name’";
        }

        $machine->{vmsPath} = $vmsPath;
        $machine->{toplevel} = $toplevel;
        writeState;
    }
}


main;
