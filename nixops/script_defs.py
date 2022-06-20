# -*- coding: utf-8 -*-

from pathlib import Path
from urllib.parse import ParseResult, urlparse, unquote
from nixops.nix_expr import nix_attribute2py_list, py2nix
from nixops.parallel import run_tasks
from nixops.storage import StorageBackend, StorageInterface
from nixops.locks import LockDriver, LockInterface

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
import json
from tempfile import TemporaryDirectory
import pipes
from typing import Tuple, List, Optional, Union, Generator, Type, Set, Sequence
import nixops.ansi

from nixops.plugins.manager import PluginManager

from nixops.plugins import get_plugin_manager
from nixops.evaluation import eval_network, NetworkEval, NixEvalError, NetworkFile
from nixops.backends import MachineDefinition


PluginManager.load()


def get_network_file(args: Namespace) -> NetworkFile:
    # Check that we don't try to build flake and classic nix at the same time
    if args.network_dir != None and args.flake != None:
        raise ValueError("Both --network and --flake can't be set simultany")

    # We use flake.
    if args.flake != None:
        flake: str = args.flake
        url: ParseResult = urlparse(flake)

        # Get the attribute or default if there is none
        quote_attribute = url.fragment if url.fragment else "default"
        # Decode % encoded
        attribute = unquote(quote_attribute)

        path: str = url.path
        # If it's a file or a directory get the absolute path
        if url.scheme in ["file", "path", ""]:
            # resolve it
            path = str(Path(path).absolute())

        # Create new url with absolute path and remove fragment (attribute)
        url = ParseResult(url.scheme, url.netloc, path, url.params, url.query, "")

        # Get the reference without the attribute
        reference = url.geturl()

        # split the path to pass it to the nix expression
        attribute_list: List[str] = nix_attribute2py_list(attribute)
        attribute_path: str = "[ " + " ".join(attribute_list) + " ]"

        # create the network with the reference and the attribute
        return NetworkFile(reference, attribute_path)

    # we don't use flake.

    # default value of network_dir is None in args but it's current working
    # dirrectory
    network_dir_name: str = os.getcwd() if args.network_dir == None else args.network_dir
    # get real path
    network_dir: str = os.path.abspath(network_dir_name)

    # check that the folder exist
    if not os.path.exists(network_dir):
        raise ValueError(f"{network_dir} does not exist")

    # path to the classic entry point file
    classic_path = os.path.join(network_dir, "nixops.nix")
    # path to the flake entry point file
    flake_path = os.path.join(network_dir, "flake.nix")

    # check existing
    classic_exists: bool = os.path.exists(classic_path)
    flake_exists: bool = os.path.exists(flake_path)

    # don't decide for the user, raise an exception.
    if all((flake_exists, classic_exists)):
        raise ValueError("Both flake.nix and nixops.nix cannot coexist")

    if classic_exists:
        # just return the network with no flake
        return NetworkFile(network=classic_path, attribute=None)

    if flake_exists:
        # return the flake path as network and the output attibute.
        # TODO: depricate this version in favor of the --flake
        return NetworkFile(network=network_dir, attribute='["default"]')

    # it's nether a flake or a classic build.
    raise ValueError(
        f"Flake not provided and neither flake.nix nor nixops.nix exists in {network_dir}"
    )


def set_common_depl(depl: nixops.deployment.Deployment, args: Namespace) -> None:
    network_file = get_network_file(args)
    depl.network_expr = network_file


@contextlib.contextmanager
def deployment(
    args: Namespace, writable: bool, activityDescription: str
) -> Generator[nixops.deployment.Deployment, None, None]:
    with network_state(args, writable, description=activityDescription) as sf:
        depl = open_deployment(sf, args)
        set_common_depl(depl, args)
        yield depl


