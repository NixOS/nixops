#! /var/run/current-system/sw/bin/perl -w

use strict;
use utf8;
use XML::LibXML;
use Cwd;
use File::Basename;
use File::Spec;
use File::Temp;
use File::Slurp;
use File::Path;
use JSON;
use Getopt::Long qw(:config posix_default gnu_getopt no_ignore_case auto_version auto_help);
use Text::Table;
use List::MoreUtils qw(uniq);
use Data::UUID;
#use Nix::Store;
use Set::Object;
use MIME::Base64;
use Pod::Usage;

$main::VERSION = "0.1";


binmode(STDERR, ":utf8");

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

# Known contents of Nix stores on machines.
my $stores;

my $dirty = 0; # whether the state file should be rewritten

my $stateFile;

my $myDir = dirname(Cwd::abs_path($0));

my $myNixDir = `echo '<charon>' | nix-instantiate - --eval-only`;
die "\$NIX_PATH does not include the Charon Nix expressions!\n" unless $myNixDir;
chomp $myNixDir;

# Whether to kill previously created VMs that no longer appear in the
# specification.
my $killObsolete = 0;

my $debug = 0;

my $tmpDir = File::Temp::tempdir("charon.XXXXX", CLEANUP => 1, TMPDIR => 1);


sub main {
    my $op = \&opDeploy;
    
    exit 1 unless GetOptions(
        "help|?" => sub { $op = \&opHelp; },
        "state|s=s" => \$stateFile,
        "create" => sub { $op = \&opCreate; },
        "info|i" => sub { $op = \&opInfo; },
        "check|c" => sub { $op = \&opCheck; },
        "destroy" => sub { $op = \&opDestroy; },
        "deploy" => sub { $op = \&opDeploy; },
        "show-physical" => sub { $op = \&opShowPhysical; },
        "kill-obsolete|k!" => \$killObsolete,
        "debug" => \$debug,
        );

    die "$0: You must specify an operation.\n" unless defined $op;
    
    &$op();
}


sub noArgs {
    die "$0: unexpected argument(s) ‘@ARGV’\n" if scalar @ARGV;
}


sub opHelp {
    pod2usage(-exitstatus => 0, -verbose => 1);
}


sub opCreate {
    eval { readState(); }; warn $@ if $@;

    my @networkExprs = @ARGV;
    die "‘--create’ requires the paths of one or more network specifications\n" if scalar @networkExprs == 0;

    $state->{networkExprs} = [ map { File::Spec->rel2abs($_) } @networkExprs ];

    writeState();
}


