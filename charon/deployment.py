# -*- coding: utf-8 -*-

import sys
import os.path
import subprocess
import json
import string
import tempfile
import atexit
import shutil
import threading
import exceptions
import errno
from xml.etree import ElementTree
import charon.backends
import charon.parallel
import re
from datetime import datetime
import getpass
import sqlite3


def _open_database(db_file, exclusive=False):
    if os.path.splitext(db_file)[1] != '.charon':
        raise Exception("state file ‘{0}’ should have extension ‘.charon’".format(db_file))
    db = sqlite3.connect(db_file, timeout=60, check_same_thread=False) # FIXME
    c = db.cursor()

    if exclusive: c.execute("pragma locking_mode = exclusive")
    c.execute("pragma journal_mode = wal")
    c.execute("pragma foreign_keys = 1")

    c.execute(
        '''create table if not exists Deployments(
             uuid text primary key
           );''')

    c.execute(
        '''create table if not exists DeploymentAttrs(
             deployment text not null,
             name text not null,
             value text not null,
             primary key(deployment, name),
             foreign key(deployment) references Deployments(uuid) on delete cascade
           );''')

    c.execute(
        '''create table if not exists Machines(
             id integer primary key autoincrement,
             deployment text not null,
             name text not null,
             type text not null,
             foreign key(deployment) references Deployments(uuid) on delete cascade
           );''')

    c.execute(
        '''create table if not exists MachineAttrs(
             machine integer not null,
             name text not null,
             value text not null,
             primary key(machine, name),
             foreign key(machine) references Machines(id) on delete cascade
           );''')

    return db


def _find_deployment(db, uuid=None):
    c = db.cursor()
    if not uuid:
        c.execute("select uuid from Deployments")
        res = c.fetchall()
        if len(res) == 0: return None
        if len(res) > 1:
            raise Exception("state file contains multiple deployments, so you should specify which one to use using ‘--uuid’")
        return Deployment(db, res[0][0])
    raise Exception("not implemented")


def create_deployment(db_file):
    """Create a new deployment."""
    db = _open_database(db_file)
    import uuid
    uuid = str(uuid.uuid1())
    db.execute("insert into Deployments(uuid) values (?)", (uuid,))
    db.commit()
    return Deployment(db, uuid)


def open_deployment(db_file, ignore_missing=False, exclusive=False):
    """Open an existing deployment."""
    db = _open_database(db_file, exclusive=exclusive)
    deployment = _find_deployment(db)
    if deployment: return deployment
    if ignore_missing: return None
    raise Exception("could not find specified deployment in state file ‘{0}’".format(db_file))


