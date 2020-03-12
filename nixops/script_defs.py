# -*- coding: utf-8 -*-

from nixops.nix_expr import py2nix
from nixops.parallel import MultipleExceptions, run_tasks
import pluggy

import contextlib
import nixops.statefile
import prettytable
from argparse import ArgumentParser, _SubParsersAction, Namespace
import os
import pwd
import re
import sys
import subprocess
import nixops.parallel
import nixops.util
import nixops.known_hosts
import time
import logging
import logging.handlers
import syslog
import json
import pipes
from typing import Tuple, List, Optional, Union, Any, Generator
from datetime import datetime
from pprint import pprint
import importlib

from nixops.plugins import get_plugin_manager


pm = get_plugin_manager()
[
    [importlib.import_module(mod) for mod in pluginimports]
    for pluginimports in pm.hook.load()
]


@contextlib.contextmanager
def deployment(args: Namespace) -> Generator[nixops.deployment.Deployment, None, None]:
    with network_state(args) as sf:
        depl = open_deployment(sf, args)
        yield depl


@contextlib.contextmanager
def network_state(args: Namespace) -> Generator[nixops.statefile.StateFile, None, None]:
    state = nixops.statefile.StateFile(args.state_file)
    try:
        yield state
    finally:
        state.close()


def op_list_plugins(args):
    if args.verbose:
        tbl = create_table([("Installed Plugins", "c"), ("Plugin Reference", "c")])
    else:
        tbl = create_table([("Installed Plugins", "c")])
    for plugin in sorted(pm.list_name_plugin()):
        if args.verbose:
            tbl.add_row([plugin[0], plugin[1].__str__()])
        else:
            tbl.add_row([plugin[0]])
    print(tbl)


def create_table(headers: List[Tuple[str, str]]) -> prettytable.PrettyTable:
    tbl = prettytable.PrettyTable([name for (name, align) in headers])
    for (name, align) in headers:
        tbl.align[name] = align
    return tbl


def sort_deployments(
    depls: List[nixops.deployment.Deployment],
) -> List[nixops.deployment.Deployment]:
    return sorted(depls, key=lambda depl: (depl.name or depl.uuid, depl.uuid))


# Handle the --all switch: if --all is given, return all deployments;
# otherwise, return the deployment specified by -d /
# $NIXOPS_DEPLOYMENT.
@contextlib.contextmanager
def one_or_all(
    args: Namespace,
) -> Generator[List[nixops.deployment.Deployment], None, None]:
    with network_state(args) as sf:
        if args.all:
            yield sf.get_all_deployments()
        else:
            yield [open_deployment(sf, args)]


def op_list_deployments(args):
    with network_state(args) as sf:
        tbl = create_table(
            [
                ("UUID", "l"),
                ("Name", "l"),
                ("Description", "l"),
                ("# Machines", "r"),
                ("Type", "c"),
            ]
        )
        for depl in sort_deployments(sf.get_all_deployments()):
            tbl.add_row(
                [
                    depl.uuid,
                    depl.name or "(none)",
                    depl.description,
                    len(depl.machines),
                    ", ".join(set(m.get_type() for m in depl.machines.values())),
                ]
            )
        print(tbl)


def open_deployment(sf: nixops.statefile.StateFile, args: Namespace):
    depl = sf.open_deployment(uuid=args.deployment)

    depl.extra_nix_path = sum(args.nix_path or [], [])
    for (n, v) in args.nix_options or []:
        depl.extra_nix_flags.extend(["--option", n, v])
    if args.max_jobs != None:
        depl.extra_nix_flags.extend(["--max-jobs", str(args.max_jobs)])
    if args.cores != None:
        depl.extra_nix_flags.extend(["--cores", str(args.cores)])
    if args.keep_going:
        depl.extra_nix_flags.append("--keep-going")
    if args.keep_failed:
        depl.extra_nix_flags.append("--keep-failed")
    if args.show_trace:
        depl.extra_nix_flags.append("--show-trace")
    if args.fallback:
        depl.extra_nix_flags.append("--fallback")
    if args.no_build_output:
        depl.extra_nix_flags.append("--no-build-output")
    if not args.read_only_mode:
        depl.extra_nix_eval_flags.append("--read-write-mode")

    return depl