def get_lock(network: NetworkEval) -> LockInterface:
    lock: LockInterface
    lock_class: Type[LockDriver]
    lock_drivers = PluginManager.lock_drivers()
    try:
        lock_class = lock_drivers[network.lock.provider]
    except KeyError:
        sys.stderr.write(
            nixops.ansi.ansi_warn(
                f"The network requires the '{network.lock.provider}' lock driver, "
                "but no plugin provides it.\n"
            )
        )
        raise Exception("Missing lock driver plugin.")
    else:
        lock_class_options = lock_class.options(**network.lock.configuration)
        lock = lock_class(lock_class_options)
    return lock


@contextlib.contextmanager
def network_state(
    args: Namespace, writable: bool, description: str, doLock: bool = True
) -> Generator[nixops.statefile.StateFile, None, None]:
    network = eval_network(get_network_file(args))
    storage_backends = PluginManager.storage_backends()
    storage_class: Optional[Type[StorageBackend]] = storage_backends.get(
        network.storage.provider
    )
    if storage_class is None:
        sys.stderr.write(
            nixops.ansi.ansi_warn(
                f"The network requires the '{network.storage.provider}' state provider, "
                "but no plugin provides it.\n"
            )
        )
        raise Exception("Missing storage provider plugin.")

    lock: Optional[LockInterface]
    if doLock:
        lock = get_lock(network)
    else:
        lock = None

    storage_class_options = storage_class.options(**network.storage.configuration)
    storage: StorageInterface = storage_class(storage_class_options)

    with TemporaryDirectory("nixops") as statedir:
        statefile = statedir + "/state.nixops"
        if lock is not None:
            lock.lock(description=description, exclusive=writable)
        try:
            storage.fetchToFile(statefile)
            if writable:
                state = nixops.statefile.StateFile(statefile, writable, lock=lock)
            else:
                # Non-mutating commands use the state file as their data
                # structure, therefore requiring mutation to work.
                # Changes *will* be lost, as tolerating racy writes will be
                # even harder to debug than consistently discarding changes.
                # TODO: Change the NixOps architecture to separate reading
                #       and writing cleanly, so we can request a read-only
                #       statefile here and 'guarantee' no loss of state changes.
                state = nixops.statefile.StateFile(statefile, True, lock=lock)
            try:
                storage.onOpen(state)

                yield state
            finally:
                state.close()
                if writable:
                    storage.uploadFromFile(statefile)
        finally:
            if lock is not None:
                lock.unlock()


def op_list_plugins(args: Namespace) -> None:
    pm = get_plugin_manager()

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
    args: Namespace, writable: bool, activityDescription: str
) -> Generator[List[nixops.deployment.Deployment], None, None]:
    with network_state(args, writable, description=activityDescription) as sf:
        if args.all:
            yield sf.get_all_deployments()
        else:
            yield [open_deployment(sf, args)]


def op_list_deployments(args: Namespace) -> None:
    with network_state(args, False, "nixops list") as sf:
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
            set_common_depl(depl, args)
            depl.evaluate()

            types: Set[str] = set()
            n_machines: int = 0

            for defn in (depl.definitions or {}).values():
                if not isinstance(defn, MachineDefinition):
                    continue
                n_machines += 1
                types.add(defn.get_type())

            tbl.add_row(
                [
                    depl.uuid,
                    depl.name or "(none)",
                    depl.description,
                    n_machines,
                    ", ".join(types),
                ]
            )
        print(tbl)


def open_deployment(
    sf: nixops.statefile.StateFile, args: Namespace
) -> nixops.deployment.Deployment:
    depl = sf.open_deployment(uuid=args.deployment)

    depl.extra_nix_path = sum(args.nix_path or [], [])
    for (n, v) in args.nix_options or []:
        depl.extra_nix_flags.extend(["--option", n, v])
    if args.max_jobs is not None:
        depl.extra_nix_flags.extend(["--max-jobs", str(args.max_jobs)])
    if args.cores is not None:
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