# ‘--info’ shows the current deployment specification and state.
sub opInfo {
    noArgs;
    eval { readState(); }; warn $@ if $@;
    eval { evalMachineInfo(); }; warn $@ if $@;

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
        my $region =  $m->{ec2}->{region} || $r->{ec2}->{region};
        push @lines,
            [ $name
            , $status
            , $m->{targetEnv} . (defined $region ? " [$region]" : "")
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

    print "Network name: ", $state->{name} || $spec->{name}, "\n";
    print "Network UUID: $state->{uuid}\n\n";
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


sub sshFlags {
    my ($name, $machine) = @_;
    my @flags;
    if ($machine->{targetEnv} eq "virtualbox") {
        push @flags, "-o", "StrictHostKeyChecking=no";
        push @flags, "-i", "$myNixDir/id_charon-virtualbox";
    }
    return @flags;
}


# Check whether the given machine is reachable via SSH.
sub pingSSH {
    my ($name, $machine) = @_;
    my $sshName = sshName($name, $machine);
    my @sshFlags = sshFlags($name, $machine);
    # !!! fix, just check whether the port is open
    system "ssh @sshFlags root\@$sshName true < /dev/null 2>/dev/null";
    return $? == 0;
}


# ‘--check’ checks whether every machine is reachable via SSH.  It
# also prints the load on every machine.
sub opCheck {
    noArgs;
    readState();
    
    foreach my $name (sort (keys %{$state->{machines}})) {
        my $machine = $state->{machines}->{$name};
        next if $machine->{obsolete};
        print STDERR "$name... ";

        my $sshName = sshName($name, $machine);
        my @sshFlags = sshFlags($name, $machine);
        my $load = `ssh @sshFlags root\@$sshName cat /proc/loadavg 2>/dev/null`;
        if ($? == 0) {
            my @load = split / /, $load;
            print STDERR "ok [$load[0] $load[1] $load[2]]\n";
        } else {
            print STDERR "fail\n";
        }
    }
}


sub opDeploy {
    noArgs;

    # Read the state file to obtain info about previously started VMs.
    readState();

    # Evaluate the user's network specification to determine machine
    # names and the desired deployment characteristics.
    evalMachineInfo();

    $state->{name} = $spec->{name};

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
# i.e., the entire network previously deployed by Charon.
sub opDestroy {
    noArgs;
    readState();
    
    foreach my $name (keys %{$state->{machines}}) {
        my $machine = $state->{machines}->{$name};
        killMachine($name, $machine);
    }
}


sub evalMachineInfo {
    die "no network specified; use ‘--create’ to associate a network specification with the state file\n" unless scalar @{$state->{networkExprs} || []};

    my $infoXML =
        `nix-instantiate --eval-only --show-trace --xml --strict --show-trace '<charon/eval-machine-info.nix>' --arg networkExprs '[ @{$state->{networkExprs}} ]' -A info`;
    die "evaluation of @{$state->{networkExprs}} failed" unless $? == 0;

    my $dom = XML::LibXML->load_xml(string => $infoXML);
    
    my ($networkInfo) = $dom->findnodes('/expr/attrs/attr[@name = "network"]');

    $spec->{name} = $networkInfo->findvalue('./attrs/attr[@name = "name"]/string/@value') || "Unnamed Charon network";

    my ($machineInfo) = $dom->findnodes('/expr/attrs/attr[@name = "machines"]');

    foreach my $m ($machineInfo->findnodes('./attrs/attr')) {
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
                , region => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "region"]/string/@value') || ""
                , controller => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "controller"]/string/@value') || die
                , ami => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "ami"]/string/@value') || die
                , instanceType => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "instanceType"]/string/@value') || die
                , keyPair => $m->findvalue('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "keyPair"]/string/@value') || die
                , securityGroups => [ map { $_->findvalue(".") } $m->findnodes('./attrs/attr[@name = "ec2"]/attrs/attr[@name = "securityGroups"]/list/string/@value') ]
                };
        } elsif ($targetEnv eq "virtualbox") {
            $info->{virtualbox} =
                { baseImage => $m->findvalue('./attrs/attr[@name = "virtualbox"]/attrs/attr[@name = "baseImage"]/string/@value') || die
                };
        } else {
            die "machine ‘$name’ has an unknown target environment type ‘$targetEnv’";
        }
        $spec->{machines}->{$name} = $info;
    }
}


sub readState {
    local $/;
    die "no state file specified; use ‘--state FILENAME.json’\n" unless defined $stateFile;
    
    if (-e $stateFile) {
        open(my $fh, '<', $stateFile) or die "$!";
        $state = decode_json <$fh>;
    } else {
        $state = { machines => {} };
    }
    
    $state->{uuid} = lc(new Data::UUID->create_str()) unless defined $state->{uuid};

    # Convert the "stores" attributes from lists into sets for efficiency.
    foreach my $name (sort (keys %{$state->{machines}})) {
        $stores->{$name} = Set::Object->new(@{$state->{machines}->{$name}->{store}});
    }
}


sub writeState {
    die "no state file specified; use ‘--state FILENAME.json’\n" unless defined $stateFile;
    open(my $fh, '>', "$stateFile.new") or die "$!";
    print $fh encode_json($state);
    close $fh;
    rename "$stateFile.new", $stateFile or die;
    $dirty = 0;
}