def set_name(depl: nixops.deployment.Deployment, name: Optional[str]):
    if not name:
        return
    if not re.match("^[a-zA-Z_\-][a-zA-Z0-9_\-\.]*$", name):
        raise Exception("invalid deployment name ‘{0}’".format(name))
    depl.name = name


def modify_deployment(args, depl: nixops.deployment.Deployment):
    nix_exprs = args.nix_exprs
    templates = args.templates or []
    for i in templates:
        nix_exprs.append("<nixops/templates/{0}.nix>".format(i))
    if len(nix_exprs) == 0:
        raise Exception("you must specify the path to a Nix expression and/or use ‘-t’")
    depl.nix_exprs = [os.path.abspath(x) if x[0:1] != "<" else x for x in nix_exprs]
    depl.nix_path = [nixops.util.abs_nix_path(x) for x in sum(args.nix_path or [], [])]


def op_create(args):
    with network_state(args) as sf:
        depl = sf.create_deployment()
        sys.stderr.write("created deployment ‘{0}’\n".format(depl.uuid))
        modify_deployment(args, depl)
        if args.name or args.deployment:
            set_name(depl, args.name or args.deployment)
        sys.stdout.write(depl.uuid + "\n")


def op_modify(args):
    with deployment(args) as depl:
        modify_deployment(args, depl)
        if args.name:
            set_name(depl, args.name)


def op_clone(args):
    with deployment(args) as depl:
        depl2 = depl.clone()
        sys.stderr.write("created deployment ‘{0}’\n".format(depl2.uuid))
        set_name(depl2, args.name)
        sys.stdout.write(depl2.uuid + "\n")


def op_delete(args):
    with one_or_all(args) as depls:
        for depl in depls:
            depl.delete(force=args.force or False)


def machine_to_key(depl: str, name: str, type: str) -> Tuple[str, str, List[object]]:
    xs = [int(x) if x.isdigit() else x for x in re.split("(\d+)", name)]
    return (depl, type, xs)


def op_info(args):
    table_headers = [
        ("Name", "l"),
        ("Status", "c"),
        ("Type", "l"),
        ("Resource Id", "l"),
        ("IP address", "l"),
    ]

    def state(
        depl: nixops.deployment.Deployment,
        d: Optional[nixops.resources.ResourceDefinition],
        m: nixops.backends.MachineState,
    ) -> str:
        if d and m.obsolete:
            return "Revived"
        if d is None and m.obsolete:
            return "Obsolete"
        if depl.configs_path != m.cur_configs_path:
            return "Outdated"

        return "Up-to-date"

    def do_eval(depl):
        if not args.no_eval:
            try:
                depl.evaluate()
            except nixops.deployment.NixEvalError:
                sys.stderr.write(
                    nixops.util.ansi_warn(
                        "warning: evaluation of the deployment specification failed; status info may be incorrect\n\n"
                    )
                )
                depl.definitions = None

    def print_deployment(depl: nixops.deployment.Deployment) -> None:
        definitions = depl.definitions or {}

        # Sort machines by type, then name.  Sort numbers in machine
        # names numerically (e.g. "foo10" comes after "foo9").
        def name_to_key(name: str) -> Tuple[str, str, List[object]]:
            d: Optional[nixops.resources.ResourceDefinition] = definitions.get(name)
            r: Optional[nixops.resources.ResourceState] = depl.resources.get(name)
            if r:
                key = machine_to_key(depl.uuid, name, r.get_type())
            elif d:
                key = machine_to_key(depl.uuid, name, d.get_type())
            else:
                key = machine_to_key(depl.uuid, name, "")

            return key

        names = sorted(
            set(definitions.keys()) | set(depl.resources.keys()), key=name_to_key
        )

        for name in names:
            d = definitions.get(name)
            r = depl.resources.get(name)

            resource_state: str = "Missing"
            if isinstance(r, nixops.backends.MachineState):
                resource_state = "{0} / {1}".format(r.show_state(), state(depl, d, r))
            elif r:
                resource_state = r.show_state()

            user_type: str = "unknown-type"
            if r:
                user_type = r.show_type()
            elif d:
                user_type = d.show_type()

            public_ipv4: str = ""
            private_ipv4: str = ""
            if isinstance(r, nixops.backends.MachineState):
                public_ipv4 = r.public_ipv4 or ""
                private_ipv4 = r.private_ipv4 or ""

            if args.plain:
                print(
                    "\t".join(
                        ([depl.uuid, depl.name or "(none)"] if args.all else [])
                        + [
                            name,
                            resource_state.lower(),
                            user_type,
                            r.resource_id or "" if r else "",
                            public_ipv4,
                            private_ipv4,
                        ]
                    )
                )
            else:
                tbl.add_row(
                    ([depl.name or depl.uuid] if args.all else [])
                    + [
                        name,
                        resource_state,
                        user_type,
                        r.resource_id or "" if r else "",
                        public_ipv4 or private_ipv4,
                    ]
                )

    if args.all:
        with network_state(args) as sf:
            if not args.plain:
                tbl = create_table([("Deployment", "l")] + table_headers)
            for depl in sort_deployments(sf.get_all_deployments()):
                do_eval(depl)
                print_deployment(depl)
            if not args.plain:
                print(tbl)

    else:
        with deployment(args) as depl:
            do_eval(depl)

            if args.plain:
                print_deployment(depl)
            else:
                print("Network name:", depl.name or "(none)")
                print("Network UUID:", depl.uuid)
                print("Network description:", depl.description)
                print("Nix expressions:", " ".join(depl.nix_exprs))
                if depl.nix_path != []:
                    print("Nix path:", " ".join(["-I " + x for x in depl.nix_path]))
                if depl.rollback_enabled:
                    print("Nix profile:", depl.get_profile())
                if depl.args != {}:
                    print(
                        "Nix arguments:",
                        ", ".join([n + " = " + v for n, v in depl.args.items()]),
                    )
                print()
                tbl = create_table(table_headers)
                print_deployment(depl)
                print(tbl)


