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
from collections import defaultdict
from xml.etree import ElementTree
import nixops.backends
import nixops.logger
import nixops.parallel
from nixops.nix_expr import RawValue, Function, Call, nixmerge, py2nix
import re
from datetime import datetime, timedelta
import getpass
import traceback
import glob
import itertools
import platform
from nixops.util import ansi_success
import inspect
import time

class NixEvalError(Exception):
    pass

class UnknownBackend(Exception):
    pass

debug = False

class Deployment(object):
    """NixOps top-level deployment manager."""

    default_description = "Unnamed NixOps network"

    name = nixops.util.attr_property("name", None)
    nix_exprs = nixops.util.attr_property("nixExprs", [], 'json')
    nix_path = nixops.util.attr_property("nixPath", [], 'json')
    args = nixops.util.attr_property("args", {}, 'json')
    description = nixops.util.attr_property("description", default_description)
    configs_path = nixops.util.attr_property("configsPath", None)
    rollback_enabled = nixops.util.attr_property("rollbackEnabled", False)

    def __init__(self, state, uuid, log_file=sys.stderr):
        self._state = state
        self.uuid = uuid

        self._last_log_prefix = None
        self.extra_nix_path = []
        self.extra_nix_flags = []
        self.extra_nix_eval_flags = []
        self.nixos_version_suffix = None
        self._tempdir = None

        self.logger = nixops.logger.Logger(log_file)

        self._lock_file_path = None

        self.expr_path = os.path.realpath(os.path.dirname(__file__) + "/../../../../share/nix/nixops")
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.realpath(os.path.dirname(__file__) + "/../../../../../share/nix/nixops")
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

        self.resources = self._state.get_resources_for(self)
        self.logger.update_log_prefixes()
        self.definitions = None


    @property
    def tempdir(self):
        if not self._tempdir:
            self._tempdir = nixops.util.SelfDeletingDir(tempfile.mkdtemp(prefix="nixops-tmp"))
        return self._tempdir

    @property
    def machines(self):
        return {n: r for n, r in self.resources.items() if is_machine(r)}

    @property
    def active(self): # FIXME: rename to "active_machines"
        return {n: r for n, r in self.resources.items() if is_machine(r) and not r.obsolete}

    @property
    def active_resources(self):
        return {n: r for n, r in self.resources.items() if not r.obsolete}


    def get_typed_resource(self, name, type):
        res = self.active_resources.get(name, None)
        if not res:
            raise Exception("resource ‘{0}’ does not exist".format(name))
        if res.get_type() != type:
            raise Exception("resource ‘{0}’ is not of type ‘{1}’".format(name, type))
        return res


    def get_machine(self, name):
        res = self.active_resources.get(name, None)
        if not res:
            raise Exception("machine ‘{0}’ does not exist".format(name))
        if not is_machine(res):
            raise Exception("resource ‘{0}’ is not a machine".format(name))
        return res

    def _set_attrs(self, attrs):
        """Update deployment attributes in the state."""
        self._state.set_deployment_attrs(self.uuid, attrs)


    def _set_attr(self, name, value):
        """Update one deployment attribute in the state."""
        self._set_attrs({name: value})


    def _del_attr(self, name):
        """Delete a deployment attribute from the state."""
        self._state.del_deployment_attr(self.uuid, name)


    #TODO(moretea): The default param does not appear to be used at all?
    # Removed it when moving the body to nixops/state/file.py.
    def _get_attr(self, name, default=nixops.util.undefined):
        """Get a deployment attribute from the state."""
        return self._state.get_deployment_attr(self.uuid, name)

    def _create_resource(self, name, type):
        r = self._state.create_resource(self, name, type)
        self.resources[name] = r
        return r


    def export(self):
        res = self._state.get_all_deployment_attrs(self.uuid)
        res['resources'] = {r.name: r.export() for r in self.resources.itervalues()}
        return res


    def import_(self, attrs):
        with self._state.db:
            for k, v in attrs.iteritems():
                if k == 'resources': continue
                self._set_attr(k, v)
            for k, v in attrs['resources'].iteritems():
                if 'type' not in v: raise Exception("imported resource lacks a type")
                r = self._create_resource(k, v['type'])
                r.import_(v)


    def clone(self):
        return self._state.clone_deployment(self.uuid)


    def _get_deployment_lock(self):
        return self._state.get_deployment_lock(self)


    def delete_resource(self, m):
        del self.resources[m.name]
        self._state.delete_resource(self.uuid, m.id)


    def delete(self, force=False):
        """Delete this deployment from the state file."""
        with self._state.db:
            if not force and len(self.resources) > 0:
                raise Exception("cannot delete this deployment because it still has resources")

            # Delete the profile, if any.
            profile = self.get_profile()
            assert profile
            for p in glob.glob(profile + "*"):
                if os.path.islink(p): os.remove(p)

            # Delete the deployment from the database.
            self._state._delete_deployment(self.uuid)


    def _nix_path_flags(self):
        flags = list(itertools.chain(*[["-I", x] for x in (self.extra_nix_path + self.nix_path)])) + self.extra_nix_flags
        flags.extend(["-I", "nixops=" + self.expr_path])
        return flags


    def _eval_flags(self, exprs):
        flags = self._nix_path_flags()
        args = {key: RawValue(val) for key, val in self.args.iteritems()}
        exprs_ = [RawValue(x) if x[0] == '<' else x for x in exprs]
        flags.extend(
            ["--arg", "networkExprs", py2nix(exprs_, inline=True),
             "--arg", "args", py2nix(args, inline=True),
             "--argstr", "uuid", self.uuid,
             "--argstr", "deploymentName", self.name if self.name else "",
             "<nixops/eval-machine-info.nix>"])
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
        self.set_arg(name, py2nix(value, inline=True))


    def unset_arg(self, name):
        """Unset a persistent argument to the deployment specification."""
        assert isinstance(name, str)
        args = self.args
        args.pop(name, None)
        self.args = args

    def evaluate_args(self):
        """Evaluate the NixOps network expression's arguments."""
        try:
            out = subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(self.nix_exprs) +
                ["--eval-only", "--json", "--strict",
                 "-A", "nixopsArguments"], stderr=self.logger.log_file)
            if debug: print >> sys.stderr, "JSON output of nix-instantiate:\n" + xml
            return json.loads(out)
        except OSError as e:
            raise Exception("unable to run ‘nix-instantiate’: {0}".format(e))
        except subprocess.CalledProcessError:
            raise NixEvalError


    def evaluate(self):
        """Evaluate the Nix expressions belonging to this deployment into a deployment specification."""

        self.definitions = {}

        try:
            # FIXME: use --json
            xml = subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(self.nix_exprs) +
                ["--eval-only", "--xml", "--strict",
                 "--arg", "checkConfigurationOptions", "false",
                 "-A", "info"], stderr=self.logger.log_file)
            if debug: print >> sys.stderr, "XML output of nix-instantiate:\n" + xml
        except OSError as e:
            raise Exception("unable to run ‘nix-instantiate’: {0}".format(e))
        except subprocess.CalledProcessError:
            raise NixEvalError

        tree = ElementTree.fromstring(xml)

        # Convert the XML to a more Pythonic representation. This is
        # in fact the same as what json.loads() on the output of
        # "nix-instantiate --json" would yield.
        config = nixops.util.xml_expr_to_python(tree.find("*"))

        # Extract global deployment attributes.
        self.description = config["network"].get("description", self.default_description)
        self.rollback_enabled = config["network"].get("enableRollback", False)

        # Extract machine information.
        for x in tree.findall("attrs/attr[@name='machines']/attrs/attr"):
            name = x.get("name")
            cfg = config["machines"][name]
            defn = _create_definition(x, cfg, cfg["targetEnv"])
            self.definitions[name] = defn

        # Extract info about other kinds of resources.
        for x in tree.findall("attrs/attr[@name='resources']/attrs/attr"):
            res_type = x.get("name")
            for y in x.findall("attrs/attr"):
                name = y.get("name")
                defn = _create_definition(y, config["resources"][res_type][name], res_type)
                self.definitions[name] = defn


    def evaluate_option_value(self, machine_name, option_name, xml=False, include_physical=False):
        """Evaluate a single option of a single machine in the deployment specification."""

        exprs = self.nix_exprs
        if include_physical:
            phys_expr = self.tempdir + "/physical.nix"
            with open(phys_expr, 'w') as f:
                f.write(self.get_physical_spec())
            exprs.append(phys_expr)

        try:
            return subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(exprs) +
                ["--eval-only", "--strict",
                 "--arg", "checkConfigurationOptions", "false",
                 "-A", "nodes.{0}.config.{1}".format(machine_name, option_name)]
                + (["--xml"] if xml else []),
                stderr=self.logger.log_file)
        except subprocess.CalledProcessError:
            raise NixEvalError


    def get_arguments(self):
        try:
            return self.evaluate_args()
        except Exception as e:
            raise Exception("Could not determine arguments to NixOps deployment.")


    def get_physical_spec(self):
        """Compute the contents of the Nix expression specifying the computed physical deployment attributes"""

        active_machines = self.active
        active_resources = self.active_resources

        attrs_per_resource = {m.name: [] for m in active_resources.itervalues()}
        authorized_keys = {m.name: [] for m in active_machines.itervalues()}
        kernel_modules = {m.name: set() for m in active_machines.itervalues()}
        trusted_interfaces = {m.name: set() for m in active_machines.itervalues()}

        # Hostnames should be accumulated like this:
        #
        #   hosts[local_name][remote_ip] = [name1, name2, ...]
        #
        # This makes hosts deterministic and is more in accordance to the
        # format in hosts(5), which is like this:
        #
        #   ip_address canonical_hostname [aliases...]
        #
        # This is critical for example when using host names for access
        # control, because the canonical_hostname is returned in reverse
        # lookups.
        hosts = defaultdict(lambda: defaultdict(list))

        def index_to_private_ip(index):
            n = 105 + index / 256
            assert n <= 255
            return "192.168.{0}.{1}".format(n, index % 256)

        def do_machine(m):
            defn = self.definitions[m.name]
            attrs_list = attrs_per_resource[m.name]

            # Emit configuration to realise encrypted peer-to-peer links.
            for m2 in active_resources.itervalues():
                ip = m.address_to(m2)
                if ip:
                    hosts[m.name][ip] += [m2.name, m2.name + "-unencrypted"]

            # Always use the encrypted/unencrypted suffixes for aliases rather
            # than for the canonical name!
            hosts[m.name]["127.0.0.1"].append(m.name + "-encrypted")

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
                attrs_list.append({
                    ('networking', 'p2pTunnels', 'ssh', m2.name): {
                        'target': '{0}-unencrypted'.format(m2.name),
                        'targetPort': m2.ssh_port,
                        'localTunnel': local_tunnel,
                        'remoteTunnel': remote_tunnel,
                        'localIPv4': local_ipv4,
                        'remoteIPv4': remote_ipv4,
                        'privateKey': '/root/.ssh/id_charon_vpn',
                    }
                })

                # FIXME: set up the authorized_key file such that ‘m’
                # can do nothing more than create a tunnel.
                authorized_keys[m2.name].append(m.public_vpn_key)
                kernel_modules[m.name].add('tun')
                kernel_modules[m2.name].add('tun')
                hosts[m.name][remote_ipv4] += [m2.name, m2.name + "-encrypted"]
                hosts[m2.name][local_ipv4] += [m.name, m.name + "-encrypted"]
                trusted_interfaces[m.name].add('tun' + str(local_tunnel))
                trusted_interfaces[m2.name].add('tun' + str(remote_tunnel))

            private_ipv4 = m.private_ipv4
            if private_ipv4:
                attrs_list.append({
                    ('networking', 'privateIPv4'): private_ipv4
                })
            public_ipv4 = m.public_ipv4
            if public_ipv4:
                attrs_list.append({
                    ('networking', 'publicIPv4'): public_ipv4
                })
            public_vpn_key = m.public_vpn_key
            if public_vpn_key:
                attrs_list.append({
                    ('networking', 'vpnPublicKey'): public_vpn_key
                })

            # Set system.stateVersion if the Nixpkgs version supports it.
            if nixops.util.parse_nixos_version(defn.config["nixosRelease"]) >= ["15", "09"]:
                attrs_list.append({
                    ('system', 'stateVersion'): Call(RawValue("lib.mkDefault"), m.state_version or defn.config["nixosRelease"])
                })

            if self.nixos_version_suffix:
                attrs_list.append({
                    ('system', 'nixosVersionSuffix'): self.nixos_version_suffix
                })

        for m in active_machines.itervalues():
            do_machine(m)

        def emit_resource(r):
            config = []
            config.extend(attrs_per_resource[r.name])
            if is_machine(r):
                # Sort the hosts by its canonical host names.
                sorted_hosts = sorted(hosts[r.name].iteritems(),
                                      key=lambda item: item[1][0])
                # Just to remember the format:
                #   ip_address canonical_hostname [aliases...]
                extra_hosts = ["{0} {1}".format(ip, ' '.join(names))
                               for ip, names in sorted_hosts]

                if authorized_keys[r.name]:
                    config.append({
                        ('users', 'extraUsers', 'root'): {
                            ('openssh', 'authorizedKeys', 'keys'): authorized_keys[r.name]
                        },
                        ('services', 'openssh'): {
                            'extraConfig': "PermitTunnel yes\n"
                        },
                    })

                config.append({
                    ('boot', 'kernelModules'): list(kernel_modules[r.name]),
                    ('networking', 'firewall'): {
                        'trustedInterfaces': list(trusted_interfaces[r.name])
                    },
                    ('networking', 'extraHosts'): '\n'.join(extra_hosts) + "\n"
                })


                # Add SSH public host keys for all machines in network.
                for m2 in active_machines.itervalues():
                    if hasattr(m2, 'public_host_key') and m2.public_host_key:
                        # Using references to files in same tempdir for now, until NixOS has support
                        # for adding the keys directly as string. This way at least it is compatible
                        # with older versions of NixOS as well.
                        # TODO: after reasonable amount of time replace with string option
                        config.append({
                            ('services', 'openssh', 'knownHosts', m2.name): {
                                 'hostNames': [m2.name + "-unencrypted",
                                               m2.name + "-encrypted",
                                               m2.name],
                                 'publicKey': m2.public_host_key,
                            }
                        })

            merged = reduce(nixmerge, config) if len(config) > 0 else {}
            physical = r.get_physical_spec()

            if len(merged) == 0 and len(physical) == 0:
                return {}
            else:
                return r.prefix_definition({
                    r.name: Function("{ config, lib, pkgs, ... }", {
                        'config': merged,
                        'imports': [physical],
                    })
                })

        return py2nix(reduce(nixmerge, [
            emit_resource(r) for r in active_resources.itervalues()
        ], {})) + "\n"

    def get_profile(self):
        profile_dir = "/nix/var/nix/profiles/per-user/" + getpass.getuser()
        if os.path.exists(profile_dir + "/charon") and not os.path.exists(profile_dir + "/nixops"):
            os.rename(profile_dir + "/charon", profile_dir + "/nixops")
        return profile_dir + "/nixops/" + self.uuid


    def create_profile(self):
        profile = self.get_profile()
        dir = os.path.dirname(profile)
        if not os.path.exists(dir): os.makedirs(dir, 0755)
        return profile


    def build_configs(self, include, exclude, dry_run=False, repair=False):
        """Build the machine configurations in the Nix store."""

        self.logger.log("building all machine configurations...")

        # Set the NixOS version suffix, if we're building from Git.
        # That way ‘nixos-version’ will show something useful on the
        # target machines.
        nixos_path = subprocess.check_output(
            ["nix-instantiate", "--find-file", "nixpkgs/nixos"] + self._nix_path_flags()).rstrip()
        get_version_script = nixos_path + "/modules/installer/tools/get-version-suffix"
        if os.path.exists(nixos_path + "/.git") and os.path.exists(get_version_script):
            self.nixos_version_suffix = subprocess.check_output(["/bin/sh", get_version_script] + self._nix_path_flags()).rstrip()

        phys_expr = self.tempdir + "/physical.nix"
        p = self.get_physical_spec()
        nixops.util.write_file(phys_expr, p)
        if debug: print >> sys.stderr, "generated physical spec:\n" + p

        selected = [m for m in self.active.itervalues() if should_do(m, include, exclude)]

        names = map(lambda m: m.name, selected)

        # If we're not running on Linux, then perform the build on the
        # target machines.  FIXME: Also enable this if we're on 32-bit
        # and want to deploy to 64-bit.
        if platform.system() != 'Linux' and os.environ.get('NIX_REMOTE') != 'daemon':
            if os.environ.get('NIX_REMOTE_SYSTEMS') == None:
                remote_machines = []
                for m in sorted(selected, key=lambda m: m.index):
                    key_file = m.get_ssh_private_key_file()
                    if not key_file: raise Exception("do not know private SSH key for machine ‘{0}’".format(m.name))
                    # FIXME: Figure out the correct machine type of ‘m’ (it might not be x86_64-linux).
                    remote_machines.append("root@{0} {1} {2} 2 1\n".format(m.get_ssh_name(), 'i686-linux,x86_64-linux', key_file))
                    # Use only a single machine for now (issue #103).
                    break
                remote_machines_file = "{0}/nix.machines".format(self.tempdir)
                with open(remote_machines_file, "w") as f:
                    f.write("".join(remote_machines))
                os.environ['NIX_REMOTE_SYSTEMS'] = remote_machines_file
            else:
                self.logger.log("using predefined remote systems file: {0}".format(os.environ['NIX_REMOTE_SYSTEMS']))

            # FIXME: Use ‘--option use-build-hook true’ instead of setting
            # $NIX_BUILD_HOOK, once Nix supports that.
            os.environ['NIX_BUILD_HOOK'] = os.path.dirname(os.path.realpath(nixops.util.which("nix-build"))) + "/../libexec/nix/build-remote.pl"

            load_dir = "{0}/current-load".format(self.tempdir)
            if not os.path.exists(load_dir): os.makedirs(load_dir, 0700)
            os.environ['NIX_CURRENT_LOAD'] = load_dir

        try:
            configs_path = subprocess.check_output(
                ["nix-build"]
                + self._eval_flags(self.nix_exprs + [phys_expr]) +
                ["--arg", "names", py2nix(names, inline=True),
                 "-A", "machines", "-o", self.tempdir + "/configs"]
                + (["--dry-run"] if dry_run else [])
                + (["--repair"] if repair else []),
                stderr=self.logger.log_file).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        if self.rollback_enabled and not dry_run:
            profile = self.create_profile()
            if subprocess.call(["nix-env", "-p", profile, "--set", configs_path]) != 0:
                raise Exception("cannot update profile ‘{0}’".format(profile))

        return configs_path


    def copy_closures(self, configs_path, include, exclude, max_concurrent_copy):
        """Copy the closure of each machine configuration to the corresponding machine."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.logger.log("copying closure...")
            m.new_toplevel = os.path.realpath(configs_path + "/" + m.name)
            if not os.path.exists(m.new_toplevel):
                raise Exception("can't find closure of machine ‘{0}’".format(m.name))
            m.copy_closure_to(m.new_toplevel)

        nixops.parallel.run_tasks(
            nr_workers=max_concurrent_copy,
            tasks=self.active.itervalues(), worker_fun=worker)
        self.logger.log(ansi_success("{0}> closures copied successfully".format(self.name or "unnamed"), outfile=self.logger._log_file))


    def activate_configs(self, configs_path, include, exclude, allow_reboot,
                         force_reboot, check, sync, always_activate, dry_activate):
        """Activate the new configuration on a machine."""

        def worker(m):
            if not should_do(m, include, exclude): return

            try:
                # Set the system profile to the new configuration.
                daemon_var = '' if m.state == m.RESCUE else 'env NIX_REMOTE=daemon '
                setprof = daemon_var + 'nix-env -p /nix/var/nix/profiles/system --set "{0}"'
                if always_activate or self.definitions[m.name].always_activate:
                    m.run_command(setprof.format(m.new_toplevel))
                else:
                    # Only activate if the profile has changed.
                    new_profile_cmd = '; '.join([
                        'old_gen="$(readlink -f /nix/var/nix/profiles/system)"',
                        'new_gen="$(readlink -f "{0}")"',
                        '[ "x$old_gen" != "x$new_gen" ] || exit 111',
                        setprof
                    ]).format(m.new_toplevel)

                    ret = m.run_command(new_profile_cmd, check=False)
                    if ret == 111:
                        m.log("configuration already up to date")
                        return
                    elif ret != 0:
                        raise Exception("unable to set new system profile")

                m.send_keys()

                if force_reboot or m.state == m.RESCUE:
                    switch_method = "boot"
                elif dry_activate:
                    switch_method = "dry-activate"
                else:
                    switch_method = "switch"

                # Run the switch script.  This will also update the
                # GRUB boot loader.
                res = m.switch_to_configuration(switch_method, sync)

                if dry_activate: return

                if res != 0 and res != 100:
                    raise Exception("unable to activate new configuration")

                if res == 100 or force_reboot or m.state == m.RESCUE:
                    if not allow_reboot and not force_reboot:
                        raise Exception("the new configuration requires a "
                                        "reboot to take effect (hint: use "
                                        "‘--allow-reboot’)".format(m.name))
                    m.reboot_sync()
                    res = 0
                    # FIXME: should check which systemd services
                    # failed to start after the reboot.

                if res == 0:
                    m.success("activation finished successfully")

                # Record that we switched this machine to the new
                # configuration.
                m.cur_configs_path = configs_path
                m.cur_toplevel = m.new_toplevel

            except Exception as e:
                # This thread shouldn't throw an exception because
                # that will cause NixOps to exit and interrupt
                # activation on the other machines.
                m.logger.error(traceback.format_exc())
                return m.name
            return None

        res = nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)
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
                    if backup_id in machine_backups[m.name].keys():
                        backup['machines'][m.name] = machine_backups[m.name][backup_id]
                        backup['info'].extend(backup['machines'][m.name]['info'])
                        # status is always running when one of the backups is still running
                        if backup['machines'][m.name]['status'] != "complete" and backup['status'] != "running":
                            backup['status'] = backup['machines'][m.name]['status']
                    else:
                        backup['status'] = 'incomplete'
                        backup['info'].extend(["No backup available for {0}".format(m.name)]);

        return backups

    def clean_backups(self, keep, keep_days, keep_physical = False):
        _backups = self.get_backups()
        backup_ids = [b for b in _backups.keys()]
        backup_ids.sort()

        if keep:
            index = len(backup_ids)-keep
            tbr = backup_ids[:index]

        if keep_days:
            cutoff = (datetime.now()- timedelta(days=keep_days)).strftime("%Y%m%d%H%M%S")
            print cutoff
            tbr = [bid for bid in backup_ids if bid < cutoff]

        for backup_id in tbr:
            print 'Removing backup {0}'.format(backup_id)
            self.remove_backup(backup_id, keep_physical)

    def remove_backup(self, backup_id, keep_physical = False):
        with self._get_deployment_lock():
            def worker(m):
                m.remove_backup(backup_id, keep_physical)

            nixops.parallel.run_tasks(nr_workers=len(self.active), tasks=self.machines.itervalues(), worker_fun=worker)


    def backup(self, include=[], exclude=[]):
        self.evaluate_active(include, exclude)
        backup_id = datetime.now().strftime("%Y%m%d%H%M%S")

        def worker(m):
            if not should_do(m, include, exclude): return
            if m.state != m.STOPPED:
                ssh_name = m.get_ssh_name()
                res = subprocess.call(["ssh", "root@" + ssh_name] + m.get_ssh_flags() + ["sync"])
                if res != 0:
                    m.logger.log("running sync failed on {0}.".format(m.name))
            m.backup(self.definitions[m.name], backup_id)

        nixops.parallel.run_tasks(nr_workers=5, tasks=self.active.itervalues(), worker_fun=worker)

        return backup_id


    def restore(self, include=[], exclude=[], backup_id=None, devices=[]):
        with self._get_deployment_lock():

            self.evaluate_active(include, exclude)
            def worker(m):
                if not should_do(m, include, exclude): return
                m.restore(self.definitions[m.name], backup_id, devices)

            nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)
            self.start_machines(include=include, exclude=exclude)
            self.logger.warn("restore finished; please note that you might need to run ‘nixops deploy’ to fix configuration issues regarding changed IP addresses")


    def evaluate_active(self, include=[], exclude=[], kill_obsolete=False):
        self.evaluate()

        # Create state objects for all defined resources.
        with self._state.db:
            for m in self.definitions.itervalues():
                if m.name not in self.resources:
                    self._create_resource(m.name, m.get_type())

        self.logger.update_log_prefixes()

        to_destroy = []

        # Determine the set of active resources.  (We can't just
        # delete obsolete resources from ‘self.resources’ because they
        # contain important state that we don't want to forget about.)
        for m in self.resources.values():
            if m.name in self.definitions:
                if m.obsolete:
                    self.logger.log("resource ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.logger.log("resource ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True
                if not should_do(m, include, exclude): continue
                if kill_obsolete:
                    to_destroy.append(m.name)

        if to_destroy:
            self._destroy_resources(include=to_destroy)


    def _deploy(self, dry_run=False, build_only=False, create_only=False, copy_only=False, evaluate_only=False,
                include=[], exclude=[], check=False, kill_obsolete=False,
                allow_reboot=False, allow_recreate=False, force_reboot=False,
                max_concurrent_copy=5, sync=True, always_activate=False, repair=False, dry_activate=False):
        """Perform the deployment defined by the deployment specification."""

        self.evaluate_active(include, exclude, kill_obsolete)

        if evaluate_only:
            return

        # Assign each resource an index if it doesn't have one.
        for r in self.active_resources.itervalues():
            if r.index == None:
                r.index = self._get_free_resource_index()
                # FIXME: Logger should be able to do coloring without the need
                #        for an index maybe?
                r.logger.register_index(r.index)

        self.logger.update_log_prefixes()

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
                r._errored = False

            def worker(r):
                try:
                    if not should_do(r, include, exclude): return

                    # Sleep until all dependencies of this resource have
                    # been created.
                    deps = r.create_after(self.active_resources.itervalues(), self.definitions[r.name])
                    for dep in deps:
                        dep._created_event.wait()
                        # !!! Should we print a message here?
                        if dep._errored:
                            r._errored = True
                            return

                    # Now create the resource itself.
                    if not r.creation_time:
                        r.creation_time = int(time.time())
                    r.create(self.definitions[r.name], check=check, allow_reboot=allow_reboot, allow_recreate=allow_recreate)

                    if is_machine(r):
                        # The first time the machine is created,
                        # record the state version. We get it from
                        # /etc/os-release, rather than from the
                        # configuration's state.systemVersion
                        # attribute, because the machine may have been
                        # booted from an older NixOS image.
                        if not r.state_version:
                            os_release = r.run_command("cat /etc/os-release", capture_stdout=True)
                            match = re.search('VERSION_ID="([0-9]+\.[0-9]+).*"', os_release)
                            if match:
                                r.state_version = match.group(1)
                                r.log("setting state version to {0}".format(r.state_version))
                            else:
                                r.warn("cannot determine NixOS version")

                        r.wait_for_ssh(check=check)
                        r.generate_vpn_key()

                except:
                    r._errored = True
                    raise
                finally:
                    r._created_event.set()

            nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active_resources.itervalues(), worker_fun=worker)

        if create_only: return

        # Build the machine configurations.
        if dry_run:
            self.build_configs(dry_run=dry_run, repair=repair, include=include, exclude=exclude)
            return

        # Record configs_path in the state so that the ‘info’ command
        # can show whether machines have an outdated configuration.
        self.configs_path = self.build_configs(repair=repair, include=include, exclude=exclude)

        if build_only: return

        # Copy the closures of the machine configurations to the
        # target machines.
        self.copy_closures(self.configs_path, include=include, exclude=exclude,
                           max_concurrent_copy=max_concurrent_copy)

        if copy_only: return

        # Active the configurations.
        self.activate_configs(self.configs_path, include=include,
                              exclude=exclude, allow_reboot=allow_reboot,
                              force_reboot=force_reboot, check=check,
                              sync=sync, always_activate=always_activate, dry_activate=dry_activate)

        if dry_activate: return

        # Trigger cleanup of resources, e.g. disks that need to be detached etc. Needs to be
        # done after activation to make sure they are not in use anymore.
        def cleanup_worker(r):
            if not should_do(r, include, exclude): return

            # Now create the resource itself.
            r.after_activation(self.definitions[r.name])

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active_resources.itervalues(), worker_fun=cleanup_worker)
        self.logger.log(ansi_success("{0}> deployment finished successfully".format(self.name or "unnamed"), outfile=self.logger._log_file))

    def deploy(self, **kwargs):
        with self._get_deployment_lock():
            self._deploy(**kwargs)


    def _rollback(self, generation, include=[], exclude=[], check=False,
                  allow_reboot=False, force_reboot=False,
                  max_concurrent_copy=5, sync=True):
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
                    self.logger.log("machine ‘{0}’ is no longer obsolete".format(m.name))
                    m.obsolete = False
            else:
                self.logger.log("machine ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete: m.obsolete = True

        self.copy_closures(self.configs_path, include=include, exclude=exclude,
                           max_concurrent_copy=max_concurrent_copy)

        self.activate_configs(self.configs_path, include=include,
                              exclude=exclude, allow_reboot=allow_reboot,
                              force_reboot=force_reboot, check=check,
                              sync=sync, always_activate=True, dry_activate=False)


    def rollback(self, **kwargs):
        with self._get_deployment_lock():
            self._rollback(**kwargs)


    def _destroy_resources(self, include=[], exclude=[], wipe=False):

        for r in self.resources.itervalues():
            r._destroyed_event = threading.Event()
            r._errored = False
            for rev_dep in r.destroy_before(self.resources.itervalues()):
                try:
                    rev_dep._wait_for.append(r)
                except AttributeError:
                    rev_dep._wait_for = [ r ]

        def worker(m):
            try:
                if not should_do(m, include, exclude): return
                try:
                    for dep in m._wait_for:
                        dep._destroyed_event.wait()
                        # !!! Should we print a message here?
                        if dep._errored:
                            m._errored = True
                            return
                except AttributeError:
                    pass
                if m.destroy(wipe=wipe): self.delete_resource(m)
            except:
                m._errored = True
                raise
            finally:
                m._destroyed_event.set()

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.resources.values(), worker_fun=worker)

    def destroy_resources(self, include=[], exclude=[], wipe=False):
        """Destroy all active and obsolete resources."""

        with self._get_deployment_lock():
            self._destroy_resources(include, exclude, wipe)

        # Remove the destroyed machines from the rollback profile.
        # This way, a subsequent "nix-env --delete-generations old" or
        # "nix-collect-garbage -d" will get rid of the machine
        # configurations.
        if self.rollback_enabled: # and len(self.active) == 0:
            profile = self.create_profile()
            attrs = {m.name:
                     Call(RawValue("builtins.storePath"), m.cur_toplevel)
                     for m in self.active.itervalues() if m.cur_toplevel}
            if subprocess.call(
                ["nix-env", "-p", profile, "--set", "*", "-I", "nixops=" + self.expr_path,
                 "-f", "<nixops/update-profile.nix>",
                 "--arg", "machines", py2nix(attrs, inline=True)]) != 0:
                raise Exception("cannot update profile ‘{0}’".format(profile))


    def reboot_machines(self, include=[], exclude=[], wait=False,
                        rescue=False, hard=False):
        """Reboot all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            if rescue:
                m.reboot_rescue(hard=hard)
            elif wait:
                m.reboot_sync(hard=hard)
            else:
                m.reboot(hard=hard)

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def stop_machines(self, include=[], exclude=[]):
        """Stop all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.stop()

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def start_machines(self, include=[], exclude=[]):
        """Start all active machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.start()

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


    def is_valid_resource_name(self, name):
        p = re.compile('^[\w-]+$')
        return not p.match(name) is None


    def rename(self, name, new_name):
        if not name in self.resources:
            raise Exception("resource ‘{0}’ not found".format(name))
        if new_name in self.resources:
            raise Exception("resource with name ‘{0}’ already exists".format(new_name))
        if not self.is_valid_resource_name(new_name):
            raise Exception("{0} is not a valid resource identifier".format(new_name))

        self.logger.log("renaming resource ‘{0}’ to ‘{1}’...".format(name, new_name))

        m = self.resources.pop(name)
        self.resources[new_name] = m
        self._state._rename_resource(self.uuid, m.id, new_name)


    def send_keys(self, include=[], exclude=[]):
        """Send LUKS encryption keys to machines."""

        def worker(m):
            if not should_do(m, include, exclude): return
            m.send_keys()

        nixops.parallel.run_tasks(nr_workers=-1, tasks=self.active.itervalues(), worker_fun=worker)


def should_do(m, include, exclude):
    return should_do_n(m.name, include, exclude)

def should_do_n(name, include, exclude):
    if name in exclude: return False
    if include == []: return True
    return name in include

def is_machine(r):
    return isinstance(r, nixops.backends.MachineState)

def is_machine_defn(r):
    return isinstance(r, nixops.backends.MachineDefinition)


def _subclasses(cls):
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]

def _create_definition(xml, config, type_name):
    """Create a resource definition object from the given XML representation of the machine's attributes."""

    for cls in _subclasses(nixops.resources.ResourceDefinition):
        if type_name == cls.get_resource_type():
            # FIXME: backward compatibility hack
            if len(inspect.getargspec(cls.__init__).args) == 2:
                return cls(xml)
            else:
                return cls(xml, config)

    raise nixops.deployment.UnknownBackend("unknown resource type ‘{0}’".format(type_name))


# Automatically load all resource types.
def _load_modules_from(dir):
    for module in os.listdir(os.path.dirname(__file__) + "/" + dir):
        if module[-3:] != '.py' or module == "__init__.py": continue
        __import__("nixops." + dir + "." + module[:-3], globals(), locals())

_load_modules_from("backends")
_load_modules_from("resources")
