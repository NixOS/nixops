# -*- coding: utf-8 -*-

import nixops.deployment
import os
import os.path
import sqlite3
import sys
import threading


class Connection(sqlite3.Connection):
    def __init__(self, db_file, **kwargs):
        db_exists = os.path.exists(db_file)
        if not db_exists:
            os.fdopen(os.open(db_file, os.O_WRONLY | os.O_CREAT, 0o600), "w").close()
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
        sqlite3.Connection.__enter__(self)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if exception_type != None:
            self.must_rollback = True
        self.nesting = self.nesting - 1
        assert self.nesting >= 0
        if self.nesting == 0:
            if self.must_rollback:
                try:
                    self.rollback()
                except sqlite3.ProgrammingError:
                    pass
            else:
                sqlite3.Connection.__exit__(
                    self, exception_type, exception_value, exception_traceback
                )
        self.lock.release()


def get_default_state_file():
    home = os.environ.get("HOME", "") + "/.nixops"
    if not os.path.exists(home):
        old_home = os.environ.get("HOME", "") + "/.charon"
        if os.path.exists(old_home):
            sys.stderr.write("renaming ‘{0}’ to ‘{1}’...\n".format(old_home, home))
            os.rename(old_home, home)
            if os.path.exists(home + "/deployments.charon"):
                os.rename(home + "/deployments.charon", home + "/deployments.nixops")
        else:
            os.makedirs(home, 0o700)
    return os.environ.get(
        "NIXOPS_STATE", os.environ.get("CHARON_STATE", home + "/deployments.nixops")
    )


class StateFile(object):
    """NixOps state file."""

    current_schema = 3

    def __init__(self, db_file):
        self.db_file = db_file

        if os.path.splitext(db_file)[1] not in [".nixops", ".charon"]:
            raise Exception(
                "state file ‘{0}’ should have extension ‘.nixops’".format(db_file)
            )
        db = sqlite3.connect(
            db_file,
            timeout=60,
            check_same_thread=False,
            factory=Connection,
            isolation_level=None,
        )  # FIXME
        db.db_file = db_file

        db.execute("pragma journal_mode = wal")
        db.execute("pragma foreign_keys = 1")

        # FIXME: this is not actually transactional, because pysqlite (not
        # sqlite) does an implicit commit before "create table".
        with db:
            c = db.cursor()

            # Get the schema version.
            version = 0  # new database
            if self._table_exists(c, "SchemaVersion"):
                c.execute("select version from SchemaVersion")
                version = c.fetchone()[0]
            elif self._table_exists(c, "Deployments"):
                version = 1

            if version == self.current_schema:
                pass
            elif version == 0:
                self._create_schema(c)
            elif version < self.current_schema:
                if version <= 1:
                    self._upgrade_1_to_2(c)
                if version <= 2:
                    self._upgrade_2_to_3(c)
                c.execute(
                    "update SchemaVersion set version = ?", (self.current_schema,)
                )
            else:
                raise Exception(
                    "this NixOps version is too old to deal with schema version {0}".format(
                        version
                    )
                )

        self._db = db

    def close(self):
        self._db.close()

    def query_deployments(self):
        """Return the UUIDs of all deployments in the database."""
        c = self._db.cursor()
        c.execute("select uuid from Deployments")
        res = c.fetchall()
        return [x[0] for x in res]

    def get_all_deployments(self):
        """Return Deployment objects for every deployment in the database."""
        uuids = self.query_deployments()
        res = []
        for uuid in uuids:
            try:
                res.append(self.open_deployment(uuid=uuid))
            except nixops.deployment.UnknownBackend as e:
                sys.stderr.write(
                    "skipping deployment ‘{0}’: {1}\n".format(uuid, str(e))
                )
        return res

    def _find_deployment(self, uuid=None):
        c = self._db.cursor()
        if not uuid:
            c.execute("select uuid from Deployments")
        else:
            c.execute(
                "select uuid from Deployments d where uuid = ? or exists (select 1 from DeploymentAttrs where deployment = d.uuid and name = 'name' and value = ?)",
                (uuid, uuid),
            )
        res = c.fetchall()
        if len(res) == 0:
            if uuid:
                # try the prefix match
                c.execute(
                    "select uuid from Deployments where uuid glob ?", (uuid + "*",)
                )
                res = c.fetchall()
                if len(res) == 0:
                    return None
            else:
                return None
        if len(res) > 1:
            if uuid:
                raise Exception(
                    "state file contains multiple deployments with the same name, so you should specify one using its UUID"
                )
            else:
                raise Exception(
                    "state file contains multiple deployments, so you should specify which one to use using ‘-d’, or set the environment variable NIXOPS_DEPLOYMENT"
                )
        return nixops.deployment.Deployment(self, res[0][0], sys.stderr)

    def open_deployment(self, uuid=None):
        """Open an existing deployment."""
        deployment = self._find_deployment(uuid=uuid)
        if deployment:
            return deployment
        raise Exception(
            "could not find specified deployment in state file ‘{0}’".format(
                self.db_file
            )
        )

    def create_deployment(self, uuid=None):
        """Create a new deployment."""
        if not uuid:
            import uuid

            uuid = str(uuid.uuid1())
        with self._db:
            self._db.execute("insert into Deployments(uuid) values (?)", (uuid,))
        return nixops.deployment.Deployment(self, uuid, sys.stderr)

    def _table_exists(self, c, table):
        c.execute(
            "select 1 from sqlite_master where name = ? and type='table'", (table,)
        )
        return c.fetchone() != None

    def _create_schemaversion(self, c):
        c.execute(
            """create table if not exists SchemaVersion(
                 version integer not null
               );"""
        )

        c.execute(
            "insert into SchemaVersion(version) values (?)", (self.current_schema,)
        )

    def _create_schema(self, c):
        self._create_schemaversion(c)

        c.execute(
            """create table if not exists Deployments(
                 uuid text primary key
               );"""
        )

        c.execute(
            """create table if not exists DeploymentAttrs(
                 deployment text not null,
                 name text not null,
                 value text not null,
                 primary key(deployment, name),
                 foreign key(deployment) references Deployments(uuid) on delete cascade
               );"""
        )

        c.execute(
            """create table if not exists Resources(
                 id integer primary key autoincrement,
                 deployment text not null,
                 name text not null,
                 type text not null,
                 foreign key(deployment) references Deployments(uuid) on delete cascade
               );"""
        )

        c.execute(
            """create table if not exists ResourceAttrs(
                 machine integer not null,
                 name text not null,
                 value text not null,
                 primary key(machine, name),
                 foreign key(machine) references Resources(id) on delete cascade
               );"""
        )

    def _upgrade_1_to_2(self, c):
        sys.stderr.write("updating database schema from version 1 to 2...\n")
        self._create_schemaversion(c)

    def _upgrade_2_to_3(self, c):
        sys.stderr.write("updating database schema from version 2 to 3...\n")
        c.execute("alter table Machines rename to Resources")
        c.execute("alter table MachineAttrs rename to ResourceAttrs")