def op_check(args):
    def highlight(s):
        return nixops.util.ansi_highlight(s, outfile=sys.stdout)

    def warn(s):
        return nixops.util.ansi_warn(s, outfile=sys.stdout)

    def render_tristate(x):
        if x == None:
            return "N/A"
        elif x:
            return nixops.util.ansi_success("Yes", outfile=sys.stdout)
        else:
            return warn("No")

    tbl = create_table(
        ([("Deployment", "l")] if args.all else [])
        + [
            ("Name", "l"),
            ("Exists", "l"),
            ("Up", "l"),
            ("Reachable", "l"),
            ("Disks OK", "l"),
            ("Load avg.", "l"),
            ("Units", "l"),
            ("Notes", "l"),
        ]
    )

    machines: List[nixops.backends.MachineState] = []
    resources: List[nixops.resources.ResourceState] = []

    def check(depl: nixops.deployment.Deployment):
        for m in depl.active_resources.values():
            if not nixops.deployment.should_do(
                m, args.include or [], args.exclude or []
            ):
                continue
            if isinstance(m, nixops.backends.MachineState):
                machines.append(m)
            else:
                resources.append(m)

    with one_or_all(args) as depls:
        for depl in depls:
            check(depl)

    ResourceStatus = Tuple[
        str,
        Union[nixops.backends.MachineState, nixops.resources.ResourceState],
        List[str],
        int,
    ]

    # Check all machines in parallel.
    def worker(m: nixops.backends.MachineState) -> ResourceStatus:
        res = m.check()

        unit_lines = []
        if res.failed_units:
            unit_lines.append(
                "\n".join([warn("{0} [failed]".format(x)) for x in res.failed_units])
            )
        if res.in_progress_units:
            unit_lines.append(
                "\n".join(
                    [
                        highlight("{0} [running]".format(x))
                        for x in res.in_progress_units
                    ]
                )
            )

        row = ([m.depl.name or m.depl.uuid] if args.all else []) + [
            m.name,
            render_tristate(res.exists),
            render_tristate(res.is_up),
            render_tristate(res.is_reachable),
            render_tristate(res.disks_ok),
            "{0} {1} {2}".format(res.load[0], res.load[1], res.load[2])
            if res.load != None
            else "",
            "\n".join(unit_lines),
            "\n".join([warn(x) for x in res.messages]),
        ]
        status = 0
        if res.exists == False:
            status |= 1
        if res.is_up == False:
            status |= 2
        if res.is_reachable == False:
            status |= 4
        if res.disks_ok == False:
            status |= 8
        if res.failed_units != None and res.failed_units != []:
            status |= 16
        return (m.depl.name or m.depl.uuid, m, row, status)

    resources_tbl = create_table(
        ([("Deployment", "l")] if args.all else []) + [("Name", "l"), ("Exists", "l")]
    )

    def resource_worker(r: nixops.resources.ResourceState) -> Optional[ResourceStatus]:
        if not nixops.deployment.is_machine(r):
            r.check()
            exist = True if r.state == nixops.resources.ResourceState.UP else False
            row = ([r.depl.name or r.depl.uuid] if args.all else []) + [
                r.name,
                render_tristate(exist),
            ]
            return (r.depl.name or r.depl.uuid, r, row, 0)
        return None

    results = run_tasks(nr_workers=len(machines), tasks=machines, worker_fun=worker)
    resources_results = run_tasks(
        nr_workers=len(resources), tasks=resources, worker_fun=resource_worker
    )

    # Sort the rows by deployment/machine.
    status = 0
    for res in sorted(
        [res for res in results if res is not None],
        key=lambda res: machine_to_key(res[0], res[1].name, res[1].get_type()),
    ):
        tbl.add_row(res[2])
        status |= res[3]
    print(nixops.util.ansi_success("Machines state:"))
    print(tbl)

    for res in sorted(
        [res for res in resources_results if res is not None],
        key=lambda res: machine_to_key(res[0], res[1].name, res[1].get_type()),
    ):
        resources_tbl.add_row(res[2])
        status |= res[3]
    print(nixops.util.ansi_success("Non machines resources state:"))
    print(resources_tbl)

    sys.exit(status)


