#! /var/run/current-system/sw/bin/perl -w -I/home/eelco/nixpkgs/Net-Amazon-EC2-0.14/lib

use strict;
use utf8;
use XML::LibXML;
use Cwd;
use File::Basename;
use JSON;
use Getopt::Long qw(:config posix_default gnu_getopt no_ignore_case auto_version);
use Text::Table;
use List::MoreUtils qw(uniq);
use Net::Amazon::EC2;

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

my $stateFile;

my $myDir = dirname(Cwd::abs_path($0));

# Whether to kill previously created VMs that no longer appear in the
# specification.
my $killObsolete = 0;

my $debug = 0;


sub main {
    my $op;
    
    exit 1 unless GetOptions(
        "state|s=s" => \$stateFile,
        "info|i" => sub { $op = \&opInfo; },
        "check|c" => sub { $op = \&opCheck; },
        "destroy" => sub { $op = \&opDestroy; },
        "deploy" => sub { $op = \&opDeploy; },
        "kill-obsolete|k!" => \$killObsolete,
        "debug" => \$debug,
        );

    die "$0: You must specify an operation.\n" unless defined $op;
    
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
                  : defined $r->{pinged}
                     ? "Started"
                     : "Starting")
               : "New")
            : "Obsolete";
        push @lines,
            [ $name
            , $status
            , $m->{targetEnv} || $r->{targetEnv}
            , $r->{vmId}
            , $r->{ipv6} || $r->{ipv4}
            ];
    }

    my $table = Text::Table->new(
        { title => "Name", align => "left" }, \ " | ",
        { title => "Status", align => "left" }, \ " | ",
        { title => "Type", align => "left" }, \ " | ",
        { title => "VM Id", align => "left" }, \ " | ",
        { title => "IP address", align => "left" },
        );
    $table->load(@lines);

    print $table->title;
    print $table->rule('-', '+');
    print $table->body;
}


# Figure out how to connect to a machine via SSH.  Use the public IPv6
# address if available, then the public IPv4 address, and then the
# host name.
sub sshName {
    my ($name, $machine) = @_;
    return $machine->{ipv6} || $machine->{ipv4} || $machine->{targetHost} || die "don't know how to reach ‘$name’";
}


# Check whether the given machine is reachable via SSH.
sub pingSSH {
    my ($name, $machine) = @_;
    my $sshName = sshName($name, $machine);
    # !!! fix, just check whether the port is open
    system "ssh -o StrictHostKeyChecking=no root\@$sshName true < /dev/null 2>/dev/null";
    return $? == 0;
}


# ‘--check’ checks whether every machine is reachable via SSH.  It
# also prints the load on every machine.
sub opCheck {
    readState();
    
    foreach my $name (sort (keys %{$state->{machines}})) {
        my $machine = $state->{machines}->{$name};
        next if $machine->{obsolete};
        print STDERR "$name... ";

        my $sshName = sshName($name, $machine);
        my $load = `ssh -o StrictHostKeyChecking=no root\@$sshName cat /proc/loadavg 2>/dev/null`;
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
        `nix-instantiate --eval-only --show-trace --xml --strict --show-trace $myDir/eval-machine-info.nix --arg networkExprs '[ @networkExprs ]' -A machineInfo`;
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
        } elsif ($targetEnv eq "ec2") {
            $info->{ec2} =
                { type => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "type"]/string/@value') || die
                , controller => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "controller"]/string/@value') || die
                , ami => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "ami"]/string/@value') || die
                , instanceType => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "instanceType"]/string/@value') || die
                , keyPair => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "keyPair"]/string/@value') || die
                };
        } else {
            die "machine ‘$name’ has an unknown target environment type ‘$targetEnv’";
        }
        $spec->{machines}->{$name} = $info;
    }
}


sub readState {
    local $/;
    if (defined $stateFile && -e $stateFile) {
        open(my $fh, '<', $stateFile) or die "$!";
        $state = decode_json <$fh>;
    } else {
        $state = { machines => {} };
    }
}


sub writeState {
    die "state file not set; please use ‘--state’\n" unless defined $stateFile;
    open(my $fh, '>', "$stateFile.new") or die "$!";
    print $fh encode_json($state);
    close $fh;
    rename "$stateFile.new", $stateFile or die;
}