def set_name(depl: nixops.deployment.Deployment, name: Optional[str]) -> None:
    if not name:
        return
    if not re.match("^[a-zA-Z_\-][a-zA-Z0-9_\-\.]*$", name):  # noqa: W605
        raise Exception("invalid deployment name ‘{0}’".format(name))
    depl.name = name


def modify_deployment(args: Namespace, depl: nixops.deployment.Deployment) -> None:
    set_common_depl(depl, args)
    depl.nix_path = [nixops.util.abs_nix_path(x) for x in sum(args.nix_path or [], [])]


def op_create(args: Namespace) -> None:
    with network_state(args, True, "nixops create") as sf:
        depl = sf.create_deployment()
        sys.stderr.write("created deployment ‘{0}’\n".format(depl.uuid))
        modify_deployment(args, depl)

        # When deployment is created without state "name" does not exist
        name: str = args.deployment
        if "name" in args:
            name = args.name or args.deployment

        if name:
            set_name(depl, name)

        sys.stdout.write(depl.uuid + "\n")


def op_modify(args: Namespace) -> None:
    with deployment(args, True, "nixops modify") as depl:
        modify_deployment(args, depl)
        if args.name:
            set_name(depl, args.name)


def op_clone(args: Namespace) -> None:
    with deployment(args, True, "nixops clone") as depl:
        depl2 = depl.clone()
        sys.stderr.write("created deployment ‘{0}’\n".format(depl2.uuid))
        set_name(depl2, args.name)
        sys.stdout.write(depl2.uuid + "\n")


def op_delete(args: Namespace) -> None:
    with one_or_all(args, True, "nixops delete") as depls:
        for depl in depls:
            depl.delete(force=args.force or False)


def machine_to_key(depl: str, name: str, type: str) -> Tuple[str, str, List[object]]:
    xs = [int(x) if x.isdigit() else x for x in re.split("(\d+)", name)]  # noqa: W605
    return (depl, type, xs)