def print_backups(depl, backups):
    tbl = prettytable.PrettyTable(["Backup ID", "Status", "Info"])
    for k, v in sorted(backups.items(), reverse=True):
        tbl.add_row([k, v["status"], "\n".join(v["info"])])
    print(tbl)


def op_clean_backups(args):
    if args.keep and args.keep_days:
        raise Exception(
            "Combining of --keep and --keep-days arguments are not possible, please use one."
        )
    if not (args.keep or args.keep_days):
        raise Exception("Please specify at least --keep or --keep-days arguments.")
    with deployment(args) as depl:
        depl.clean_backups(args.keep, args.keep_days, args.keep_physical)


def op_remove_backup(args):
    with deployment(args) as depl:
        depl.remove_backup(args.backupid, args.keep_physical)


def op_backup(args):
    with deployment(args) as depl:

        def do_backup():
            backup_id = depl.backup(
                include=args.include or [],
                exclude=args.exclude or [],
                devices=args.devices or [],
            )
            print(backup_id)

        if args.force:
            do_backup()
        else:
            backups = depl.get_backups(
                include=args.include or [], exclude=args.exclude or []
            )
            backups_status = [b["status"] for _, b in backups.items()]
            if "running" in backups_status:
                raise Exception(
                    "There are still backups running, use --force to run a new backup concurrently (not advised!)"
                )
            else:
                do_backup()


def op_backup_status(args):
    with deployment(args) as depl:
        backupid = args.backupid
        while True:
            backups = depl.get_backups(
                include=args.include or [], exclude=args.exclude or []
            )

            if backupid or args.latest:
                sorted_backups = sorted(backups.keys(), reverse=True)
                if args.latest:
                    if len(backups) == 0:
                        raise Exception("no backups found")
                    backupid = sorted_backups[0]
                if backupid not in backups:
                    raise Exception("backup ID ‘{0}’ does not exist".format(backupid))
                _backups = {}
                _backups[backupid] = backups[backupid]
            else:
                _backups = backups

            print_backups(depl, _backups)

            backups_status = [b["status"] for _, b in _backups.items()]
            if "running" in backups_status:
                if args.wait:
                    print("waiting for 30 seconds...")
                    time.sleep(30)
                else:
                    raise Exception("backup has not yet finished")
            else:
                return