sub openEC2 {
    require Net::Amazon::EC2;
    my ($name, $machine) = @_;
    return Net::Amazon::EC2->new
        ( AWSAccessKeyId => ($ENV{'EC2_ACCESS_KEY'} || $ENV{'AWS_ACCESS_KEY_ID'} || die "please set \$EC2_ACCESS_KEY or \$AWS_ACCESS_KEY_ID\n")
        , SecretAccessKey => ($ENV{'EC2_SECRET_KEY'} || $ENV{'AWS_SECRET_ACCESS_KEY'} || die "please set \$EC2_SECRET_KEY or \$AWS_SECRET_ACCESS_KEY\n")
        , # !!! This assumes that all machines have the same controller/region.
          base_url => $machine->{ec2}->{controller}
        , version => '2011-01-01' # required for tag support
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

    elsif ($machine->{targetEnv} eq "virtualbox") {
        print STDERR "killing VM ‘$name’ (VirtualBox machine ‘$machine->{vmId}’)...\n";
        
        system "VBoxManage controlvm '$machine->{vmId}' poweroff";
        #die "unable to power off VirtualBox VM: $?" unless $? == 0;

        sleep 2; # !!! stupid asynchronous commands
        
        system "VBoxManage unregistervm --delete '$machine->{vmId}'";
        die "unable to destroy VirtualBox VM: $?" unless $? == 0;
    }

    else {
        die "don't know how to kill machine ‘$name’";
    }

    delete $state->{machines}->{$name};
    delete $stores->{$name};
    writeState;
}


# Create the physical network specification module.  It's added to the
# user's network specification to produce the complete specification
# that can be built and deployed.
sub createPhysicalSpec {

    # Produce the /etc/hosts file.
    my $hosts = "";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};
        $hosts .= "$machine->{ipv6} $name\\n" if $machine->{ipv6};
        if (defined $machine->{privateIpv4}) {
            $hosts .= "$machine->{privateIpv4} $name\\n";
        } else {
            $hosts .= "$machine->{ipv4} $name\\n" if $machine->{ipv4};
        }
        if (defined $machine->{ipv4}) {
            $hosts .= "$machine->{ipv4} $name-public\\n";
        }
    }

    # Assign globally unique numbers to tun devices to prevent collisions.
    my $tunNr = 0;

    my $physical = "{\n";
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};

        $physical .= "  $name = { config, pkgs, modulesPath, ... }:\n";
        $physical .= "    {\n";

        my %kernelModules;
        my $needsPublicKey = 0;
        my $needsPrivateKey = 0;
        
        # Determine whether and how this machine can talk to every
        # other machine in the network.
        foreach my $name2 (keys %{$spec->{machines}}) {
            my $machine2 = $state->{machines}->{$name2};
            next if $name eq $name2;

            if ($machine->{targetEnv} eq $machine2->{targetEnv}) {

                if ($machine->{targetEnv} eq "ec2" &&
                    $machine->{ec2}->{controller} ne $machine2->{ec2}->{controller})
                {
                    # The two machines are in different regions, so
                    # they can't talk directly to each other over
                    # their private IP.  So create a VPN connection
                    # over their public IPs to forward the private
                    # IPs.
                    $kernelModules{"tun"} = 1;

                    # It's a two-way tunnel, so we only need to start
                    # it on one machine (for each pair of machines).
                    # Pick the one that has the higher name
                    # (lexicographically).  Note that this is the
                    # reverse order in which machines get activated,
                    # so the server should be up by the time the
                    # client starts the connection.
                    if ($name gt $name2) {
                        print STDERR "creating tunnel between ‘$name’ and ‘$name2’\n";
                        my $clientIP = $machine->{privateIpv4} || die;
                        my $serverIP = $machine2->{privateIpv4} || die;
                        $physical .= "      jobs.vpn = { path = [ pkgs.nettools ]; startOn = \"started network-interfaces\"; exec = \"\${pkgs.openssh}/bin/ssh -i /root/.ssh/id_vpn -o StrictHostKeyChecking=no -f -x -w $tunNr:$tunNr $name2-public 'ifconfig tun$tunNr $clientIP $serverIP netmask 255.255.255.255; route add $clientIP/32 dev tun$tunNr'\"; daemonType = \"fork\"; postStart = \"ifconfig tun$tunNr $serverIP $clientIP netmask 255.255.255.255; route add $serverIP/32 dev tun$tunNr\"; };\n";
                        $tunNr++;
                        $needsPrivateKey = 1;
                    } else {
                        $needsPublicKey = 1;
                    }
                }

                next;
            }

            print STDERR "warning: machines ‘$name’ and ‘$name2’ may not be able to talk to each other\n";
        }

        if (scalar(keys %kernelModules) > 0) {
            $physical .= "      boot.kernelModules = [ " . join(" ", map { "\"$_\"" } (keys %kernelModules)) . " ];\n";
        }

        $physical .= "      services.openssh.extraConfig = \"PermitTunnel yes\\n\";\n";

        if ($needsPublicKey) {
            $physical .= "      system.activationScripts.addAuthorizedKey = \"mkdir -p /root/.ssh -m 700; grep -v DUMMY < /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.tmp; cat \${/home/eelco/Dev/charon/id_tmp.pub} >> /root/.ssh/authorized_keys.tmp; mv /root/.ssh/authorized_keys.tmp /root/.ssh/authorized_keys\";\n";
        }

        if ($needsPrivateKey) {
            $physical .= "      system.activationScripts.addPrivateKey = \"mkdir -p /root/.ssh -m 700; cat \${/home/eelco/Dev/charon/id_tmp} > /root/.ssh/id_vpn; chmod 600 /root/.ssh/id_vpn\";\n";
        }

        if ($machine->{targetEnv} eq "adhoc") {
            $physical .= "      require = [ <charon/adhoc-cloud-vm.nix> ];\n";
        } elsif ($machine->{targetEnv} eq "ec2") {
            if ($machine->{ec2}->{type} eq "ec2") {
                $physical .= "      require = [ \"\${modulesPath}/virtualisation/amazon-config.nix\" ];\n";
            } elsif ($machine->{ec2}->{type} eq "nova") {
                $physical .= "      require = [ \"\${modulesPath}/virtualisation/nova-image.nix\" ];\n";
            } else {
                die "machine ‘$name’ has unknown EC2 type ‘$machine->{ec2}->{type}’\n";
            }
        } elsif ($machine->{targetEnv} eq "virtualbox") {
            $physical .= "      require = [ <charon/virtualbox-image-charon.nix> ];\n";
            $physical .= "      nixpkgs.system = pkgs.lib.mkOverride 900 \"x86_64-linux\";\n";
        }
        
        if (defined $machine->{privateIpv4}) {
          $physical .= "      networking.privateIPv4 = \"$machine->{privateIpv4}\";\n";
        }
        if (defined $machine->{ipv4}) {
          $physical .= "      networking.publicIPv4 = \"$machine->{ipv4}\";\n";
        }
        $physical .= "      networking.extraHosts = \"$hosts\";\n";
        $physical .= "    };\n";
        
    }
    $physical .= "}\n";

    return $physical;
}