def op_info(args: Namespace) -> None:  # noqa: C901
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
        m: nixops.backends.GenericMachineState,
    ) -> str:
        if d and m.obsolete:
            return "Revived"
        if d is None and m.obsolete:
            return "Obsolete"
        if depl.configs_path != m.cur_configs_path:
            return "Outdated"

        return "Up-to-date"

    def do_eval(depl) -> None:
        set_common_depl(depl, args)

        if not args.no_eval:
            try:
                depl.evaluate()
            except NixEvalError:
                sys.stderr.write(
                    nixops.ansi.ansi_warn(
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
            r: Optional[nixops.resources.GenericResourceState] = depl.resources.get(
                name
            )
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
        with network_state(args, False, "nixops info") as sf:
            if not args.plain:
                tbl = create_table([("Deployment", "l")] + table_headers)
            for depl in sort_deployments(sf.get_all_deployments()):
                do_eval(depl)
                print_deployment(depl)
            if not args.plain:
                print(tbl)

    else:
        with deployment(args, False, "nixops info") as depl:
            do_eval(depl)

            if args.plain:
                print_deployment(depl)
            else:
                print("Network name:", depl.name or "(none)")
                print("Network UUID:", depl.uuid)
                print("Network description:", depl.description)

                print("Nix expression:", get_network_file(args).network)
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


def op_check(args: Namespace) -> None:  # noqa: C901
    def highlight(s: str) -> str:
        return nixops.ansi.ansi_highlight(s, outfile=sys.stdout)

    def warn(s: str) -> str:
        return nixops.ansi.ansi_warn(s, outfile=sys.stdout)

    def render_tristate(x: bool) -> str:
        if x is None:
            return "N/A"
        elif x:
            return nixops.ansi.ansi_success("Yes", outfile=sys.stdout)
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

    machines: List[nixops.backends.GenericMachineState] = []
    resources: List[nixops.resources.GenericResourceState] = []

    def check(depl: nixops.deployment.Deployment) -> None:
        for m in depl.active_resources.values():
            if not nixops.deployment.should_do(
                m, args.include or [], args.exclude or []
            ):
                continue
            if isinstance(m, nixops.backends.MachineState):
                machines.append(m)
            else:
                resources.append(m)

    # TODO: writable=False?
    # Historically, nixops check was allowed to write to the state file.
    # With remote state however, this requires an exclusive lock, which may
    # not be the best choice.
    with one_or_all(args, writable=True, activityDescription="nixops check") as depls:
        for depl in depls:
            check(depl)

        ResourceStatus = Tuple[
            str,
            Union[
                nixops.backends.GenericMachineState,
                nixops.resources.GenericResourceState,
            ],
            List[str],
            int,
        ]

        # Check all machines in parallel.
        def worker(m: nixops.backends.GenericMachineState) -> ResourceStatus:
            res = m.check()

            unit_lines = []
            if res.failed_units:
                unit_lines.append(
                    "\n".join(
                        [warn("{0} [failed]".format(x)) for x in res.failed_units]
                    )
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
                if res.load is not None
                else "",
                "\n".join(unit_lines),
                "\n".join([warn(x) for x in res.messages]),
            ]
            status = 0
            if res.exists is False:
                status |= 1
            if res.is_up is False:
                status |= 2
            if res.is_reachable is False:
                status |= 4
            if res.disks_ok is False:
                status |= 8
            if res.failed_units is not None and res.failed_units != []:
                status |= 16
            return (m.depl.name or m.depl.uuid, m, row, status)

        resources_tbl = create_table(
            ([("Deployment", "l")] if args.all else [])
            + [("Name", "l"), ("Exists", "l")]
        )

        def resource_worker(
            r: nixops.resources.GenericResourceState,
        ) -> Optional[ResourceStatus]:
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
        print(nixops.ansi.ansi_success("Machines state:"))
        print(tbl)

        for res in sorted(
            [res for res in resources_results if res is not None],
            key=lambda res: machine_to_key(res[0], res[1].name, res[1].get_type()),
        ):
            resources_tbl.add_row(res[2])
            status |= res[3]
        print(nixops.ansi.ansi_success("Non machines resources state:"))
        print(resources_tbl)

        sys.exit(status)


def print_backups(depl, backups) -> None:
    tbl = prettytable.PrettyTable(["Backup ID", "Status", "Info"])
    for k, v in sorted(backups.items(), reverse=True):
        tbl.add_row([k, v["status"], "\n".join(v["info"])])
    print(tbl)


def op_clean_backups(args: Namespace) -> None:
    if args.keep and args.keep_days:
        raise Exception(
            "Combining of --keep and --keep-days arguments are not possible, please use one."
        )
    if not (args.keep or args.keep_days):
        raise Exception("Please specify at least --keep or --keep-days arguments.")
    with deployment(args, True, "nixops clean-backups") as depl:
        depl.clean_backups(args.keep, args.keep_days, args.keep_physical)


def op_remove_backup(args: Namespace) -> None:
    with deployment(args, True, "nixops remove-backup") as depl:
        depl.remove_backup(args.backupid, args.keep_physical)


def op_backup(args: Namespace) -> None:
    with deployment(args, True, "nixops backup") as depl:

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


def op_backup_status(args: Namespace) -> None:
    with deployment(args, False, "nixops backup-status") as depl:
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


def op_restore(args: Namespace) -> None:
    with deployment(args, True, "nixops restore") as depl:
        depl.restore(
            include=args.include or [],
            exclude=args.exclude or [],
            backup_id=args.backup_id,
            devices=args.devices or [],
        )


def op_deploy(args: Namespace) -> None:
    with deployment(args, True, "nixops deploy") as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        if args.evaluate_only:
            raise Exception("--evaluate-only was removed as it's the same as --dry-run")
        depl.deploy(
            dry_run=args.dry_run,
            test=args.test,
            boot=args.boot,
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


def op_send_keys(args: Namespace) -> None:
    with deployment(args, False, "nixops send-keys") as depl:
        depl.send_keys(include=args.include or [], exclude=args.exclude or [])


def op_set_args(args: Namespace) -> None:
    with deployment(args, True, "nixops set-args") as depl:
        for [n, v] in args.args or []:
            depl.set_arg(n, v)
        for [n, v] in args.argstrs or []:
            depl.set_argstr(n, v)
        for [n] in args.unset or []:
            depl.unset_arg(n)


def op_destroy(args: Namespace) -> None:
    with one_or_all(args, True, "nixops destroy") as depls:
        for depl in depls:
            if args.confirm:
                depl.logger.set_autoresponse("y")
            depl.destroy_resources(
                include=args.include or [], exclude=args.exclude or [], wipe=args.wipe
            )


def op_reboot(args: Namespace) -> None:
    with deployment(args, True, "nixops reboot") as depl:
        depl.reboot_machines(
            include=args.include or [],
            exclude=args.exclude or [],
            wait=(not args.no_wait),
            rescue=args.rescue,
            hard=args.hard,
        )


def op_delete_resources(args: Namespace) -> None:
    with deployment(args, True, "nixops delete-resources") as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        depl.delete_resources(include=args.include or [], exclude=args.exclude or [])


def op_stop(args: Namespace) -> None:
    with deployment(args, True, "nixops stop") as depl:
        if args.confirm:
            depl.logger.set_autoresponse("y")
        depl.stop_machines(include=args.include or [], exclude=args.exclude or [])


def op_start(args: Namespace) -> None:
    with deployment(args, True, "nixops start") as depl:
        depl.start_machines(include=args.include or [], exclude=args.exclude or [])


def op_rename(args: Namespace) -> None:
    with deployment(args, True, "nixops rename") as depl:
        depl.rename(args.current_name, args.new_name)


def print_physical_backup_spec(
    depl: nixops.deployment.Deployment, backupid: str
) -> None:
    config = {}
    for m in depl.active_machines.values():
        config[m.name] = m.get_physical_backup_spec(backupid)
    sys.stdout.write(py2nix(config))


def op_show_arguments(cli_args: Namespace) -> None:
    with deployment(cli_args, False, "nixops show-arguments") as depl:
        tbl = create_table([("Name", "l"), ("Location", "l")])
        args = depl.get_arguments()
        for arg in sorted(args.keys()):
            files = sorted(args[arg])
            tbl.add_row([arg, "\n".join(files)])
        print(tbl)


def op_show_physical(args: Namespace) -> None:
    with deployment(args, False, "nixops show-physical") as depl:
        if args.backupid:
            print_physical_backup_spec(depl, args.backupid)
            return
        depl.evaluate()
        sys.stdout.write(depl.get_physical_spec())


def op_dump_nix_paths(args: Namespace) -> None:
    def get_nix_path(p: Optional[str]) -> Optional[str]:
        if p is None:
            return None
        p = os.path.realpath(os.path.abspath(p))
        # FIXME: hardcoded nix store
        nix_store = "/nix/store"
        if not p.startswith("{0}/".format(nix_store)):
            return None
        return "/".join(p.split("/")[: len(nix_store.split("/")) + 1])

    def strip_nix_path(p: str) -> str:
        parts: List[str] = p.split("=")
        if len(parts) == 1:
            return parts[0]
        else:
            return parts[1]

    def nix_paths(depl: nixops.deployment.Deployment) -> List[str]:
        set_common_depl(depl, args)
        candidates: Sequence[Optional[str]] = []
        candidates = (
            [depl.network_expr.network]
            + [strip_nix_path(p) for p in depl.nix_path]
            + [depl.configs_path]
        )
        candidates = [get_nix_path(p) for p in candidates]
        return [p for p in candidates if p is not None]

    paths: List[str] = []

    with one_or_all(args, False, "nixops dump-nix-paths") as depls:
        for depl in depls:
            paths.extend(nix_paths(depl))

    for p in paths:
        print(p)


def op_export(args: Namespace) -> None:
    res = {}

    with one_or_all(args, False, "nixops export") as depls:
        for depl in depls:
            res[depl.uuid] = depl.export()
    print(json.dumps(res, indent=2, sort_keys=True, cls=nixops.util.NixopsEncoder))


def op_unlock(args: Namespace) -> None:
    network = eval_network(get_network_file(args))
    lock = get_lock(network)
    lock.unlock()


def op_import(args: Namespace) -> None:
    with network_state(args, True, "nixops import") as sf:
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
                for m in depl.active_machines.values():
                    if nixops.deployment.is_machine(m) and hasattr(
                        m, "public_host_key"
                    ):
                        if m.public_ipv4:
                            nixops.known_hosts.add(m.public_ipv4, m.public_host_key)
                        if m.private_ipv4:
                            nixops.known_hosts.add(m.private_ipv4, m.public_host_key)


def parse_machine(
    name: str, depl: nixops.deployment.Deployment
) -> Tuple[str, str, nixops.backends.GenericMachineState]:
    username: Optional[str]
    machine_name: str
    if name.find("@") == -1:
        username = None
        machine_name = name
    else:
        username, machine_name = name.split("@", 1)

    # For nixops mount, split path element
    machine_name = machine_name.split(":")[0]

    m = depl.machines.get(machine_name)

    if not m:
        raise Exception("unknown machine ‘{0}’".format(machine_name))

    if not username and m.ssh_user:
        username = m.ssh_user

    if username is None:
        username = "root"

    return username, machine_name, m


def op_ssh(args: Namespace) -> None:
    with network_state(
        args, False, description="nixops ssh", doLock=not args.now
    ) as sf:
        depl = open_deployment(sf, args)
        set_common_depl(depl, args)

        (username, _, m) = parse_machine(args.machine, depl)
        flags, command = m.ssh.split_openssh_args(args.args)

        # unlock early, to avoid blocking mutable operations (deploy etc) while
        # an interactive session is active.
        if sf.lock is not None:
            sf.lock.unlock()
        sys.exit(
            m.ssh.run_command(
                command,
                flags=flags,
                check=False,
                logged=False,
                allow_ssh_args=True,
                user=username,
            )
        )


def op_ssh_for_each(args: Namespace) -> None:
    results: List[Optional[int]] = []
    with one_or_all(args, False, "nixops ssh-for-each") as depls:
        for depl in depls:

            def worker(m: nixops.backends.GenericMachineState) -> Optional[int]:
                if not nixops.deployment.should_do(
                    m, args.include or [], args.exclude or []
                ):
                    return None

                return m.ssh.run_command_get_status(
                    args.args, allow_ssh_args=True, check=False, user=m.ssh_user
                )

            results = results + nixops.parallel.run_tasks(
                nr_workers=len(depl.machines) if args.parallel else 1,
                tasks=iter(depl.active_machines.values()),
                worker_fun=worker,
            )

    sys.exit(max(results) if results != [] else 0)


def scp_loc(user: str, ssh_name: str, remote: str, loc: str) -> str:
    return "{0}@{1}:{2}".format(user, ssh_name, loc) if remote else loc


def op_scp(args: Namespace) -> None:
    if args.scp_from == args.scp_to:
        raise Exception("exactly one of ‘--from’ and ‘--to’ must be specified")
    with deployment(args, False, "nixops scp") as depl:
        (username, machine, m) = parse_machine(args.machine, depl)
        ssh_name = m.get_ssh_name()
        from_loc = scp_loc(username, ssh_name, args.scp_from, args.source)
        to_loc = scp_loc(username, ssh_name, args.scp_to, args.destination)
        print("{0} -> {1}".format(from_loc, to_loc), file=sys.stderr)
        flags = ["scp", "-r"] + m.get_ssh_flags() + [from_loc, to_loc]
        # Map ssh's ‘-p’ to scp's ‘-P’.
        flags = ["-P" if f == "-p" else f for f in flags]
        res = subprocess.call(flags)
        sys.exit(res)


def op_mount(args: Namespace) -> None:
    # TODO: Fixme
    with deployment(args, False, "nixops mount") as depl:
        (username, rest, m) = parse_machine(args.machine, depl)
        try:
            remote_path = args.machine.split(":")[1]
        except IndexError:
            remote_path = "/"

        ssh_name = m.get_ssh_name()

        ssh_flags = nixops.util.shlex_join(["ssh"] + m.get_ssh_flags())
        new_flags = ["-o" f"ssh_command={ssh_flags}"]

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


def op_show_option(args: Namespace) -> None:
    with deployment(args, False, "nixops show-option") as depl:
        if args.include_physical:
            depl.evaluate()
        json.dump(
            depl.evaluate_option_value(
                args.machine, args.option, include_physical=args.include_physical,
            ),
            sys.stdout,
            indent=2,
        )


@contextlib.contextmanager
def deployment_with_rollback(
    args: Namespace, activityDescription: str,
) -> Generator[nixops.deployment.Deployment, None, None]:
    with deployment(args, True, activityDescription) as depl:
        if not depl.rollback_enabled:
            raise Exception(
                "rollback is not enabled for this network; please set ‘network.enableRollback’ to ‘true’ and redeploy"
            )
        yield depl


def op_list_generations(args: Namespace) -> None:
    with deployment_with_rollback(args, "nixops list-generations") as depl:
        if (
            subprocess.call(["nix-env", "-p", depl.get_profile(), "--list-generations"])
            != 0
        ):
            raise Exception("nix-env --list-generations failed")


def op_delete_generation(args: Namespace) -> None:
    with deployment_with_rollback(args, "nixops delete-generation") as depl:
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


def op_rollback(args: Namespace) -> None:
    with deployment_with_rollback(args, "nixops rollback") as depl:
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


def op_show_console_output(args: Namespace) -> None:
    with deployment(args, False, "nixops show-console-output") as depl:
        m = depl.machines.get(args.machine)
        if not m:
            raise Exception("unknown machine ‘{0}’".format(args.machine))
        sys.stdout.write(m.get_console_output())


def op_edit(args: Namespace) -> None:
    with deployment(args, False, "nixops edit") as depl:
        editor = os.environ.get("EDITOR")
        if not editor:
            raise Exception("the $EDITOR environment variable is not set")
        os.system(
            "$EDITOR " + " ".join([pipes.quote(x) for x in depl.network_expr.network])
        )


def op_copy_closure(args: Namespace) -> None:
    with deployment(args, False, "nixops copy-closure") as depl:
        (username, machine, m) = parse_machine(args.machine, depl)
        m.copy_closure_to(args.storepath)


# Set up logging of all commands and output
def setup_logging(args: Namespace) -> None:
    if os.path.exists("/dev/log") and args.op not in [
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
        except Exception:
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
        "--network",
        dest="network_dir",
        metavar="FILE",
        default=None,
        help="path to a directory containing either nixops.nix or flake.nix",
    )
    subparser.add_argument(
        "--flake",
        "-f",
        dest="flake",
        metavar="FLAKE_URI",
        default=os.environ.get("NIXOPS_FLAKE", None),
        help="the flake uri.",
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


def add_common_deployment_options(subparser: ArgumentParser) -> None:
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


def error(msg: str) -> None:
    sys.stderr.write(nixops.ansi.ansi_warn("error: ") + msg + "\n")


def parser_plugin_hooks(parser: ArgumentParser, subparsers: _SubParsersAction) -> None:
    PluginManager.parser(parser, subparsers)