def op_restore(args):
    with deployment(args) as depl:
        depl.restore(
            include=args.include or [],
            exclude=args.exclude or [],
            backup_id=args.backup_id,
            devices=args.devices or [],
        )


def op_deploy(args):
    with deployment(args) as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        if args.evaluate_only:
            raise Exception("--evaluate-only was removed as it's the same as --dry-run")
        depl.deploy(
            dry_run=args.dry_run,
            test=args.test,
            build_only=args.build_only,
            plan_only=args.plan_only,
            create_only=args.create_only,
            copy_only=args.copy_only,
            include=args.include or [],
            exclude=args.exclude or [],
            check=args.check,
            kill_obsolete=args.kill_obsolete,
            allow_reboot=args.allow_reboot,
            allow_recreate=args.allow_recreate,
            force_reboot=args.force_reboot,
            max_concurrent_copy=args.max_concurrent_copy,
            sync=not args.no_sync,
            always_activate=args.always_activate,
            repair=args.repair,
            dry_activate=args.dry_activate,
            max_concurrent_activate=args.max_concurrent_activate,
        )


def op_send_keys(args):
    with deployment(args) as depl:
        depl.send_keys(include=args.include or [], exclude=args.exclude or [])


def op_set_args(args):
    with deployment(args) as depl:
        for [n, v] in args.args or []:
            depl.set_arg(n, v)
        for [n, v] in args.argstrs or []:
            depl.set_argstr(n, v)
        for [n] in args.unset or []:
            depl.unset_arg(n)


def op_destroy(args):
    with one_or_all(args) as depls:
        for depl in depls:
            if args.confirm:
                depl.logger.set_autoresponse("y")
            depl.destroy_resources(
                include=args.include or [], exclude=args.exclude or [], wipe=args.wipe
            )


def op_reboot(args):
    with deployment(args) as depl:
        depl.reboot_machines(
            include=args.include or [],
            exclude=args.exclude or [],
            wait=(not args.no_wait),
            rescue=args.rescue,
            hard=args.hard,
        )


def op_delete_resources(args):
    with deployment(args) as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        depl.delete_resources(include=args.include or [], exclude=args.exclude or [])


def op_stop(args):
    with deployment(args) as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        depl.stop_machines(include=args.include or [], exclude=args.exclude or [])


def op_start(args):
    with deployment(args) as depl:
        depl.start_machines(include=args.include or [], exclude=args.exclude or [])


def op_rename(args):
    with deployment(args) as depl:
        depl.rename(args.current_name, args.new_name)


def print_physical_backup_spec(depl, backupid):
    config = {}
    for m in depl.active.values():
        config[m.name] = m.get_physical_backup_spec(backupid)
    sys.stdout.write(py2nix(config))


def op_show_arguments(args):
    with deployment(args) as depl:
        tbl = create_table([("Name", "l"), ("Location", "l")])
        args = depl.get_arguments()
        for arg in sorted(args.keys()):
            files = sorted(args[arg])
            tbl.add_row([arg, "\n".join(files)])
        print(tbl)


def op_show_physical(args):
    with deployment(args) as depl:
        if args.backupid:
            print_physical_backup_spec(depl, args.backupid)
            return
        depl.evaluate()
        sys.stdout.write(depl.get_physical_spec())


def op_dump_nix_paths(args):
    def get_nix_path(p):
        if p is None:
            return None
        p = os.path.realpath(os.path.abspath(p))
        # FIXME: hardcoded nix store
        nix_store = "/nix/store"
        if not p.startswith("{0}/".format(nix_store)):
            return None
        return "/".join(p.split("/")[: len(nix_store.split("/")) + 1])

    def strip_nix_path(p):
        p = p.split("=")
        if len(p) == 1:
            return p[0]
        else:
            return p[1]

    def nix_paths(depl) -> List[str]:
        candidates = (
            depl.nix_exprs
            + [strip_nix_path(p) for p in depl.nix_path]
            + [depl.configs_path]
        )
        candidates = [get_nix_path(p) for p in candidates]
        return [p for p in candidates if not p is None]

    paths: List[str] = []

    with one_or_all(args) as depls:
        for depl in depls:
            paths.extend(nix_paths(depl))

    for p in paths:
        print(p)