# Generate an SSH key pair.
sub generateKeyPair {
    # !!! make this thread-safe
    my $dir = "$tmpDir/ssh-key";
    mkpath($dir, 0, 0700);
    system "ssh-keygen -t dsa -f $dir/key -N '' -C 'Charon auto-generated key' > /dev/null";
    die "cannot generate an SSH key: $?" unless $? == 0;
    my $private = read_file("$dir/key");
    unlink "$dir/key" or die;
    my $public = read_file("$dir/key.pub");
    chomp $public;
    unlink "$dir/key.pub" or die;
    return ($public, $private);
}


# Add a machine's public key to ~/.ssh/known_hosts and remove existing
# entries for the machine's IP address or host name.  !!!
# Alternatively, we could just create a per-machine known_hosts file,
# which might be easier to maintain.
sub addToKnownHosts {
    my ($machine) = @_;
    my $file = "$ENV{HOME}/.ssh/known_hosts";
    my $contents = "";
    if (-e $file) { $contents = read_file($file); };
    
    my @names = ();
    push @names, $machine->{dnsName} if defined $machine->{dnsName};
    push @names, $machine->{ipv4} if defined $machine->{ipv4};
    push @names, $machine->{ipv6} if defined $machine->{ipv6};
    
    my $new = "";
    foreach my $line (split /\n/, $contents) {
        $line =~ /^([^ ]*) (.*)$/ or die;
        my $key = $2;
        my @left;
        foreach my $name (split /,/, $1) {
            push @left, $name unless grep { $_ eq $name } @names;
        }
        $new .= join(",", @left) . " " . $key . "\n" if scalar @left > 0;
    }
    
    $new .= join(",", @names) . " " . $machine->{publicHostKey} . "\n"
        if scalar @names > 0 && exists $machine->{publicHostKey};
        
    write_file($file . ".new", $new);

    rename($file . ".new", $file) or die;
}