sub openEC2 {
    my ($name, $machine) = @_;
    return Net::Amazon::EC2->new
        ( AWSAccessKeyId => ($ENV{'EC2_ACCESS_KEY'} || $ENV{'AWS_ACCESS_KEY_ID'} || die "please set \$EC2_ACCESS_KEY or \$AWS_ACCESS_KEY_ID\n")
        , SecretAccessKey => ($ENV{'EC2_SECRET_KEY'} || $ENV{'AWS_SECRET_ACCESS_KEY'} || die "please set \$EC2_SECRET_KEY or \$AWS_SECRET_ACCESS_KEY\n")
        , # !!! This assumes that all machines have the same controller/zone.
          base_url => $machine->{ec2}->{controller}
        , debug => $debug
        );
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
        die "unable to kill VM: $?" unless $? == 0;
    }

    elsif ($machine->{targetEnv} eq "ec2") {
        print STDERR "killing VM ‘$name’ (EC2 instance ‘$machine->{vmId}’)...\n";
        my $ec2 = openEC2($name, $machine);
        my $res = $ec2->terminate_instances(InstanceId => $machine->{vmId});
        unless (!defined $res || ref $res eq "ARRAY") {
            my $error = @{$res->errors}[0];
            if ($error->code eq "InstanceNotFound") {
                warn "EC2 instance “$machine->{vmId}” no longer exists, removing\n";
            } else {
                die "could not terminate EC2 instance: “" . $error->message . "”\n";
            }
        }
        # !!! Check the state change? Wait until the machine has shut down?
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

        elsif ($machine->{targetEnv} eq "ec2") {
            print STDERR "starting missing VM ‘$name’ on EC2 cloud ‘$machine->{ec2}->{controller}’...\n";

            my $ec2 = openEC2($name, $machine);

            my $reservation = $ec2->run_instances
                ( ImageId => $machine->{ec2}->{ami}
                , InstanceType => $machine->{ec2}->{instanceType}
                , KeyName => $machine->{ec2}->{keyPair}
                , MinCount => 1
                , MaxCount => 1
                );

            die "could not create EC2 instance: “" . @{$reservation->errors}[0]->message . "”\n"
                if $reservation->isa('Net::Amazon::EC2::Errors');

            my $instance = @{$reservation->instances_set}[0];
            my $vmId = $instance->instance_id;

            print STDERR
                "got reservation ‘", $reservation->reservation_id,
                "’, instance ‘$vmId’\n";

            # !!! We should already update the state record to
            # remember that we started an instance.

            # Wait until the machine has an IP address.  (It may not
            # have finished booting, but later down we wait for the
            # SSH port to open.)
            print STDERR "waiting for IP address... ";
            while (1) {
                my $state = $instance->instance_state->name;
                print STDERR "[$state] ";
                die "EC2 instance ‘$vmId’ didn't start; it went to state ‘$state’\n"
                    if $state ne "pending" && $state ne "running" &&
                       $state ne "scheduling" && $state ne "launching";
                last if defined $instance->dns_name_v6 || defined $instance->ip_address;
                sleep 5;
                my $reservations = $ec2->describe_instances(InstanceId => $vmId);
                die "could not query EC2 instance: “" . @{$reservations->errors}[0]->message . "”\n"
                    if ref $reservations ne "ARRAY";
                $instance = @{@{$reservations}[0]->instances_set}[0];
            }
            print STDERR "\n";

            $state->{machines}->{$name} =
                { targetEnv => $machine->{targetEnv}
                , vmId => $vmId
                , ipv4 => $instance->ip_address
                , ipv6 => $instance->dns_name_v6 # actually its public IPv6 address
                , reservation => $reservation->reservation_id
                , privateIpv4 => $instance->private_ip_address
                , dnsName => $instance->dns_name
                , privateDnsName => $instance->private_dns_name
                , timeCreated => time()
                , ec2 => $machine->{ec2}
                };

            my $addr = $instance->dns_name_v6 || $instance->ip_address || die "don't know how to reach ‘$name’";
            print STDERR "started instance with IP address $addr\n";
                
            writeState;            
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
    
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        unless (defined $machine->{pinged}) {
            print STDERR "checking whether machine ‘$name’ is reachable via SSH...";
            my $n = 0;
            while (1) {
                last if pingSSH($name, $machine);
                print STDERR ".";
                die "machine ‘$name’ cannot be reached via SSH" if $n++ == 40;
                sleep 5;
            }
            print STDERR " yes\n";
            $machine->{pinged} = 1;
            writeState;
        }
    }
    
    # So now that we know the hostnames / IP addresses of all
    # machines, generate a Nix expression containing the physical
    # network configuration that can be stacked on top of the
    # user-supplied network configuration.
    my $hosts = "";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        $hosts .= "$machine->{ipv6} $name\\n" if $machine->{ipv6};
        if (defined $machine->{privateIpv4}) {
            $hosts .= "$machine->{privateIpv4} $name\\n";
        } else {
            $hosts .= "$machine->{ipv4} $name\\n" if $machine->{ipv4};
        }
    }
    
    open STATE, ">physical.nix" or die;
    print STATE "{\n";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        print STATE "  $name = { config, pkgs, modulesPath, ... }:\n";
        print STATE "    {\n";
        if ($machine->{targetEnv} eq "adhoc") {
            print STATE "      require = [ $myDir/adhoc-cloud-vm.nix ];\n";
        } elsif ($machine->{targetEnv} eq "ec2") {
            if ($machine->{ec2}->{type} eq "ec2") {
                print STATE "      require = [ \"\${modulesPath}/virtualisation/amazon-config.nix\" ];\n";
            } elsif ($machine->{ec2}->{type} eq "nova") {
                print STATE "      require = [ \"\${modulesPath}/virtualisation/nova-image.nix\" ];\n";
            } else {
                die "machine ‘$name’ has unknown EC2 type ‘$machine->{ec2}->{type}’\n";
            }
        }
        print STATE "      networking.extraHosts = \"$hosts\";\n";
        print STATE "    };\n";
    }
    print STATE "}\n";
    close STATE;
}


sub buildConfigs {
    print STDERR "building all machine configurations...\n";
    my $vmsPath = `nix-build --show-trace $myDir/eval-machine-info.nix --arg networkExprs '[ @networkExprs ./physical.nix ]' -A machines`;
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
        my $sshName = sshName($name, $machine);
        system "nix-copy-closure --gzip --to root\@$sshName $toplevel";
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
        my $sshName = sshName($name, $machine);
        system "ssh -o StrictHostKeyChecking=no root\@$sshName nix-env -p /nix/var/nix/profiles/system --set $toplevel \\; /nix/var/nix/profiles/system/bin/switch-to-configuration switch";
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