def op_export(args):
    res = {}

    with one_or_all(args) as depls:
        for depl in depls:
            res[depl.uuid] = depl.export()
    print(json.dumps(res, indent=2, sort_keys=True))


def op_import(args):
    with network_state(args) as sf:
        existing = set(sf.query_deployments())

        dump = json.loads(sys.stdin.read())
        for uuid, attrs in dump.items():
            if uuid in existing:
                raise Exception(
                    "state file already contains a deployment with UUID ‘{0}’".format(
                        uuid
                    )
                )
            with sf._db:
                depl = sf.create_deployment(uuid=uuid)
                depl.import_(attrs)
            sys.stderr.write("added deployment ‘{0}’\n".format(uuid))

            if args.include_keys:
                for m in depl.active.values():
                    if nixops.deployment.is_machine(m) and hasattr(
                        m, "public_host_key"
                    ):
                        if m.public_ipv4:
                            nixops.known_hosts.add(m.public_ipv4, m.public_host_key)
                        if m.private_ipv4:
                            nixops.known_hosts.add(m.private_ipv4, m.public_host_key)


def parse_machine(name):
    return ("root", name) if name.find("@") == -1 else name.split("@", 1)


def op_ssh(args):
    with deployment(args) as depl:
        (username, machine) = parse_machine(args.machine)
        m = depl.machines.get(machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(machine))
        flags, command = m.ssh.split_openssh_args(args.args)
        user = None if username == "root" else username
        sys.exit(
            m.ssh.run_command(
                command,
                flags,
                check=False,
                logged=False,
                allow_ssh_args=True,
                user=user,
            )
        )


def op_ssh_for_each(args):
    results: List[Optional[int]] = []
    with one_or_all(args) as depls:
        for depl in depls:

            def worker(m: nixops.backends.MachineState) -> Optional[int]:
                if not nixops.deployment.should_do(
                    m, args.include or [], args.exclude or []
                ):
                    return None
                return m.ssh.run_command_get_status(
                    args.args, allow_ssh_args=True, check=False
                )

            results = results + nixops.parallel.run_tasks(
                nr_workers=len(depl.machines) if args.parallel else 1,
                tasks=iter(depl.active.values()),
                worker_fun=worker,
            )

    sys.exit(max(results) if results != [] else 0)


def scp_loc(user, ssh_name, remote, loc):
    return "{0}@{1}:{2}".format(user, ssh_name, loc) if remote else loc


def op_scp(args):
    if args.scp_from == args.scp_to:
        raise Exception("exactly one of ‘--from’ and ‘--to’ must be specified")
    with deployment(args) as depl:
        (username, machine) = parse_machine(args.machine)
        m = depl.machines.get(machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(machine))
        ssh_name = m.get_ssh_name()
        from_loc = scp_loc(username, ssh_name, args.scp_from, args.source)
        to_loc = scp_loc(username, ssh_name, args.scp_to, args.destination)
        print("{0} -> {1}".format(from_loc, to_loc), file=sys.stderr)
        flags = ["scp", "-r"] + m.get_ssh_flags() + [from_loc, to_loc]
        # Map ssh's ‘-p’ to scp's ‘-P’.
        flags = ["-P" if f == "-p" else f for f in flags]
        res = subprocess.call(flags)
        sys.exit(res)


def op_mount(args):
    with deployment(args) as depl:
        (username, rest) = parse_machine(args.machine)
        (machine, remote_path) = (
            (rest, "/") if rest.find(":") == -1 else rest.split(":", 1)
        )
        m = depl.machines.get(machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(machine))
        ssh_name = m.get_ssh_name()

        flags = m.get_ssh_flags()
        new_flags = []
        n = 0
        while n < len(flags):
            if flags[n] == "-i":
                new_flags.extend(["-o", "IdentityFile=" + flags[n + 1]])
                n = n + 2
            elif flags[n] == "-p":
                new_flags.extend(["-p", flags[n + 1]])
                n = n + 2
            elif flags[n] == "-o":
                new_flags.extend(["-o", flags[n + 1]])
                n = n + 2
            else:
                raise Exception(
                    "don't know how to pass SSH flag ‘{0}’ to sshfs".format(flags[n])
                )

        for o in args.sshfs_option or []:
            new_flags.extend(["-o", o])

        # Note: sshfs will go into the background when it has finished
        # setting up, so we can safely delete the SSH identity file
        # afterwards.
        res = subprocess.call(
            ["sshfs", username + "@" + ssh_name + ":" + remote_path, args.destination]
            + new_flags
        )
        sys.exit(res)


