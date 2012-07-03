# -*- coding: utf-8 -*-

import sys
import os.path
import subprocess
import json
import uuid
import string
import tempfile
import atexit
import shutil
import threading
import fcntl
import exceptions
import errno
from xml.etree import ElementTree
import charon.backends
import charon.parallel
import re

class Deployment:
    """Charon top-level deployment manager."""

    def __init__(self, state_file, create=False, nix_exprs=[], lock=True):
        self.state_file = os.path.abspath(state_file)
        self.machines = { }
        self._machine_state = { }
        self.active = { }
        self.configs_path = None
        self.description = "Unnamed Charon network"
        self._last_log_prefix = None
        self.auto_response = None
        
        self._state_lock = threading.Lock()
        self._log_lock = threading.Lock()
            
        self.expr_path = os.path.dirname(__file__) + "/../../../../share/nix/charon"
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

        if lock:
            self._state_file_lock = open(self.state_file + ".lock", "w+")
            try:
                fcntl.lockf(self._state_file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except exceptions.IOError as e:
                if e.errno != errno.EAGAIN: raise
                self.log("waiting for exclusive lock on ‘{0}’...".format(self.state_file))
                fcntl.lockf(self._state_file_lock, fcntl.LOCK_EX)

        if create:
            if os.path.exists(self.state_file):
                self.load_state()
            else:
                self.uuid = uuid.uuid1()
            self.nix_exprs = [os.path.abspath(x) for x in nix_exprs]
        else:
            self.load_state()

        self.tempdir = tempfile.mkdtemp(prefix="charon-tmp")
        atexit.register(lambda: shutil.rmtree(self.tempdir))


    def load_state(self):
        """Read the current deployment state from the state file."""
        f = open(self.state_file, 'r')
        state = json.load(f)
        self.nix_exprs = state['networkExprs']
        self.uuid = uuid.UUID(state['uuid'])
        self.description = state.get('description', self.description)
        self.machines = { }
        self._machine_state = { }
        self.configs_path = state.get('vmsPath', None)
        for n, v in state['machines'].iteritems():
            self.machines[n] = charon.backends.create_state(self, v['targetEnv'], n)
            self.machines[n].deserialise(v)
            self._machine_state[n] = v
        self.set_log_prefixes()
        
            
    def write_state(self):
        """Write the current deployment state to the state file in JSON format."""
        state = {'networkExprs': self.nix_exprs,
                 'uuid': str(self.uuid),
                 'description': self.description,
                 'machines': self._machine_state}
        if self.configs_path: state['vmsPath'] = self.configs_path
        tmp = self.state_file + ".tmp"
        f = open(tmp, 'w')
        json.dump(state, f, indent=2)
        f.close()
        os.rename(tmp, self.state_file)


    def update_machine_state(self, m):
        with self._state_lock:
            self._machine_state[m.name] = m.serialise()
            self.write_state()


    def delete_machine(self, m):
        with self._state_lock:
            del self.machines[m.name]
            if m.name in self._machine_state: del self._machine_state[m.name]
            if m.name in self.active: del self.active[m.name]
            self.write_state()


    def log(self, msg):
        with self._log_lock:
            if self._last_log_prefix != None:
                sys.stderr.write("\n")
                self._last_log_prefix = None
            sys.stderr.write(msg + "\n")


    def log_start(self, prefix, msg):
        with self._log_lock:
            if self._last_log_prefix != prefix:
                if self._last_log_prefix != None:
                    sys.stderr.write("\n")
                sys.stderr.write(prefix)
            sys.stderr.write(msg)
            self._last_log_prefix = prefix
        

    def log_end(self, prefix, msg):
        with self._log_lock:
            last = self._last_log_prefix
            self._last_log_prefix = None
            if last != prefix:
                if last != None:
                    sys.stderr.write("\n")
                if msg == "": return
                sys.stderr.write(prefix)
            sys.stderr.write(msg + "\n")


    def set_log_prefixes(self):
        max_len = max([len(m.name) for m in self.machines.itervalues()] or [0])
        for m in self.machines.itervalues():
            m.set_log_prefix(max_len)


    def confirm(self, question):
        while True:
            with self._log_lock:
                if self._last_log_prefix != None:
                    sys.stderr.write("\n")
                    self._last_log_prefix = None
                sys.stderr.write(charon.util.ansi_warn("warning: {0} (y/N) ".format(question)))
                if self.auto_response != None:
                    sys.stderr.write("{0}\n".format(self.auto_response))
                    return self.auto_response == "y"
                response = sys.stdin.readline()
                if response == "": return False
                response = response.rstrip().lower()
                if response == "y": return True
                if response == "n" or response == "": return False


    def evaluate(self):
        """Evaluate the Nix expressions belonging to this deployment into a deployment model."""

        self.definitions = {}

        try:
            xml = subprocess.check_output(
                ["nix-instantiate", "-I", "charon=" + self.expr_path,
                 "--eval-only", "--show-trace", "--xml", "--strict",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "networkExprs", "[ " + string.join(self.nix_exprs) + " ]",
                 "-A", "info"])
        except subprocess.CalledProcessError:
            raise NixEvalError

        tree = ElementTree.fromstring(xml)

        # Extract global deployment attributes.
        info = tree.find("attrs/attr[@name='network']")
        assert info != None
        elem = info.find("attrs/attr[@name='description']/string")
        if elem != None: self.description = elem.get("value")

        # Extract machine information.
        machines = tree.find("attrs/attr[@name='machines']/attrs")

        for m in machines.findall("attr"):
            defn = charon.backends.create_definition(m)
            self.definitions[defn.name] = defn


    def get_physical_spec(self):
        """Compute the contents of the Nix expression specifying the computed physical deployment attributes"""

        lines_per_machine = {m.name: [] for m in self.active.itervalues()}
        authorized_keys = {m.name: [] for m in self.active.itervalues()}
        kernel_modules = {m.name: set() for m in self.active.itervalues()}
        hosts = {}

        for m in self.active.itervalues():
            hosts[m.name] = {}
            for m2 in self.active.itervalues():
                if m == m2: continue
                ip = m.address_to(m2)
                if ip: hosts[m.name][m2.name] = hosts[m.name][m2.name + "-unencrypted"] = ip

        def do_machine(m):
            defn = self.definitions[m.name]
            lines = lines_per_machine[m.name]
            
            lines.extend(m.get_physical_spec(self.active))

            # Emit configuration to realise encrypted peer-to-peer links.
            for m2_name in defn.encrypted_links_to:
                
                if m2_name not in self.active:
                    raise Exception("‘deployment.encryptedLinksTo’ in machine ‘{0}’ refers to an unknown machine ‘{1}’"
                                    .format(m.name, m2_name))
                m2 = self.active[m2_name]
                # Don't create two tunnels between a pair of machines.
                if m.name in self.definitions[m2.name].encrypted_links_to and m.name >= m2.name:
                    continue
                local_ipv4 = "192.168.105.{0}".format(m.index)
                remote_ipv4 = "192.168.105.{0}".format(m2.index)
                lines.append('    networking.p2pTunnels.{0} ='.format(m2.name))
                lines.append('      {{ target = "{0}-unencrypted";'.format(m2.name))
                lines.append('        localTunnel = {0};'.format(10000 + m2.index))
                lines.append('        remoteTunnel = {0};'.format(10000 + m.index))
                lines.append('        localIPv4 = "{0}";'.format(local_ipv4))
                lines.append('        remoteIPv4 = "{0}";'.format(remote_ipv4))
                lines.append('        privateKey = "/root/.ssh/id_charon_vpn";')
                lines.append('      }};'.format(m2.name))
                # FIXME: set up the authorized_key file such that ‘m’
                # can do nothing more than create a tunnel.
                authorized_keys[m2.name].append('"' + m._public_vpn_key + '"')
                kernel_modules[m.name].add('"tun"')
                kernel_modules[m2.name].add('"tun"')
                hosts[m.name][m2.name] = hosts[m.name][m2.name + "-encrypted"] = remote_ipv4
                hosts[m2.name][m.name] = hosts[m2.name][m.name + "-encrypted"] = local_ipv4
            
            private_ipv4 = m.private_ipv4
            if private_ipv4: lines.append('    networking.privateIPv4 = "{0}";'.format(private_ipv4))
            public_ipv4 = m.public_ipv4
            if public_ipv4: lines.append('    networking.publicIPv4 = "{0}";'.format(public_ipv4))
            
        for m in self.active.itervalues(): do_machine(m)

        def emit_machine(m):
            lines = []
            lines.append("  " + m.name + " = { config, pkgs, ... }: {")
            lines.extend(lines_per_machine[m.name])
            if authorized_keys[m.name]:
                lines.append('    users.extraUsers.root.openssh.authorizedKeys.keys = [ {0} ];'.format(" ".join(authorized_keys[m.name])))
                lines.append('    services.openssh.extraConfig = "PermitTunnel yes\\n";')
            lines.append('    boot.kernelModules = [ {0} ];'.format(" ".join(kernel_modules[m.name])))
            lines.append('    networking.extraHosts = "{0}\\n";'.format('\\n'.join([hosts[m.name][m2] + " " + m2 for m2 in hosts[m.name]])))
            lines.append("  };\n")
            return "\n".join(lines)

        return "".join(["{\n"] + [emit_machine(m) for m in self.active.itervalues()] + ["}\n"])
            

    def build_configs(self, include, exclude, dry_run=False):
        """Build the machine configurations in the Nix store."""

        self.log("building all machine configurations...")

        phys_expr = self.tempdir + "/physical.nix"
        f = open(phys_expr, "w")
        f.write(self.get_physical_spec())
        f.close()

        names = ['"' + m.name + '"' for m in self.active.itervalues() if should_do(m, include, exclude)]
        
        try:
            configs_path = subprocess.check_output(
                ["nix-build", "-I", "charon=" + self.expr_path, "--show-trace",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "networkExprs", "[ " + " ".join(self.nix_exprs + [phys_expr]) + " ]",
                 "--arg", "names", "[ " + " ".join(names) + " ]",
                 "-A", "machines", "-o", self.tempdir + "/configs"]
                + (["--dry-run"] if dry_run else [])).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        return configs_path
        

    def copy_closures(self, configs_path, include, exclude):
        """Copy the closure of each machine configuration to the corresponding machine."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.log("copying closure...")
            m.new_toplevel = os.path.realpath(configs_path + "/" + m.name)
            if not os.path.exists(m.new_toplevel):
                raise Exception("can't find closure of machine ‘{0}’".format(m.name))
            m.copy_closure_to(m.new_toplevel)

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)
            

    def activate_configs(self, configs_path, include, exclude):
        """Activate the new configuration on a machine."""

        def worker(m):
            if not should_do(m, include, exclude): return
            
            m.log("activating new configuration...")

            res = m.run_command(
                # Set the system profile to the new configuration.
                "set -e; nix-env -p /nix/var/nix/profiles/system --set " + m.new_toplevel + ";" +
                # Run the switch script.  This will also update the
                # GRUB boot loader.  For performance, skip this step
                # if the new config is already current.
                "cur=$(readlink /var/run/current-system); " +
                'if [ "$cur" != ' + m.new_toplevel + " ]; then /nix/var/nix/profiles/system/bin/switch-to-configuration switch; fi",
                check=False)
            if res != 0: raise Exception("unable to activate new configuration on machine ‘{0}’".format(m.name))

            # Record that we switched this machine to the new
            # configuration.
            m.cur_configs_path = configs_path
            m.cur_toplevel = m.new_toplevel
            self.update_machine_state(m)

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


    def _get_free_machine_index(self):
        index = 0
        for m in self.machines.itervalues():
            if m.index != None and index <= m.index:
                index = m.index + 1
        return index
            

    def deploy(self, dry_run=False, build_only=False, create_only=False,
               include=[], exclude=[], check=False, kill_obsolete=False,
               allow_reboot=False):
        """Perform the deployment defined by the deployment model."""

        self.evaluate()

        # Create state objects for all defined machines.
        for m in self.definitions.itervalues():
            if m.name not in self.machines:
                self.machines[m.name] = charon.backends.create_state(self, m.get_type(), m.name)

        self.set_log_prefixes()
        
        # Determine the set of active machines.  (We can't just delete
        # obsolete machines from ‘self.machines’ because they contain
        # important state that we don't want to forget about.)
        self.active = {}
        for m in self.machines.values():
            if m.name in self.definitions:
                self.active[m.name] = m
            else:
                self.log("machine ‘{0}’ is obsolete".format(m.name))
                if not should_do(m, include, exclude): continue
                if kill_obsolete and m.destroy(): self.delete_machine(m)

        # Assign each machine an index if it doesn't have one.
        for m in self.active.itervalues():
            if m.index == None:
                m.index = self._get_free_machine_index()
                
        self.set_log_prefixes()
        
        # Start or update the active machines.
        if not dry_run and not build_only:
            def worker(m):
                if not should_do(m, include, exclude): return
                defn = self.definitions[m.name]
                if m.get_type() != defn.get_type():
                    raise Exception("the type of machine ‘{0}’ changed from ‘{1}’ to ‘{2}’, which is currently unsupported"
                                    .format(m.name, m.get_type(), defn.get_type()))
                m.create(self.definitions[m.name], check=check, allow_reboot=allow_reboot)
                m.wait_for_ssh(check=check)
                m.generate_vpn_key()
            charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)

        if create_only: return
        
        # Build the machine configurations.
        if dry_run:
            self.build_configs(dry_run=True, include=include, exclude=exclude)
            return

        self.configs_path = self.build_configs(include=include, exclude=exclude)

        # Record configs_path in the state so that the ‘info’ command
        # can show whether machines have an outdated configuration.
        self.write_state()

        if build_only: return
        
        # Copy the closures of the machine configurations to the
        # target machines.
        self.copy_closures(self.configs_path, include=include, exclude=exclude)

        # Active the configurations.
        self.activate_configs(self.configs_path, include=include, exclude=exclude)

            
    def destroy_vms(self, include=[], exclude=[]):
        """Destroy all current or obsolete VMs."""

        def worker(m):
            if not should_do(m, include, exclude): return
            if m.destroy(): self.delete_machine(m)

        charon.parallel.run_tasks(nr_workers=len(self.machines), tasks=self.machines.values(), worker_fun=worker)
            

    def reboot_machines(self, include=[], exclude=[]):
        """Reboot all current or obsolete machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.reboot()

        charon.parallel.run_tasks(nr_workers=len(self.machines), tasks=self.machines.itervalues(), worker_fun=worker)


    def stop_machines(self, include=[], exclude=[]):
        """Stop all current or obsolete machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.stop()

        charon.parallel.run_tasks(nr_workers=len(self.machines), tasks=self.machines.itervalues(), worker_fun=worker)
            

    def start_machines(self, include=[], exclude=[]):
        """Start all current or obsolete machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.start()

        charon.parallel.run_tasks(nr_workers=len(self.machines), tasks=self.machines.itervalues(), worker_fun=worker)

    def is_valid_machine_name(self, name):
        p = re.compile('^\w+$')
        return not p.match(name) is None

    def rename(self, name, new_name):
        if not name in self.machines:
            raise Exception("Machine {0} not found.".format(name))
        if new_name in self.machines:
            raise Exception("Machine with {0} already exists.".format(new_name))
        if not self.is_valid_machine_name(new_name):
            raise Exception("{0} is not a valid machine identifier.".format(new_name))

        self.log("Renaming machine ‘{0}’ to ‘{1}’...".format(name, new_name))
        machine = self._machine_state.pop(name)
        self._machine_state[new_name] = machine
        self.write_state()

class NixEvalError(Exception):
    pass


def should_do(m, include, exclude):
    if m.name in exclude: return False
    if include == []: return True
    return m.name in include