sub startMachines {
    foreach my $name (sort (keys %{$spec->{machines}})) {
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
                $dirty = 1;
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

            # Generate the instance's host key and pass it throught
            # the user data attribute.  We throw away the private key
            # and put the public key in ~/.ssh/known_hosts.
            my ($public, $private) = generateKeyPair();

            $private =~ s/\n/\|/g;
            my $userData = "SSH_HOST_DSA_KEY_PUB:$public\nSSH_HOST_DSA_KEY:$private\n";
            $private = ""; # get rid of it ASAP

            #print "DATA:\n$userData";

            my $ec2 = openEC2($name, $machine);

            my $reservation = $ec2->run_instances
                ( ImageId => $machine->{ec2}->{ami}
                , InstanceType => $machine->{ec2}->{instanceType}
                , KeyName => $machine->{ec2}->{keyPair}
                , MinCount => 1
                , MaxCount => 1
                , SecurityGroup => $machine->{ec2}->{securityGroups}
                , UserData => encode_base64($userData)
                );

            die "could not create EC2 instance: “" . @{$reservation->errors}[0]->message . "”\n"
                if $reservation->isa('Net::Amazon::EC2::Errors');

            my $instance = @{$reservation->instances_set}[0];
            my $vmId = $instance->instance_id;

            print STDERR
                "got reservation ‘", $reservation->reservation_id,
                "’, instance ‘", $instance->instance_id, "’\n";

            $state->{machines}->{$name} =
                { targetEnv => $machine->{targetEnv}
                , vmId => $instance->instance_id
                , reservation => $reservation->reservation_id
                , timeCreated => time()
                , ec2 => $machine->{ec2}
                , publicHostKey => $public
                };

            writeState;
        }

        elsif ($machine->{targetEnv} eq "virtualbox") {
            print STDERR "starting missing VirtualBox VM ‘$name’...\n";

            my $vmId = "charon-$state->{uuid}-$name";

            system "VBoxManage createvm --name '$vmId' --ostype Linux --register";
            die "unable to create VirtualBox VM: $?" unless $? == 0;

            $state->{machines}->{$name} =
                { targetEnv => $machine->{targetEnv}
                , baseImage => $machine->{virtualbox}->{baseImage}
                , vmId => $vmId
                , timeCreated => time()
                };

            writeState;
        }
    }

    writeState if $dirty;
    
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
    
    # Some machines may have been started, but we need some
    # information on them (like IP address) that becomes available
    # later.  So get that now.
    foreach my $name (keys %{$spec->{machines}}) {
        my $machine = $state->{machines}->{$name};

        if ($machine->{targetEnv} eq "ec2" && !$machine->{instanceRunning}) {
            my $ec2 = openEC2($name, $machine);
            
            # Tag the instance.
            $ec2->create_tags
                ( ResourceId => $machine->{vmId}
                , 'Tag.Key' => [ "Name", "CharonNetworkUUID", "CharonMachineName"  ]
                , 'Tag.Value' => [ "$state->{name} [$name]", $state->{uuid}, $name ]
                );

            # Wait until the machine has an IP address.  (It may not
            # have finished booting, but later down we wait for the
            # SSH port to open.)
            print STDERR "waiting for IP address of ‘$name’... ";
            my $instance;
            while (1) {
                my $reservations = $ec2->describe_instances(InstanceId => $machine->{vmId});
                die "could not query EC2 instance: “" . @{$reservations->errors}[0]->message . "”\n"
                    if ref $reservations ne "ARRAY";
                $instance = @{@{$reservations}[0]->instances_set}[0];
                my $state = $instance->instance_state->name;
                print STDERR "[$state] ";
                die "EC2 instance ‘$machine->{vmId}’ didn't start; it went to state ‘$state’\n"
                    if $state ne "pending" && $state ne "running" &&
                       $state ne "scheduling" && $state ne "launching";
                last if defined $instance->dns_name_v6 || defined $instance->ip_address;
                sleep 5;
            }
            print STDERR "\n";

            $machine->{ipv4} = $instance->ip_address;
            $machine->{ipv6} = $instance->dns_name_v6; # actually its public IPv6 address
            $machine->{privateIpv4} = $instance->private_ip_address;
            $machine->{dnsName} = $instance->dns_name;
            $machine->{privateDnsName} = $instance->private_dns_name;
            $machine->{instanceRunning} = 1;

            my $addr = $instance->dns_name_v6 || $instance->ip_address || die "don't know how to reach ‘$name’";
            print STDERR "started instance with IP address $addr\n";
                
            addToKnownHosts $machine;
            
            writeState;
        }

        if ($machine->{targetEnv} eq "virtualbox" && !exists $machine->{disk}) {
            my $vmDir = "$ENV{'HOME'}/VirtualBox VMs/$machine->{vmId}";
            die "don't know where VirtualBox is storing its VMs!\n" unless -d $vmDir;

            my $disk = "$vmDir/disk1.vdi";

            # If the base image is a derivation, build it now.XXX
            my $baseImage = $machine->{baseImage};
            if ($baseImage eq "drv") {
                # !!! ‘baseImage’ should be a temporary GC root until we've cloned it.
                $baseImage = `nix-build --show-trace '<charon/eval-machine-info.nix>' --arg networkExprs '[ @{$state->{networkExprs}} ]' -A nodes.'$name'.config.deployment.virtualbox.baseImage`;
                die "unable to build base image" unless $? == 0;
                chomp $baseImage;
            }

            system "VBoxManage clonehd '$baseImage' '$disk'";
            die "unable to copy VirtualBox disk: $?" unless $? == 0;
            
            $machine->{disk} = $disk;
            writeState;
        }

        if ($machine->{targetEnv} eq "virtualbox" && !$machine->{diskAttached}) {
            system "VBoxManage storagectl '$machine->{vmId}' --name SATA --add sata --sataportcount 2 --bootable on --hostiocache on";
            die "unable to create SATA controller on VirtualBox VM: $?" unless $? == 0;
                
            system "VBoxManage storageattach '$machine->{vmId}' --storagectl SATA --port 0 --device 0 --type hdd --medium '$machine->{disk}'";
            die "unable to attach disk to VirtualBox VM: $?" unless $? == 0;

            $machine->{diskAttached} = 1;
            writeState;
        }

        if ($machine->{targetEnv} eq "virtualbox" && !$machine->{instanceRunning}) {
            system("VBoxManage modifyvm '$machine->{vmId}' --memory 512 --vram 10"
                   . " --nictype1 virtio --nictype2 virtio --nic2 hostonly --hostonlyadapter2 vboxnet0"
                   . " --nestedpaging off");
            die "unable to set memory size of VirtualBox VM: $?" unless $? == 0;

            system "VBoxManage startvm '$machine->{vmId}'";
            die "unable to start VirtualBox VM: $?" unless $? == 0;

            $machine->{instanceRunning} = 1;
            writeState;
        }

        if ($machine->{targetEnv} eq "virtualbox" && !$machine->{privateIpv4}) {
            print STDERR "waiting for IP address of ‘$name’...";
            while (1) {
                my $res = `VBoxManage guestproperty get '$machine->{vmId}' /VirtualBox/GuestInfo/Net/1/V4/IP`;
                if ($? == 0 && $res =~ /Value: (.*)$/) {
                    my $ip = $1;
                    print STDERR " $ip\n";
                    $machine->{privateIpv4} = $ip;
                    $machine->{ipv4} = $ip;
                    last;
                }
                sleep 5;
                print STDERR ".";
            }
            addToKnownHosts $machine;
            writeState;
        }
    }

    # Wait until the machines are up.
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
}