def op_show_option(args):
    with deployment(args) as depl:
        if args.include_physical:
            depl.evaluate()
        sys.stdout.write(
            depl.evaluate_option_value(
                args.machine,
                args.option,
                json=args.json,
                xml=args.xml,
                include_physical=args.include_physical,
            )
        )


@contextlib.contextmanager
def deployment_with_rollback(args):
    with deployment(args) as depl:
        if not depl.rollback_enabled:
            raise Exception(
                "rollback is not enabled for this network; please set ‘network.enableRollback’ to ‘true’ and redeploy"
            )
        yield depl


def op_list_generations(args):
    with deployment_with_rollback(args) as depl:
        if (
            subprocess.call(["nix-env", "-p", depl.get_profile(), "--list-generations"])
            != 0
        ):
            raise Exception("nix-env --list-generations failed")


def op_delete_generation(args):
    with deployment_with_rollback(args) as depl:
        if (
            subprocess.call(
                [
                    "nix-env",
                    "-p",
                    depl.get_profile(),
                    "--delete-generations",
                    str(args.generation),
                ]
            )
            != 0
        ):
            raise Exception("nix-env --delete-generations failed")


def op_rollback(args):
    with deployment_with_rollback(args) as depl:
        depl.rollback(
            generation=args.generation,
            include=args.include or [],
            exclude=args.exclude or [],
            check=args.check,
            allow_reboot=args.allow_reboot,
            force_reboot=args.force_reboot,
            max_concurrent_copy=args.max_concurrent_copy,
            max_concurrent_activate=args.max_concurrent_activate,
            sync=not args.no_sync,
        )


def op_show_console_output(args):
    with deployment(args) as depl:
        m = depl.machines.get(args.machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(args.machine))
        sys.stdout.write(m.get_console_output())


def op_edit(args):
    with deployment(args) as depl:
        editor = os.environ.get("EDITOR")
        if not editor:
            raise Exception("the $EDITOR environment variable is not set")
        os.system("$EDITOR " + " ".join([pipes.quote(x) for x in depl.nix_exprs]))


def op_copy_closure(args):
    with deployment(args) as depl:
        (username, machine) = parse_machine(args.machine)
        m = depl.machines.get(machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(machine))
        env = dict(os.environ)
        env["NIX_SSHOPTS"] = " ".join(m.get_ssh_flags())
        res = nixops.util.logged_exec(
            [
                "nix",
                "copy",
                "--to",
                "ssh://{}".format(m.get_ssh_name()),
                args.storepath,
            ],
            m.logger,
            env=env,
        )
        sys.exit(res)


# Set up logging of all commands and output
def setup_logging(args):
    if os.path.exists("/dev/log") and not args.op in [
        op_ssh,
        op_ssh_for_each,
        op_scp,
        op_mount,
        op_info,
        op_list_deployments,
        op_list_generations,
        op_backup_status,
        op_show_console_output,
        op_dump_nix_paths,
        op_export,
        op_show_physical,
    ]:
        # determine user
        try:
            user = subprocess.check_output(
                ["logname"], stderr=subprocess.PIPE, text=True
            ).strip()
        except:
            user = pwd.getpwuid(os.getuid())[0]

        logger = logging.getLogger("root")
        logger.setLevel(logging.INFO)

        handler = logging.handlers.SysLogHandler(address="/dev/log")
        formatter = logging.Formatter("nixops[{0}]: %(message)s".format(os.getpid()))
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.info("User: {0}, Command: {1}".format(user, " ".join(sys.argv)))

        # pass all stdout/stderr to the logger as well
        nixops.util.TeeStderr()
        nixops.util.TeeStdout()


