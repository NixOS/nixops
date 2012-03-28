# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import shutil
import boto.ec2
from charon.backends import MachineDefinition, MachineState
import charon.known_hosts


class EC2Definition(MachineDefinition):
    """Definition of an EC2 machine."""

    @classmethod
    def get_type(cls):
        return "ec2"
    
    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='ec2']/attrs")
        assert x is not None
        self.type = x.find("attr[@name='type']/string").get("value")
        self.region = x.find("attr[@name='region']/string").get("value")
        self.controller = x.find("attr[@name='controller']/string").get("value")
        self.ami = x.find("attr[@name='ami']/string").get("value")
        self.instance_type = x.find("attr[@name='instanceType']/string").get("value")
        self.key_pair = x.find("attr[@name='keyPair']/string").get("value")
        self.security_groups = [e.get("value") for e in x.findall("attr[@name='securityGroups']/list/string")]

    def make_state():
        return MachineState()


class EC2State(MachineState):
    """State of an EC2 machine."""

    @classmethod
    def get_type(cls):
        return "ec2"
    
    def __init__(self, depl, name):
        MachineState.__init__(self, depl, name)

        self._conn = None
        
        self._region = None
        self._zone = None
        self._controller = None
        self._ami = None
        self._instance_type = None
        self._key_pair = None
        self._security_groups = None
        
        self._instance_id = None
        self._public_ipv4 = None
        self._private_ipv4 = None
        self._tagged = False
        self._public_host_key = False
        self._public_vpn_key = False
        
        
    def serialise(self):
        x = MachineState.serialise(self)
        
        if self._region: x['region'] = self._region
        if self._zone: x['zone'] = self._zone
        if self._controller: x['controller'] = self._controller
        if self._ami: x['ami'] = self._ami
        if self._instance_type: x['instanceType'] = self._instance_type
        if self._key_pair: x['keyPair'] = self._key_pair
        if self._security_groups: x['securityGroups'] = self._security_groups
        
        if self._instance_id: x['vmId'] = self._instance_id
        if self._public_ipv4: x['ipv4'] = self._public_ipv4
        if self._private_ipv4: x['privateIpv4'] = self._private_ipv4
        if self._tagged: x['tagged'] = self._tagged
        if self._public_host_key: x['publicHostKey'] = self._public_host_key
        if self._public_vpn_key: x['publicVpnKey'] = self._public_vpn_key
        
        return x

    
    def deserialise(self, x):
        MachineState.deserialise(self, x)
        
        self._region = x.get('region', None)
        self._zone = x.get('zone', None)
        self._controller = x.get('controller', None)
        self._ami = x.get('ami', None)
        self._instance_type = x.get('instanceType', None)
        self._key_pair = x.get('keyPair', None)
        self._security_groups = x.get('securityGroups', None)
        
        self._instance_id = x.get('vmId', None)
        self._public_ipv4 = x.get('ipv4', None)
        self._private_ipv4 = x.get('privateIpv4', None)
        self._tagged = x.get('tagged', False)
        self._vpn_key_set = x.get('vpnKeySet', False)
        self._public_host_key = x.get('publicHostKey', None)
        self._public_vpn_key = x.get('publicVpnKey', None)

        
    def get_ssh_name(self):
        assert self._public_ipv4
        return self._public_ipv4

    def get_physical_spec(self, machines):
        lines = ['    require = [ <nixos/modules/virtualisation/amazon-config.nix> ];',
                 '    services.openssh.extraConfig = "PermitTunnel yes\\n";']
        authorized_keys = []
        tun = 0
        for m in machines.itervalues():
            tun = tun + 1
            if self != m and isinstance(m, EC2State) and self._region != m._region:
                # The two machines are in different regions, so they
                # can't talk directly to each other over their private
                # IP.  So create a VPN connection over their public
                # IPs to forward the private IPs.
                if self.name > m.name:
                    # Since it's a two-way tunnel, we only need to
                    # start it on one machine (for each pair of
                    # machines).  Pick the one that has the higher
                    # name (lexicographically).
                    lines.append('    jobs."vpn-to-{0}" = {{'.format(m.name))
                    lines.append('      startOn = "started network-interfaces";')
                    lines.append('      path = [ pkgs.nettools pkgs.openssh ];')
                    lines.append('      daemonType = "fork";')
                    lines.append('      exec = "ssh -i /root/.ssh/id_vpn -o StrictHostKeyChecking=no -f -x -w {0}:{0} {4} \'ifconfig tun{0} {2} {3} netmask 255.255.255.255; route add {2}/32 dev tun{0}\'";'
                                 .format(tun, m.name, self._private_ipv4, m._private_ipv4, m._public_ipv4))
                    lines.append('      postStart = "ifconfig tun{0} {2} {1} netmask 255.255.255.255; route add {2}/32 dev tun{0}";'
                                 .format(tun, self._private_ipv4, m._private_ipv4))
                    lines.append('    };')
                else:
                    # The other side just needs an authorized_keys entry.
                    authorized_keys.append('"' + m._public_vpn_key + '"')
        lines.append('    users.extraUsers.root.openssh.authorizedKeys.keys = [ {0} ];'.format(" ".join(authorized_keys)))
        return lines
    
    def show_type(self):
        s = MachineState.show_type(self)
        if m._zone or m._region: s = "{0} [{1}]".format(s, m._zone or m._region)
        return s

    @property
    def vm_id(self):
        return self._instance_id

    @property
    def public_ipv4(self):
        return self._public_ipv4

    @property
    def private_ipv4(self):
        return self._private_ipv4

    
    def address_to(self, m):
        if isinstance(m, EC2State):
            return m._private_ipv4
        return MachineState.address_to(self, m)

    
    def connect(self):
        if self._conn: return
        assert self._region
        access_key_id = os.environ.get('EC2_ACCESS_KEY') or os.environ.get('AWS_ACCESS_KEY_ID')
        if not access_key_id:
            raise Exception("please set $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")
        secret_access_key = os.environ.get('EC2_SECRET_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')
        if not secret_access_key:
            raise Exception("please set $EC2_SECRET_KEY or $AWS_SECRET_ACCESS_KEY")
        self._conn = boto.ec2.connect_to_region(
            region_name=self._region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

        
    def get_instance_by_id(self, instanceid):
        """Get instance object by instance id."""
        self.connect()
        reservations = self._conn.get_all_instances([instanceid])
        return reservations[0].instances[0]


    def _create_key_pair(self):
        key_dir = self.depl.tempdir + "/ssh-key-" + self.name
        os.mkdir(key_dir, 0700)
        fnull = open(os.devnull, 'w')
        res = subprocess.call(["ssh-keygen", "-t", "dsa", "-f", key_dir + "/key", "-N", '', "-C", "Charon auto-generated key"],
                              stdout=fnull)
        fnull.close()
        if res != 0: raise Exception("unable to generate an SSH key")
        f = open(key_dir + "/key"); private = f.read(); f.close()
        f = open(key_dir + "/key.pub"); public = f.read().rstrip(); f.close()
        shutil.rmtree(key_dir)
        return (private, public)

    
    def create(self, defn, check):
        assert isinstance(defn, EC2Definition)
        assert defn.type == "ec2"

        if not self._instance_id:
            print >> sys.stderr, "creating EC2 instance ‘{0}’ (AMI ‘{1}’, type ‘{2}’, region ‘{3}’)...".format(
                self.name, defn.ami, defn.instance_type, defn.region)

            self._region = defn.region
            self.connect()

            (private, public) = self._create_key_pair()

            user_data = "SSH_HOST_DSA_KEY_PUB:{0}\nSSH_HOST_DSA_KEY:{1}\n".format(public, private.replace("\n", "|"))

            reservation = self._conn.run_instances(
                image_id=defn.ami,
                instance_type=defn.instance_type,
                key_name=defn.key_pair,
                security_groups=defn.security_groups,
                user_data=user_data)

            assert len(reservation.instances) == 1

            instance = reservation.instances[0]

            self._instance_id = instance.id
            self._controller = defn.controller
            self._ami = defn.ami
            self._instance_type = defn.instance_type
            self._key_pair = defn.key_pair
            self._security_groups = defn.security_groups
            self._zone = instance.placement
            self._public_host_key = public
            
            self.write()

        if not self._tagged or check:
            self.connect()
            self._conn.create_tags(
                [self._instance_id],
                {'Name': "{0} [{1}]".format(self.depl.description, self.name),
                 'CharonNetworkUUID': str(self.depl.uuid),
                 'CharonMachineName': self.name})
            self._tagged = True
            self.write()

        if not self._private_ipv4 or check:
            instance = None
            sys.stderr.write("waiting for IP address of ‘{0}’... ".format(self.name))
            while True:
                instance = self.get_instance_by_id(self._instance_id)
                sys.stderr.write("[{0}] ".format(instance.state))
                if instance.private_ip_address: break
                time.sleep(3)
            sys.stderr.write("{0} / {1}\n".format(instance.ip_address, instance.private_ip_address))

            charon.known_hosts.add(instance.ip_address, self._public_host_key)
            
            self._private_ipv4 = instance.private_ip_address
            self._public_ipv4 = instance.ip_address
            self.write()

        # !!! Wait until the machine is reachable via SSH.
            
        if not self._public_vpn_key:
            (private, public) = self._create_key_pair()
            f = open(self.depl.tempdir + "/id_vpn-" + self.name, "w+")
            f.write(private)
            f.seek(0)
            res = subprocess.call(
                ["ssh", "-x", "root@" + self.get_ssh_name()]
                + self.get_ssh_flags() +
                ["umask 077 && mkdir -p /root/.ssh && cat > /root/.ssh/id_vpn"],
                stdin=f)
            f.close()
            if res != 0: raise Exception("unable to upload VPN key to ‘{0}’".format(self.name))
            self._public_vpn_key = public
            self.write()


    def destroy(self):
        print >> sys.stderr, "destroying EC2 instance ‘{0}’...".format(self.name)

        instance = self.get_instance_by_id(self._instance_id)
        instance.terminate()