class Deployment(object):
    """Charon top-level deployment manager."""

    nix_exprs = charon.util.attr_property("nixExprs", [], 'json')
    nix_path = charon.util.attr_property("nixPath", [], 'json')
    args = charon.util.attr_property("args", {}, 'json')
    description = charon.util.attr_property("description", None)
    configs_path = charon.util.attr_property("configsPath", None)
    rollback_enabled = charon.util.attr_property("rollbackEnabled", False)

    def __init__(self, db, uuid, log_file=sys.stderr):
        self._db = db
        self.uuid = uuid

        self._last_log_prefix = None
        self.auto_response = None
        self.extra_nix_path = []

        self._log_lock = threading.Lock()

        self.expr_path = os.path.dirname(__file__) + "/../../../../share/nix/charon"
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

        self.tempdir = tempfile.mkdtemp(prefix="charon-tmp")
        atexit.register(lambda: shutil.rmtree(self.tempdir))

        self._log_file = log_file

        self.machines = {}
        self.active = {}
        c = self._db.cursor()
        c.execute("select id, name, type from Machines where deployment = ?", (self.uuid,))
        for (id, name, type) in c.fetchall():
            m = charon.backends.create_state(self, type, name, id, self._log_file)
            self.machines[name] = m
            if not m.obsolete: self.active[name] = m
        self.set_log_prefixes()


    def _set_attrs(self, attrs, commit=True):
        """Update deployment attributes in the state file."""
        c = self._db.cursor()
        for n, v in attrs.iteritems():
            if v == None:
                c.execute("delete from DeploymentAttrs where deployment = ? and name = ?", (self.uuid, n))
            else:
                c.execute("insert or replace into DeploymentAttrs(deployment, name, value) values (?, ?, ?)",
                          (self.uuid, n, v))
        if commit: self._db.commit()


    def _set_attr(self, name, value, commit=True):
        """Update one deployment attribute in the state file."""
        self._set_attrs({name: value}, commit=commit)


    def _get_attr(self, name, default=charon.util.undefined):
        """Get a deployment attribute from the state file."""
        c = self._db.cursor()
        c.execute("select value from DeploymentAttrs where deployment = ? and name = ?", (self.uuid, name))
        row = c.fetchone()
        if row != None: return row[0]
        if default != charon.util.undefined: return default
        raise Exception("deployment attribute ‘{0}’ missing from state file".format(name))


    def delete_machine(self, m):
        del self.machines[m.name]
        self.active.pop(m.name, None)
        self._db.execute("delete from Machines where deployment = ? and id = ?", (self.uuid, m.id))
        self._db.commit()


    def log(self, msg):
        with self._log_lock:
            if self._last_log_prefix != None:
                self._log_file.write("\n")
                self._last_log_prefix = None
            self._log_file.write(msg + "\n")


    def log_start(self, prefix, msg):
        with self._log_lock:
            if self._last_log_prefix != prefix:
                if self._last_log_prefix != None:
                    self._log_file.write("\n")
                self._log_file.write(prefix)
            self._log_file.write(msg)
            self._last_log_prefix = prefix


    def log_end(self, prefix, msg):
        with self._log_lock:
            last = self._last_log_prefix
            self._last_log_prefix = None
            if last != prefix:
                if last != None:
                    self._log_file.write("\n")
                if msg == "": return
                self._log_file.write(prefix)
            self._log_file.write(msg + "\n")


    def set_log_prefixes(self):
        max_len = max([len(m.name) for m in self.machines.itervalues()] or [0])
        for m in self.machines.itervalues():
            m.set_log_prefix(max_len)


    def confirm(self, question):
        while True:
            with self._log_lock:
                if self._last_log_prefix != None:
                    self._log_file.write("\n")
                    self._last_log_prefix = None
                self._log_file.write(charon.util.ansi_warn("warning: {0} (y/N) ".format(question), outfile=self._log_file))
                if self.auto_response != None:
                    self._log_file.write("{0}\n".format(self.auto_response))
                    return self.auto_response == "y"
                response = sys.stdin.readline()
                if response == "": return False
                response = response.rstrip().lower()
                if response == "y": return True
                if response == "n" or response == "": return False


    def _eval_flags(self):
        return sum([["-I", x] for x in (self.extra_nix_path + self.nix_path)], [])


    def set_arg(self, name, value):
        """Set a persistent argument to the deployment specification."""
        assert isinstance(name, str)
        assert isinstance(value, str)
        args = self.args
        args[name] = value
        self.args = args


    def set_argstr(self, name, value):
        """Set a persistent argument to the deployment specification."""
        assert isinstance(value, str)
        s = ""
        for c in value:
            if c == '"': s += '\\"'
            elif c == '\\': s += '\\\\'
            elif c == '$': s += '\\$'
            else: s += c
        self.set_arg(name, '"' + s + '"')


    def unset_arg(self, name):
        """Unset a persistent argument to the deployment specification."""
        assert isinstance(name, str)
        args = self.args
        args.pop(name, None)
        self.args = args


    def _args_to_attrs(self):
        return "{ " + string.join([n + " = " + v + "; " for n, v in self.args.iteritems()]) + "}"


    def evaluate(self):
        """Evaluate the Nix expressions belonging to this deployment into a deployment specification."""

        self.definitions = {}

        try:
            xml = subprocess.check_output(
                ["nix-instantiate", "-I", "charon=" + self.expr_path]
                + self._eval_flags() +
                ["--eval-only", "--show-trace", "--xml", "--strict",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "checkConfigurationOptions", "false",
                 "--arg", "networkExprs", "[ " + string.join(self.nix_exprs) + " ]",
                 "--arg", "args", self._args_to_attrs(),
                 "-A", "info"], stderr=self._log_file)
        except subprocess.CalledProcessError:
            raise NixEvalError

        tree = ElementTree.fromstring(xml)

        # Extract global deployment attributes.
        info = tree.find("attrs/attr[@name='network']")
        assert info != None
        elem = info.find("attrs/attr[@name='description']/string")
        self.description = elem.get("value") if elem != None else None
        elem = info.find("attrs/attr[@name='enableRollback']/bool")
        self.rollback_enabled = elem != None and elem.get("value") == "true"

        # Extract machine information.
        machines = tree.find("attrs/attr[@name='machines']/attrs")

        for m in machines.findall("attr"):
            defn = charon.backends.create_definition(m)
            self.definitions[defn.name] = defn


    def evaluate_option_value(self, machine_name, option_name, xml=False):
        """Evaluate a single option of a single machine in the deployment specification."""

        try:
            return subprocess.check_output(
                ["nix-instantiate", "-I", "charon=" + self.expr_path]
                + self._eval_flags() +
                ["--eval-only", "--show-trace", "--strict",
                 "<charon/eval-machine-info.nix>",
                 "--arg", "checkConfigurationOptions", "false",
                 "--arg", "networkExprs", "[ " + string.join(self.nix_exprs) + " ]",
                 "--arg", "args", self._args_to_attrs(),
                 "-A", "nodes.{0}.config.{1}".format(machine_name, option_name)]
                + (["--xml"] if xml else []),
                stderr=self._log_file)
        except subprocess.CalledProcessError:
            raise NixEvalError


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
                authorized_keys[m2.name].append('"' + m.public_vpn_key + '"')
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
            lines.append("  \"" + m.name + "\" = { config, pkgs, ... }: {")
            lines.extend(lines_per_machine[m.name])
            if authorized_keys[m.name]:
                lines.append('    users.extraUsers.root.openssh.authorizedKeys.keys = [ {0} ];'.format(" ".join(authorized_keys[m.name])))
                lines.append('    services.openssh.extraConfig = "PermitTunnel yes\\n";')
            lines.append('    boot.kernelModules = [ {0} ];'.format(" ".join(kernel_modules[m.name])))
            lines.append('    networking.extraHosts = "{0}\\n";'.format('\\n'.join([hosts[m.name][m2] + " " + m2 for m2 in hosts[m.name]])))
            lines.append("  };\n")
            return "\n".join(lines)

        return "".join(["{\n"] + [emit_machine(m) for m in self.active.itervalues()] + ["}\n"])


    def get_profile(self):
        return "/nix/var/nix/profiles/per-user/{0}/charon/{1}".format(getpass.getuser(), self.uuid)


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
                ["nix-build", "-I", "charon=" + self.expr_path, "--show-trace"]
                + self._eval_flags() +
                ["<charon/eval-machine-info.nix>",
                 "--arg", "networkExprs", "[ " + " ".join(self.nix_exprs + [phys_expr]) + " ]",
                 "--arg", "args", self._args_to_attrs(),
                 "--arg", "names", "[ " + " ".join(names) + " ]",
                 "-A", "machines", "-o", self.tempdir + "/configs"]
                + (["--dry-run"] if dry_run else []), stderr=self._log_file).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        if self.rollback_enabled:
            profile = self.get_profile()
            dir = os.path.dirname(profile)
            if not os.path.exists(dir): os.makedirs(dir, 0755)
            if subprocess.call(["nix-env", "-p", profile, "--set", configs_path]) != 0:
                raise Exception("cannot update profile ‘{0}’".format(profile))

        return configs_path


    def copy_closures(self, configs_path, include, exclude, max_concurrent_copy):
        """Copy the closure of each machine configuration to the corresponding machine."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.log("copying closure...")
            m.new_toplevel = os.path.realpath(configs_path + "/" + m.name)
            if not os.path.exists(m.new_toplevel):
                raise Exception("can't find closure of machine ‘{0}’".format(m.name))
            m.copy_closure_to(m.new_toplevel)

        charon.parallel.run_tasks(
            nr_workers=max_concurrent_copy,
            tasks=self.active.itervalues(), worker_fun=worker)


    def activate_configs(self, configs_path, include, exclude, allow_reboot, check):
        """Activate the new configuration on a machine."""

        def worker(m):
            if not should_do(m, include, exclude): return

            try:
                res = m.run_command(
                    # Set the system profile to the new configuration.
                    "set -e; nix-env -p /nix/var/nix/profiles/system --set " + m.new_toplevel + "; " +
                    # In case the switch crashes the system, do a sync.
                    "sync; " +
                    # Run the switch script.  This will also update the
                    # GRUB boot loader.  For performance, skip this step
                    # if the new config is already current.
                    ("cur=$(readlink /run/current-system); " +
                     'if [ "$cur" != ' + m.new_toplevel + " ]; then /nix/var/nix/profiles/system/bin/switch-to-configuration switch; fi"
                     if not check else "/nix/var/nix/profiles/system/bin/switch-to-configuration switch"),
                    check=False)
                if res != 0 and res != 100:
                    raise Exception("unable to activate new configuration")
                if res == 100:
                    if not allow_reboot:
                        raise Exception("the new configuration requires a reboot to take effect (hint: use ‘--allow-reboot’)".format(m.name))
                    m.reboot_sync()
                    # FIXME: should check which systemd services
                    # failed to start after the reboot.

                # Record that we switched this machine to the new
                # configuration.
                m.cur_configs_path = configs_path
                m.cur_toplevel = m.new_toplevel

            except Exception as e:
                # This thread shouldn't throw an exception because
                # that will cause Charon to exit and interrupt
                # activation on the other machines.
                m.log(str(e))
                return m.name
            return None

        res = charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)
        failed = [x for x in res if x != None]
        if failed != []:
            raise Exception("activation of {0} of {1} machines failed (namely on {2})"
                            .format(len(failed), len(res), ", ".join(["‘{0}’".format(x) for x in failed])))


    def _get_free_machine_index(self):
        index = 0
        for m in self.machines.itervalues():
            if m.index != None and index <= m.index:
                index = m.index + 1
        return index


    def get_backups(self, include=[], exclude=[]):
        self.evaluate_active(include, exclude) # unnecessary?
        machine_backups = {}
        for m in self.active.itervalues():
            if should_do(m, include, exclude):
                machine_backups[m.name] = m.get_backups()

        # merging machine backups into network backups
        backup_ids = [b for bs in machine_backups.values() for b in bs.keys()]
        backups = {}
        for backup_id in backup_ids:
            backups[backup_id] = {}
            backups[backup_id]['machines'] = {}
            backups[backup_id]['info'] = []
            backups[backup_id]['status'] = 'complete'
            backup = backups[backup_id]
            for m in self.active.itervalues():
                if should_do(m, include, exclude):
                    backup['machines'][m.name] = machine_backups[m.name][backup_id]
                    backup['info'].extend(backup['machines'][m.name]['info'])
                    # status is always running when one of the backups is still running
                    if backup['machines'][m.name]['status'] != "complete" and backup['status'] != "running":
                        backup['status'] = backup['machines'][m.name]['status']
        return backups


    def backup(self, include=[], exclude=[]):
        self.evaluate_active(include, exclude) # unnecessary?
        backup_id = datetime.now().strftime("%Y%m%d%H%M%S");

        def worker(m):
            if not should_do(m, include, exclude): return
            ssh_name = m.get_ssh_name()
            res = subprocess.call(["ssh", "root@" + ssh_name] + m.get_ssh_flags() + ["sync"])
            if res != 0:
                m.log("Running sync failed on {0}.".format(m.name))
            m.backup(backup_id)

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


    def restore(self, include=[], exclude=[], backup_id=None):
        self.evaluate_active(include, exclude)
        def worker(m):
            if not should_do(m, include, exclude): return
            m.restore(self.definitions[m.name], backup_id)

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)
        self.deploy(include=include, exclude=exclude, check=True)


    def evaluate_active(self, include=[], exclude=[], kill_obsolete=False):
        self.evaluate()

        # Create state objects for all defined machines.
        for m in self.definitions.itervalues():
            if m.name not in self.machines:
                c = self._db.cursor()
                c.execute("select 1 from Machines where deployment = ? and name = ?", (self.uuid, m.name))
                if len(c.fetchall()) != 0:
                    raise Exception("machine already exists in database!")
                c.execute("insert into Machines(deployment, name, type) values (?, ?, ?)",
                          (self.uuid, m.name, m.get_type()))
                id = c.lastrowid
                self.machines[m.name] = charon.backends.create_state(self, m.get_type(), m.name, id, self._log_file)

        self._db.commit()

        self.set_log_prefixes()

        # Determine the set of active machines.  (We can't just delete
        # obsolete machines from ‘self.machines’ because they contain
        # important state that we don't want to forget about.)
        self.active = {}
        for m in self.machines.values():
            if m.name in self.definitions:
                self.active[m.name] = m
                if m.obsolete:
                    self.log("machine ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.log("machine ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True
                if not should_do(m, include, exclude): continue
                if kill_obsolete and m.destroy(): self.delete_machine(m)


    def deploy(self, dry_run=False, build_only=False, create_only=False, copy_only=False,
               include=[], exclude=[], check=False, kill_obsolete=False,
               allow_reboot=False, max_concurrent_copy=5):
        """Perform the deployment defined by the deployment specification."""

        self.evaluate_active(include, exclude, kill_obsolete)

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
                m.send_keys()
                m.generate_vpn_key()
            charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)

        if create_only: return

        # Build the machine configurations.
        if dry_run:
            self.build_configs(dry_run=True, include=include, exclude=exclude)
            return

        # Record configs_path in the state so that the ‘info’ command
        # can show whether machines have an outdated configuration.
        self.configs_path = self.build_configs(include=include, exclude=exclude)

        if build_only: return

        # Copy the closures of the machine configurations to the
        # target machines.
        self.copy_closures(self.configs_path, include=include, exclude=exclude,
                           max_concurrent_copy=max_concurrent_copy)

        if copy_only: return

        # Active the configurations.
        self.activate_configs(self.configs_path, include=include, exclude=exclude,
                              allow_reboot=allow_reboot, check=check)


    def rollback(self, generation, include=[], exclude=[], check=False,
                 allow_reboot=False, max_concurrent_copy=5):
        if not self.rollback_enabled:
            raise Exception("rollback is not enabled for this network; please set ‘network.enableRollback’ to ‘true’ and redeploy"
                            )
        profile = self.get_profile()
        if subprocess.call(["nix-env", "-p", profile, "--switch-generation", str(generation)]) != 0:
            raise Exception("nix-env --switch-generation failed")

        self.configs_path = os.path.realpath(profile)
        assert os.path.isdir(self.configs_path)

        names = set()
        for filename in os.listdir(self.configs_path):
            if not os.path.islink(self.configs_path + "/" + filename): continue
            if should_do_n(filename, include, exclude) and filename not in self.machines:
                raise Exception("cannot roll back machine ‘{0}’ which no longer exists".format(filename))
            names.add(filename)

        # Update the set of active machines.
        self.active = {}
        for m in self.machines.values():
            if m.name in names:
                self.active[m.name] = m
                if m.obsolete:
                    self.log("machine ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.log("machine ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True

        self.copy_closures(self.configs_path, include=include, exclude=exclude,
                           max_concurrent_copy=max_concurrent_copy)

        self.activate_configs(self.configs_path, include=include, exclude=exclude,
                              allow_reboot=allow_reboot, check=check)


    def destroy_vms(self, include=[], exclude=[]):
        """Destroy all active or obsolete VMs."""

        def worker(m):
            if not should_do(m, include, exclude): return
            if m.destroy(): self.delete_machine(m)

        charon.parallel.run_tasks(nr_workers=len(self.machines), tasks=self.machines.values(), worker_fun=worker)


    def reboot_machines(self, include=[], exclude=[], wait=False):
        """Reboot all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            if wait:
                m.reboot_sync()
            else:
                m.reboot()

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


    def stop_machines(self, include=[], exclude=[]):
        """Stop all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.stop()

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


    def start_machines(self, include=[], exclude=[]):
        """Start all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.start()

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


    def is_valid_machine_name(self, name):
        p = re.compile('^\w+$')
        return not p.match(name) is None


    def rename(self, name, new_name):
        if not name in self.machines:
            raise Exception("machine {0} not found".format(name))
        if new_name in self.machines:
            raise Exception("machine with {0} already exists".format(new_name))
        if not self.is_valid_machine_name(new_name):
            raise Exception("{0} is not a valid machine identifier".format(new_name))

        self.log("renaming machine ‘{0}’ to ‘{1}’...".format(name, new_name))

        m = self.machines.pop(name)
        self.machines[new_name] = m
        # FIXME: update self.active

        self._db.execute("update Machines set name = ? where deployment = ? and id = ?", (new_name, self.uuid, m.id))
        self._db.commit()


    def send_keys(self, include=[], exclude=[]):
        """Send LUKS encryption keys to machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.send_keys()

        charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.active.itervalues(), worker_fun=worker)


class NixEvalError(Exception):
    pass


def should_do(m, include, exclude):
    return should_do_n(m.name, include, exclude)

def should_do_n(name, include, exclude):
    if name in exclude: return False
    if include == []: return True
    return name in include