sub buildConfigs {
    # So now that we know the hostnames / IP addresses of all
    # machines, we can generate the physical network configuration
    # that can be stacked on top of the user-supplied network
    # configuration.
    my $physicalExpr = "$tmpDir/physical.nix";
    write_file($physicalExpr, createPhysicalSpec());
    
    print STDERR "building all machine configurations...\n";
    my $vmsPath = `nix-build --show-trace '<charon/eval-machine-info.nix>' --arg networkExprs '[ @{$state->{networkExprs}} $physicalExpr ]' -A machines`;
    die "unable to build all machine configurations" unless $? == 0;
    chomp $vmsPath;
    return $vmsPath;
}


sub copyPathsBetween {
    my ($sourceName, $sourceMachine, $targetName, $targetMachine, $paths) = @_;
    print STDERR "    copying from ‘$sourceName’ to ‘$targetName’...\n";

    my $sourceSshName = sshName($sourceName, $sourceMachine);
    my $targetSshName = sshName($targetName, $targetMachine);

    # If the machines are in the same cloud (e.g. EC2 region), then
    # use the source's internal IP address, because that's typically
    # cheaper.
    # !!! Generalize.
    if ($sourceMachine->{targetEnv} eq "ec2" &&
        $targetMachine->{targetEnv} eq "ec2" &&
        $sourceMachine->{ec2}->{controller} eq $targetMachine->{ec2}->{controller})
    {
        $sourceSshName = $sourceMachine->{privateIpv4} if defined $sourceMachine->{privateIpv4};
    }

    print STDERR "      i.e. ‘$targetSshName’ will copy from ‘$sourceSshName’\n";

    system("ssh -x root\@$targetSshName 'NIX_SSHOPTS=\"-o StrictHostKeyChecking=no\" nix-copy-closure --gzip --from root\@$sourceSshName " . join(" ", $paths->elements()) . "'");
    # This is only a warning because we have a fall-back
    # nix-copy-closure from the distributor machine at the end.
    warn "warning: unable to copy paths from machine ‘$sourceName’ to ‘$targetName’\n" unless $? == 0;
}


