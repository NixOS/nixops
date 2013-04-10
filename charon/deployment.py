# -*- coding: utf-8 -*-

import sys
import os.path
import subprocess
import json
import string
import tempfile
import shutil
import threading
import exceptions
import errno
from xml.etree import ElementTree
import charon.backends
import charon.parallel
import charon.resources.ec2_keypair
import charon.resources.sqs_queue
import charon.resources.iam_role
import re
from datetime import datetime
import getpass
import sqlite3
import traceback
import glob
import fcntl
import itertools


debug = False


class Connection(sqlite3.Connection):

    def __init__(self, db_file, **kwargs):
        sqlite3.Connection.__init__(self, db_file, **kwargs)
        self.db_file = db_file
        self.nesting = 0
        self.lock = threading.RLock()

    # Implement Python's context management protocol so that "with db"
    # automatically commits or rolls back.  The difference with the
    # parent's "with" implementation is that we nest, i.e. a commit or
    # rollback is only done at the outer "with".
    def __enter__(self):
        self.lock.acquire()
        if self.nesting == 0:
            self.must_rollback = False
        self.nesting = self.nesting + 1

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if exception_type != None: self.must_rollback = True
        self.nesting = self.nesting - 1
        assert self.nesting >= 0
        if self.nesting == 0:
            if self.must_rollback:
                try:
                    self.rollback()
                except sqlite3.ProgrammingError:
                    pass
            else:
                self.commit()
        self.lock.release()


def _table_exists(c, table):
    c.execute("select 1 from sqlite_master where name = ? and type='table'", (table,));
    return c.fetchone() != None


current_schema = 3


def _create_schemaversion(c):
    c.execute(
        '''create table if not exists SchemaVersion(
             version integer not null
           );''')

    c.execute("insert into SchemaVersion(version) values (?)", (current_schema,))


def _create_schema(c):
    _create_schemaversion(c)

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
        '''create table if not exists Resources(
             id integer primary key autoincrement,
             deployment text not null,
             name text not null,
             type text not null,
             foreign key(deployment) references Deployments(uuid) on delete cascade
           );''')

    c.execute(
        '''create table if not exists ResourceAttrs(
             machine integer not null,
             name text not null,
             value text not null,
             primary key(machine, name),
             foreign key(machine) references Resources(id) on delete cascade
           );''')


def _upgrade_1_to_2(c):
    sys.stderr.write("updating database schema from version 1 to 2...\n")
    _create_schemaversion(c)


def _upgrade_2_to_3(c):
    sys.stderr.write("updating database schema from version 2 to 3...\n")
    c.execute("alter table Machines rename to Resources")
    c.execute("alter table MachineAttrs rename to ResourceAttrs")


def get_default_state_file():
    home = os.environ.get("HOME", "") + "/.charon"
    if not os.path.exists(home): os.makedirs(home, 0700)
    return os.environ.get("CHARON_STATE", home + "/deployments.charon")


def open_database(db_file):
    if os.path.splitext(db_file)[1] != '.charon':
        raise Exception("state file ‘{0}’ should have extension ‘.charon’".format(db_file))
    db = sqlite3.connect(db_file, timeout=60, check_same_thread=False, factory=Connection) # FIXME
    db.db_file = db_file

    db.execute("pragma journal_mode = wal")
    db.execute("pragma foreign_keys = 1")

    # FIXME: this is not actually transactional, because pysqlite (not
    # sqlite) does an implicit commit before "create table".
    with db:
        c = db.cursor()

        # Get the schema version.
        version = 0 # new database
        if _table_exists(c, 'SchemaVersion'):
            c.execute("select version from SchemaVersion")
            version = c.fetchone()[0]
        elif _table_exists(c, 'Deployments'):
            version = 1

        if version == current_schema:
            pass
        elif version == 0:
            _create_schema(c)
        elif version < current_schema:
            if version <= 1: _upgrade_1_to_2(c)
            if version <= 2: _upgrade_2_to_3(c)
            c.execute("update SchemaVersion set version = ?", (current_schema,))
        else:
            raise Exception("this Charon version is too old to deal with schema version {0}".format(version))

    return db