def add_subparser(
    subparsers: _SubParsersAction, name: str, help: str
) -> ArgumentParser:
    subparser = subparsers.add_parser(name, help=help)
    subparser.add_argument(
        "--state",
        "-s",
        dest="state_file",
        metavar="FILE",
        default=nixops.statefile.get_default_state_file(),
        help="path to state file",
    )
    subparser.add_argument(
        "--deployment",
        "-d",
        dest="deployment",
        metavar="UUID_OR_NAME",
        default=os.environ.get(
            "NIXOPS_DEPLOYMENT", os.environ.get("CHARON_DEPLOYMENT", None)
        ),
        help="UUID or symbolic name of the deployment",
    )
    subparser.add_argument("--debug", action="store_true", help="enable debug output")
    subparser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm dangerous operations; do not ask",
    )

    # Nix options that we pass along.
    subparser.add_argument(
        "-I",
        nargs=1,
        action="append",
        dest="nix_path",
        metavar="PATH",
        help="append a directory to the Nix search path",
    )
    subparser.add_argument(
        "--max-jobs",
        "-j",
        type=int,
        metavar="N",
        help="set maximum number of concurrent Nix builds",
    )
    subparser.add_argument(
        "--cores",
        type=int,
        metavar="N",
        help="sets the value of the NIX_BUILD_CORES environment variable in the invocation of builders",
    )
    subparser.add_argument(
        "--keep-going", action="store_true", help="keep going after failed builds"
    )
    subparser.add_argument(
        "--keep-failed",
        "-K",
        action="store_true",
        help="keep temporary directories of failed builds",
    )
    subparser.add_argument(
        "--show-trace",
        action="store_true",
        help="print a Nix stack trace if evaluation fails, or a python stack trace if nixops fails",
    )
    subparser.add_argument(
        "--fallback", action="store_true", help="fall back on installation from source"
    )
    subparser.add_argument(
        "--no-build-output",
        action="store_true",
        help="suppress output written by builders",
    )
    subparser.add_argument(
        "--option",
        nargs=2,
        action="append",
        dest="nix_options",
        metavar=("NAME", "VALUE"),
        help="set a Nix option",
    )
    subparser.add_argument(
        "--read-only-mode",
        action="store_true",
        help="run Nix evaluations in read-only mode",
    )

    return subparser


def add_common_modify_options(subparser: ArgumentParser):
    subparser.add_argument(
        "nix_exprs",
        nargs="*",
        metavar="NIX-FILE",
        help="Nix expression(s) defining the network",
    )
    subparser.add_argument(
        "--template",
        "-t",
        action="append",
        dest="templates",
        metavar="TEMPLATE",
        help="name of template to be used",
    )


def add_common_deployment_options(subparser: ArgumentParser):
    subparser.add_argument(
        "--include",
        nargs="+",
        metavar="MACHINE-NAME",
        help="perform deployment actions on the specified machines only",
    )
    subparser.add_argument(
        "--exclude",
        nargs="+",
        metavar="MACHINE-NAME",
        help="do not perform deployment actions on the specified machines",
    )
    subparser.add_argument(
        "--check",
        action="store_true",
        help="do not assume that the recorded state is correct",
    )
    subparser.add_argument(
        "--allow-reboot", action="store_true", help="reboot machines if necessary"
    )
    subparser.add_argument(
        "--force-reboot", action="store_true", help="reboot machines unconditionally"
    )
    subparser.add_argument(
        "--max-concurrent-copy",
        type=int,
        default=5,
        metavar="N",
        help="maximum number of concurrent nix-copy-closure processes",
    )
    subparser.add_argument(
        "--max-concurrent-activate",
        type=int,
        default=-1,
        metavar="N",
        help="maximum number of concurrent machine activations",
    )
    subparser.add_argument(
        "--no-sync", action="store_true", help="do not flush buffers to disk"
    )


def error(msg):
    sys.stderr.write(nixops.util.ansi_warn("error: ") + msg + "\n")


def parser_plugin_hooks(parser, subparsers):
    pm.hook.parser(parser=parser, subparsers=subparsers)