sub copyClosures {
    my ($vmsPath) = @_;

    # !!! Should copy closures in parallel.
    foreach my $name (sort (keys %{$spec->{machines}})) {
        my $machine = $state->{machines}->{$name};
        $stores->{$name} = Set::Object->new() unless defined $stores->{$name};
        
        my $toplevel = readlink "$vmsPath/$name" or die;
        
        next if $stores->{$name}->has($toplevel);
            
        print STDERR "copying closure to machine ‘$name’...\n";
        
        #my @closure = reverse(topoSortPaths(computeFSClosure(0, 0, $toplevel)));
        my @closure = split ' ', `nix-store -qR '$toplevel'`;
        die "cannot get closure of ‘$toplevel’\n" if $? != 0;

        print STDERR "  ", scalar @closure, " paths in closure $toplevel\n";

        $stores->{$name} = Set::Object->new() unless defined $stores->{$name};

        # As an optimisation, copy paths from other machines within
        # the same cloud.  This is typically faster and cheaper (e.g.,
        # Amazon doesn't charge for transfers within a region).  We do
        # this in a loop: we select the machine that is cheapest
        # relative to the target machine and contains the most paths
        # still needed by the target.  Then we copy those paths.  This
        # is repeated until there are no paths left that can be
        # copied.
        if ($machine->{targetEnv} ne "virtualbox") {
            my $pathsRemaining = Set::Object->new(@closure);
            my $round = 0;

            $pathsRemaining = $pathsRemaining - $stores->{$name};

            while ($pathsRemaining->size() > 0) {
                print STDERR "  round $round, ", $pathsRemaining->size(), " remaining...\n";
                $round++;

                my @candidates = ();

                # For each other machine, determine how many of the
                # remaining paths it already has (the intersection),
                # as well as the cost factor for copying from that
                # machine to the target.
                foreach my $name2 (sort (keys %{$spec->{machines}})) {
                    my $machine2 = $state->{machines}->{$name2};
                    next if $name eq $name2;
                    next unless defined $stores->{$name2};
                    print STDERR "    considering copying from $name2\n";
                    my $intersection = $pathsRemaining * $stores->{$name2};
                    print STDERR "      ", $intersection->size(), " paths in common\n";
                    next if $intersection->size() == 0;
                    push @candidates, { name => $name2, machine => $machine2, intersection => $intersection };
                    # !!! compute a cost factor
                }

                last if scalar @candidates == 0;

                @candidates = sort { $b->{intersection}->size() <=> $a->{intersection}->size()} @candidates;

                print STDERR "    selected machine $candidates[0]->{name}\n";

                copyPathsBetween($candidates[0]->{name}, $candidates[0]->{machine},
                                 $name, $machine, $candidates[0]->{intersection});

                $pathsRemaining = $pathsRemaining - $candidates[0]->{intersection};
            }
        }

        print STDERR "    copying from distributor to ‘$name’...\n";
        
        my $sshName = sshName($name, $machine);
        my @sshFlags = sshFlags($name, $machine);
        system "NIX_SSHOPTS='@sshFlags' nix-copy-closure --gzip --to root\@$sshName $toplevel";
        die "unable to copy closure to machine ‘$name’" unless $? == 0;

        $stores->{$name}->insert(@closure);
        
        $machine->{store} = [ sort { $a cmp $b } $stores->{$name}->elements() ];
        writeState;
    }
}