def query_deployments(db):
    """Return the UUIDs of all deployments in the database."""
    c = db.cursor()
    c.execute("select uuid from Deployments")
    res = c.fetchall()
    return [x[0] for x in res]


def _find_deployment(db, uuid=None):
    c = db.cursor()
    if not uuid:
        c.execute("select uuid from Deployments")
    else:
        c.execute("select uuid from Deployments d where uuid = ? or exists (select 1 from DeploymentAttrs where deployment = d.uuid and name = 'name' and value = ?)", (uuid, uuid))
    res = c.fetchall()
    if len(res) == 0: return None
    if len(res) > 1:
        raise Exception("state file contains multiple deployments, so you should specify which one to use using ‘-d’")
    return Deployment(db, res[0][0])


def create_deployment(db, uuid=None):
    """Create a new deployment."""
    if not uuid:
        import uuid
        uuid = str(uuid.uuid1())
    with db:
        db.execute("insert into Deployments(uuid) values (?)", (uuid,))
    return Deployment(db, uuid)


def open_deployment(db, uuid=None):
    """Open an existing deployment."""
    deployment = _find_deployment(db, uuid=uuid)
    if deployment: return deployment
    raise Exception("could not find specified deployment in state file ‘{0}’".format(db.db_file))


class Deployment(object):
    """Charon top-level deployment manager."""

    default_description = "Unnamed Charon network"

    name = charon.util.attr_property("name", None)
    nix_exprs = charon.util.attr_property("nixExprs", [], 'json')
    nix_path = charon.util.attr_property("nixPath", [], 'json')
    args = charon.util.attr_property("args", {}, 'json')
    description = charon.util.attr_property("description", default_description)
    configs_path = charon.util.attr_property("configsPath", None)
    rollback_enabled = charon.util.attr_property("rollbackEnabled", False)

    def __init__(self, db, uuid, log_file=sys.stderr):
        self._db = db
        self.uuid = uuid

        self._last_log_prefix = None
        self.auto_response = None
        self.extra_nix_path = []
        self.extra_nix_flags = []
        self.nixos_version_suffix = None

        self._log_lock = threading.Lock()
        self._log_file = log_file

        self._lock_file_path = None

        self.expr_path = os.path.dirname(__file__) + "/../../../../../share/nix/charon"
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

        self.tempdir = charon.util.SelfDeletingDir(tempfile.mkdtemp(prefix="charon-tmp"))

        self.resources = {}
        with self._db:
            c = self._db.cursor()
            c.execute("select id, name, type from Resources where deployment = ?", (self.uuid,))
            for (id, name, type) in c.fetchall():
                r = charon.backends.create_state(self, type, name, id)
                self.resources[name] = r
        self.set_log_prefixes()

        self.definitions = None


    @property
    def machines(self):
        return {n: r for n, r in self.resources.items() if is_machine(r)}

    @property
    def active(self): # FIXME: rename to "active_machines"
        return {n: r for n, r in self.resources.items() if is_machine(r) and not r.obsolete}

    @property
    def active_resources(self):
        return {n: r for n, r in self.resources.items() if not r.obsolete}


    def _set_attrs(self, attrs):
        """Update deployment attributes in the state file."""
        with self._db:
            c = self._db.cursor()
            for n, v in attrs.iteritems():
                if v == None:
                    c.execute("delete from DeploymentAttrs where deployment = ? and name = ?", (self.uuid, n))
                else:
                    c.execute("insert or replace into DeploymentAttrs(deployment, name, value) values (?, ?, ?)",
                              (self.uuid, n, v))


    def _set_attr(self, name, value):
        """Update one deployment attribute in the state file."""
        self._set_attrs({name: value})


    def _del_attr(self, name):
        """Delete a deployment attribute from the state file."""
        with self._db:
            self._db.execute("delete from DeploymentAttrs where deployment = ? and name = ?", (self.uuid, name))


    def _get_attr(self, name, default=charon.util.undefined):
        """Get a deployment attribute from the state file."""
        with self._db:
            c = self._db.cursor()
            c.execute("select value from DeploymentAttrs where deployment = ? and name = ?", (self.uuid, name))
            row = c.fetchone()
            if row != None: return row[0]
            return charon.util.undefined


    def clone(self):
        with self._db:
            new = create_deployment(self._db)
            self._db.execute("insert into DeploymentAttrs (deployment, name, value) " +
                             "select ?, name, value from DeploymentAttrs where deployment = ?",
                             (new.uuid, self.uuid))
            new.configs_path = None
            return new


    def _get_deployment_lock(self):
        if self._lock_file_path is None:
            lock_dir = os.environ.get("HOME", "") + "/.charon/locks"
            if not os.path.exists(lock_dir): os.makedirs(lock_dir, 0700)
            self._lock_file_path = lock_dir + "/" + self.uuid
        class DeploymentLock(object):
            def __init__(self, depl):
                self._lock_file_path = depl._lock_file_path
                self._log = depl.log
                self._lock_file = None
            def __enter__(self):
                self._lock_file = open(self._lock_file_path, "w")
                fcntl.fcntl(self._lock_file, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
                try:
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    self._log("waiting for exclusive deployment lock...")
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX)
            def __exit__(self, exception_type, exception_value, exception_traceback):
                self._lock_file.close()
        return DeploymentLock(self)


    def delete_resource(self, m):
        del self.resources[m.name]
        with self._db:
            self._db.execute("delete from Resources where deployment = ? and id = ?", (self.uuid, m.id))


    def delete(self):
        """Delete this deployment from the state file."""
        if len(self.resources) > 0:
            raise Exception("cannot delete this deployment because it still has resources")
        with self._db:
            if len(self.resources) > 0:
                raise Exception("cannot delete this deployment because it still has resources")

            # Delete the profile, if any.
            profile = self.get_profile()
            assert profile
            for p in glob.glob(profile + "*"):
                if os.path.islink(p): os.remove(p)

            # Delete the deployment from the database.
            self._db.execute("delete from Deployments where uuid = ?", (self.uuid,))


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
        max_len = max([len(r.name) for r in self.resources.itervalues()] or [0])
        for r in self.resources.itervalues():
            r.set_log_prefix(max_len)


    def warn(self, msg):
        self.log(charon.util.ansi_warn("warning: " + msg, outfile=self._log_file))


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


    def _nix_path_flags(self):
        flags = list(itertools.chain(*[["-I", x] for x in (self.extra_nix_path + self.nix_path)])) + self.extra_nix_flags
        flags.extend(["-I", "charon=" + self.expr_path])
        return flags


    def _eval_flags(self, exprs):
        flags = self._nix_path_flags()
        flags.extend(
            ["--arg", "networkExprs", "[ " + string.join(exprs) + " ]",
             "--arg", "args", self._args_to_attrs(),
             "--argstr", "uuid", self.uuid,
             "--show-trace",
             "<charon/eval-machine-info.nix>"])
        return flags


    def set_arg(self, name, value):
        """Set a persistent argument to the deployment specification."""
        assert isinstance(name, basestring)
        assert isinstance(value, basestring)
        args = self.args
        args[name] = value
        self.args = args


    def set_argstr(self, name, value):
        """Set a persistent argument to the deployment specification."""
        assert isinstance(value, basestring)
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
                ["nix-instantiate"]
                + self._eval_flags(self.nix_exprs) +
                ["--eval-only", "--xml", "--strict",
                 "--arg", "checkConfigurationOptions", "false",
                 "-A", "info"], stderr=self._log_file)
            if debug: print >> sys.stderr, "XML output of nix-instantiate:\n" + xml
        except subprocess.CalledProcessError:
            raise NixEvalError

        tree = ElementTree.fromstring(xml)

        # Extract global deployment attributes.
        info = tree.find("attrs/attr[@name='network']")
        assert info != None
        elem = info.find("attrs/attr[@name='description']/string")
        self.description = elem.get("value") if elem != None else self.default_description
        elem = info.find("attrs/attr[@name='enableRollback']/bool")
        self.rollback_enabled = elem != None and elem.get("value") == "true"

        # Extract machine information.
        for x in tree.find("attrs/attr[@name='machines']/attrs").findall("attr"):
            defn = charon.backends.create_definition(x)
            self.definitions[defn.name] = defn

        # Extract info about other kinds of resources.
        res = tree.find("attrs/attr[@name='resources']/attrs")

        for x in res.find("attr[@name='ec2KeyPairs']/attrs").findall("attr"):
            defn = charon.resources.ec2_keypair.EC2KeyPairDefinition(x)
            self.definitions[defn.name] = defn

        for x in res.find("attr[@name='sqsQueues']/attrs").findall("attr"):
            defn = charon.resources.sqs_queue.SQSQueueDefinition(x)
            self.definitions[defn.name] = defn

        for x in res.find("attr[@name='iamRoles']/attrs").findall("attr"):
            defn = charon.resources.iam_role.IAMRoleDefinition(x)
            self.definitions[defn.name] = defn

        for x in res.find("attr[@name='s3Buckets']/attrs").findall("attr"):
            defn = charon.resources.s3_bucket.S3BucketDefinition(x)
            self.definitions[defn.name] = defn


    def evaluate_option_value(self, machine_name, option_name, xml=False):
        """Evaluate a single option of a single machine in the deployment specification."""

        try:
            return subprocess.check_output(
                ["nix-instantiate"]
                + self._eval_flags(self.nix_exprs) +
                ["--eval-only", "--strict",
                 "--arg", "checkConfigurationOptions", "false",
                 "-A", "nodes.{0}.config.{1}".format(machine_name, option_name)]
                + (["--xml"] if xml else []),
                stderr=self._log_file)
        except subprocess.CalledProcessError:
            raise NixEvalError


    def get_physical_spec(self):
        """Compute the contents of the Nix expression specifying the computed physical deployment attributes"""

        active_machines = self.active
        active_resources = self.active_resources

        lines_per_resource = {m.name: [] for m in active_resources.itervalues()}
        authorized_keys = {m.name: [] for m in active_machines.itervalues()}
        kernel_modules = {m.name: set() for m in active_machines.itervalues()}
        trusted_interfaces = {m.name: set() for m in active_machines.itervalues()}
        hosts = {}

        for m in active_machines.itervalues():
            hosts[m.name] = {m.name + "-encrypted": "127.0.0.1"}
            for m2 in active_machines.itervalues():
                if m == m2: continue
                ip = m.address_to(m2)
                if ip: hosts[m.name][m2.name] = hosts[m.name][m2.name + "-unencrypted"] = ip

        def index_to_private_ip(index):
            n = 105 + index / 256
            assert n <= 255
            return "192.168.{0}.{1}".format(n, index % 256)

        def do_machine(m):
            defn = self.definitions[m.name]
            lines = lines_per_resource[m.name]

            # Emit configuration to realise encrypted peer-to-peer links.
            for m2_name in defn.encrypted_links_to:

                if m2_name not in active_machines:
                    raise Exception("‘deployment.encryptedLinksTo’ in machine ‘{0}’ refers to an unknown machine ‘{1}’"
                                    .format(m.name, m2_name))
                m2 = active_machines[m2_name]
                # Don't create two tunnels between a pair of machines.
                if m.name in self.definitions[m2.name].encrypted_links_to and m.name >= m2.name:
                    continue
                local_ipv4 = index_to_private_ip(m.index)
                remote_ipv4 = index_to_private_ip(m2.index)
                local_tunnel = 10000 + m2.index
                remote_tunnel = 10000 + m.index
                lines.append('    networking.p2pTunnels.ssh.{0} ='.format(m2.name))
                lines.append('      {{ target = "{0}-unencrypted";'.format(m2.name))
                lines.append('        localTunnel = {0};'.format(local_tunnel))
                lines.append('        remoteTunnel = {0};'.format(remote_tunnel))
                lines.append('        localIPv4 = "{0}";'.format(local_ipv4))
                lines.append('        remoteIPv4 = "{0}";'.format(remote_ipv4))
                lines.append('        privateKey = "/root/.ssh/id_charon_vpn";')
                lines.append('      }};'.format(m2.name))

                if hasattr(m2, 'public_host_key'):
                    # Using references to files in same tempdir for now, until NixOS has support
                    # for adding the keys directly as string. This way at least it is compatible
                    # with older versions of NixOS as well.
                    # TODO: after reasonable amount of time replace with string option
                    lines.append('    services.openssh.knownHosts.{0} ='.format(m2.name))
                    lines.append('      {{ hostNames = ["{0}-unencrypted" "{0}-encrypted" "{0}" ];'.format(m2.name))
                    lines.append('        publicKeyFile = ./{0}.public_host_key;'.format(m2.name))
                    lines.append('      }};'.format(m2.name))

                # FIXME: set up the authorized_key file such that ‘m’
                # can do nothing more than create a tunnel.
                authorized_keys[m2.name].append('"' + m.public_vpn_key + '"')
                kernel_modules[m.name].add('"tun"')
                kernel_modules[m2.name].add('"tun"')
                hosts[m.name][m2.name] = hosts[m.name][m2.name + "-encrypted"] = remote_ipv4
                hosts[m2.name][m.name] = hosts[m2.name][m.name + "-encrypted"] = local_ipv4
                trusted_interfaces[m.name].add('"tun' + str(local_tunnel) + '"')
                trusted_interfaces[m2.name].add('"tun' + str(remote_tunnel) + '"')

            private_ipv4 = m.private_ipv4
            if private_ipv4: lines.append('    networking.privateIPv4 = "{0}";'.format(private_ipv4))
            public_ipv4 = m.public_ipv4
            if public_ipv4: lines.append('    networking.publicIPv4 = "{0}";'.format(public_ipv4))

            if self.nixos_version_suffix:
                lines.append('    system.nixosVersionSuffix = "{0}";'.format(self.nixos_version_suffix))

        for m in active_machines.itervalues(): do_machine(m)

        def emit_resource(r):
            lines = []
            lines.extend(r.get_physical_spec())
            lines.extend(lines_per_resource[r.name])
            if is_machine(r):
                if authorized_keys[r.name]:
                    lines.append('    users.extraUsers.root.openssh.authorizedKeys.keys = [ {0} ];'.format(" ".join(authorized_keys[r.name])))
                    lines.append('    services.openssh.extraConfig = "PermitTunnel yes\\n";')
                lines.append('    boot.kernelModules = [ {0} ];'.format(" ".join(kernel_modules[r.name])))
                lines.append('    networking.firewall.trustedInterfaces = [ {0} ];'.format(" ".join(trusted_interfaces[r.name])))
                lines.append('    networking.extraHosts = "{0}\\n";'.format('\\n'.join([hosts[r.name][m2] + " " + m2 for m2 in hosts[r.name]])))
            if lines == []: return ""
            lines.insert(0, '  {0}"{1}" = {{ config, pkgs, ... }}: {{'.format(r.get_definition_prefix(), r.name))
            lines.append("  };\n")
            return "\n".join(lines)

        return "".join(["{\n"] + [emit_resource(r) for r in active_resources.itervalues()] + ["}\n"])


    def get_profile(self):
        return "/nix/var/nix/profiles/per-user/{0}/charon/{1}".format(getpass.getuser(), self.uuid)


    def create_profile(self):
        profile = self.get_profile()
        dir = os.path.dirname(profile)
        if not os.path.exists(dir): os.makedirs(dir, 0755)
        return profile


    def build_configs(self, include, exclude, dry_run=False):
        """Build the machine configurations in the Nix store."""

        def write_temp_file(tmpfile, contents):
            f = open(tmpfile, "w")
            f.write(contents)
            f.close()

        self.log("building all machine configurations...")

        # Set the NixOS version suffix, if we're building from Git.
        # That way ‘nixos-version’ will show something useful on the
        # target machines.
        nixos_path = subprocess.check_output(
            ["nix-instantiate", "--find-file", "nixos"] + self._nix_path_flags()).rstrip()
        get_version_script = nixos_path + "/modules/installer/tools/get-version-suffix"
        if os.path.exists(nixos_path + "/.git") and os.path.exists(get_version_script):
            self.nixos_version_suffix = subprocess.check_output(["/bin/sh", get_version_script] + self._nix_path_flags()).rstrip()

        phys_expr = self.tempdir + "/physical.nix"
        p = self.get_physical_spec()
        write_temp_file(phys_expr, p)
        if debug: print >> sys.stderr, "generated physical spec:\n" + p

        for m in self.active.itervalues():
            if hasattr(m, "public_host_key"):
                write_temp_file("{0}/{1}.public_host_key".format(self.tempdir,m.name), m.public_host_key + "\n")

        names = ['"' + m.name + '"' for m in self.active.itervalues() if should_do(m, include, exclude)]

        try:
            configs_path = subprocess.check_output(
                ["nix-build"]
                + self._eval_flags(self.nix_exprs + [phys_expr]) +
                ["--arg", "names", "[ " + " ".join(names) + " ]",
                 "-A", "machines", "-o", self.tempdir + "/configs"]
                + (["--dry-run"] if dry_run else []), stderr=self._log_file).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        if self.rollback_enabled:
            profile = self.create_profile()
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


    def activate_configs(self, configs_path, include, exclude, allow_reboot, force_reboot, check, sync):
        """Activate the new configuration on a machine."""

        def worker(m):
            if not should_do(m, include, exclude): return

            try:
                m.send_keys()

                res = m.run_command(
                    # Set the system profile to the new configuration.
                    "set -e; nix-env -p /nix/var/nix/profiles/system --set " + m.new_toplevel + "; " +
                    # Run the switch script.  This will also update the
                    # GRUB boot loader.
                    ("NIXOS_NO_SYNC=1 " if not sync else "") +
                    "/nix/var/nix/profiles/system/bin/switch-to-configuration " + ("boot" if force_reboot else "switch"),
                    check=False)

                if res != 0 and res != 100:
                    raise Exception("unable to activate new configuration")

                if res == 100 or force_reboot:
                    if not allow_reboot and not force_reboot:
                        raise Exception("the new configuration requires a reboot to take effect (hint: use ‘--allow-reboot’)".format(m.name))
                    m.reboot_sync()
                    res = 0
                    # FIXME: should check which systemd services
                    # failed to start after the reboot.

                if res == 0:
                    m.log("activation finished successfully")

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

        res = charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)
        failed = [x for x in res if x != None]
        if failed != []:
            raise Exception("activation of {0} of {1} machines failed (namely on {2})"
                            .format(len(failed), len(res), ", ".join(["‘{0}’".format(x) for x in failed])))


    def _get_free_resource_index(self):
        index = 0
        for r in self.resources.itervalues():
            if r.index != None and index <= r.index:
                index = r.index + 1
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

    def clean_backups(self, keep=10):
        _backups = self.get_backups()
        backup_ids = [b for b in _backups.keys()]
        backup_ids.sort()
        index = len(backup_ids)-keep
        for backup_id in backup_ids[:index]:
            print 'Removing backup {0}'.format(backup_id)
            self.remove_backup(backup_id)

    def remove_backup(self, backup_id):
        with self._get_deployment_lock():
            def worker(m):
                m.remove_backup(backup_id)

            charon.parallel.run_tasks(nr_workers=len(self.active), tasks=self.machines.itervalues(), worker_fun=worker)


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

        charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)

        return backup_id


    def restore(self, include=[], exclude=[], backup_id=None):
        with self._get_deployment_lock():

            self.evaluate_active(include, exclude)
            def worker(m):
                if not should_do(m, include, exclude): return
                m.restore(self.definitions[m.name], backup_id)

            charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)
            self.start_machines(include=include, exclude=exclude)
            self.warn("restore finished; please note that you might need to run ‘charon deploy’ to fix configuration issues regarding changed IP addresses")


    def evaluate_active(self, include=[], exclude=[], kill_obsolete=False):
        self.evaluate()

        # Create state objects for all defined resources.
        with self._db:
            for m in self.definitions.itervalues():
                if m.name not in self.resources:
                    c = self._db.cursor()
                    c.execute("select 1 from Resources where deployment = ? and name = ?", (self.uuid, m.name))
                    if len(c.fetchall()) != 0:
                        raise Exception("resource already exists in database!")
                    c.execute("insert into Resources(deployment, name, type) values (?, ?, ?)",
                              (self.uuid, m.name, m.get_type()))
                    id = c.lastrowid
                    self.resources[m.name] = charon.backends.create_state(self, m.get_type(), m.name, id)

        self.set_log_prefixes()

        # Determine the set of active resources.  (We can't just
        # delete obsolete resources from ‘self.resources’ because they
        # contain important state that we don't want to forget about.)
        for m in self.resources.values():
            if m.name in self.definitions:
                if m.obsolete:
                    self.log("resource ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.log("resource ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True
                if not should_do(m, include, exclude): continue
                if kill_obsolete and m.destroy(): self.delete_resource(m)


    def _deploy(self, dry_run=False, build_only=False, create_only=False, copy_only=False,
               include=[], exclude=[], check=False, kill_obsolete=False,
               allow_reboot=False, force_reboot=False, max_concurrent_copy=5, sync=True):
        """Perform the deployment defined by the deployment specification."""

        self.evaluate_active(include, exclude, kill_obsolete)

        # Assign each resource an index if it doesn't have one.
        for r in self.active_resources.itervalues():
            if r.index == None:
                r.index = self._get_free_resource_index()

        self.set_log_prefixes()

        # Start or update the active resources.  Non-machine resources
        # are created first, because machines may depend on them
        # (e.g. EC2 machines depend on EC2 key pairs or EBS volumes).
        # FIXME: would be nice to have a more fine-grained topological
        # sort.
        if not dry_run and not build_only:

            for r in self.active_resources.itervalues():
                defn = self.definitions[r.name]
                if r.get_type() != defn.get_type():
                    raise Exception("the type of resource ‘{0}’ changed from ‘{1}’ to ‘{2}’, which is currently unsupported"
                                    .format(r.name, r.get_type(), defn.get_type()))
                r._created_event = threading.Event()

            def worker(r):
                if not should_do(r, include, exclude): return

                # Sleep until all dependencies of this resource have
                # been created.
                deps = r.create_after(self.active_resources.itervalues())
                for dep in deps:
                    if not should_do(dep, include, exclude): continue
                    dep._created_event.wait()

                # Now create the resource itself.
                r.create(self.definitions[r.name], check=check, allow_reboot=allow_reboot)
                if is_machine(r):
                    r.wait_for_ssh(check=check)
                    r.generate_vpn_key()

                r._created_event.set()

            charon.parallel.run_tasks(nr_workers=-1, tasks=self.active_resources.itervalues(), worker_fun=worker)

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
                              allow_reboot=allow_reboot, force_reboot=force_reboot, check=check, sync=sync)


    def deploy(self, **kwargs):
        with self._get_deployment_lock():
            self._deploy(**kwargs)


    def _rollback(self, generation, include=[], exclude=[], check=False,
                 allow_reboot=False, force_reboot=False, max_concurrent_copy=5, sync=True):
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
        for m in self.machines.values():
            if m.name in names:
                if m.obsolete:
                    self.log("machine ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.log("machine ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True

        self.copy_closures(self.configs_path, include=include, exclude=exclude,
                           max_concurrent_copy=max_concurrent_copy)

        self.activate_configs(self.configs_path, include=include, exclude=exclude,
                              allow_reboot=allow_reboot, force_reboot=force_reboot, check=check, sync=sync)


    def rollback(self, **kwargs):
        with self._get_deployment_lock():
            self._rollback(**kwargs)


    def destroy_resources(self, include=[], exclude=[]):
        """Destroy all active or obsolete resources."""

        with self._get_deployment_lock():

            def worker(m):
                if not should_do(m, include, exclude): return
                if m.destroy(): self.delete_resource(m)

            charon.parallel.run_tasks(nr_workers=-1, tasks=self.resources.values(), worker_fun=worker)

        # Remove the destroyed machines from the rollback profile.
        # This way, a subsequent "nix-env --delete-generations old" or
        # "nix-collect-garbage -d" will get rid of the machine
        # configurations.
        if self.rollback_enabled: # and len(self.active) == 0:
            profile = self.create_profile()
            attrs = ["\"{0}\" = builtins.storePath {1};".format(m.name, m.cur_toplevel) for m in self.active.itervalues() if m.cur_toplevel]
            if subprocess.call(
                ["nix-env", "-p", profile, "--set", "*", "-I", "charon=" + self.expr_path,
                 "-f", "<charon/update-profile.nix>",
                 "--arg", "machines", "{ " + " ".join(attrs) + " }"]) != 0:
                raise Exception("cannot update profile ‘{0}’".format(profile))


    def reboot_machines(self, include=[], exclude=[], wait=False):
        """Reboot all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            if wait:
                m.reboot_sync()
            else:
                m.reboot()

        charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def stop_machines(self, include=[], exclude=[]):
        """Stop all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.stop()

        charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def start_machines(self, include=[], exclude=[]):
        """Start all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.start()

        charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def is_valid_resource_name(self, name):
        p = re.compile('^\w+$')
        return not p.match(name) is None


    def rename(self, name, new_name):
        if not name in self.resources:
            raise Exception("resource ‘{0}’ not found".format(name))
        if new_name in self.resources:
            raise Exception("resource with name ‘{0}’ already exists".format(new_name))
        if not self.is_valid_resource_name(new_name):
            raise Exception("{0} is not a valid resource identifier".format(new_name))

        self.log("renaming resource ‘{0}’ to ‘{1}’...".format(name, new_name))

        m = self.resources.pop(name)
        self.resources[new_name] = m

        with self._db:
            self._db.execute("update Resources set name = ? where deployment = ? and id = ?", (new_name, self.uuid, m.id))


    def send_keys(self, include=[], exclude=[]):
        """Send LUKS encryption keys to machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.send_keys()

        charon.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


class NixEvalError(Exception):
    pass


def should_do(m, include, exclude):
    return should_do_n(m.name, include, exclude)

def should_do_n(name, include, exclude):
    if name in exclude: return False
    if include == []: return True
    return name in include

def is_machine(r):
    return isinstance(r, charon.backends.MachineState)

def is_machine_defn(r):
    return isinstance(r, charon.backends.MachineDefinition)