sub activateConfigs {
    my ($vmsPath) = @_;

    # Store the store path to the VMs in the deployment state.  This
    # allows ‘--info’ to show whether machines have an outdated
    # configuration.
    $state->{vmsPath} = $vmsPath;

    foreach my $name (sort (keys %{$spec->{machines}})) {
        print STDERR "activating new configuration on machine ‘$name’...\n";
        my $machine = $state->{machines}->{$name};

        my $toplevel = readlink "$vmsPath/$name" or die;
        my $sshName = sshName($name, $machine);
        my @sshFlags = sshFlags($name, $machine);
        system "ssh @sshFlags root\@$sshName nix-env -p /nix/var/nix/profiles/system --set $toplevel \\; /nix/var/nix/profiles/system/bin/switch-to-configuration switch";
        if ($? != 0) {
            # !!! do a rollback
            die "unable to activate new configuration on machine ‘$name’";
        }

        $machine->{vmsPath} = $vmsPath;
        $machine->{toplevel} = $toplevel;
        writeState;
    }
}


sub opShowPhysical {
    noArgs;
    readState();
    evalMachineInfo();
    print createPhysicalSpec();
}


main;


__END__

=head1 NAME

charon - NixOS network deployment tool

=head1 SYNOPSIS

B<charon> [<operation>] [<options>]

Operations:
    
  --deploy              deploy the network configuration (default)
  --create              create a state file
  --info                query a state file
  --check               check the state of the machines in the network
  --destroy             destroy all virtual machines in the network
  --help                show a brief help message
  --version             show Charon's version number

Options:

  -s / --state          path to state file
  -k / --kill-obsolete  kill obsolete virtual machines
  --debug               show debug information

=cut
