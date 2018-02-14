# -*- coding: utf-8 -*-


import nixops.deployment
import os
import os.path
import urlparse
import sys
import threading
import fcntl
import sqlite3


def _subclasses(cls):
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]


class Connection(sqlite3.Connection):

    def __init__(self, db_file, **kwargs):
        db_exists = os.path.exists(db_file)
        if not db_exists:
            os.fdopen(os.open(db_file, os.O_WRONLY | os.O_CREAT, 0o600), 'w').close()

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
                sqlite3.Connection.__exit__(self, exception_type, exception_value, exception_traceback)
        self.lock.release()


class SQLiteConnection(object):
    """NixOps state file."""

    current_schema = 3

    def __init__(self, db_file):
        url = urlparse.urlparse(db_file)
        self.db_file = url.netloc + url.path

        if os.path.splitext(db_file)[1] not in ['.nixops', '.charon']:
            raise Exception("state file ‘{0}’ should have extension ‘.nixops’".format(db_file))
        db = sqlite3.connect(self.db_file, timeout=60, check_same_thread=False, factory=Connection, isolation_level=None) # FIXME
        db.db_file = db_file

        db.execute("pragma journal_mode = wal")
        db.execute("pragma foreign_keys = 1")

        # FIXME: this is not actually transactional, because pysqlite (not
        # sqlite) does an implicit commit before "create table".
        with db:
            c = db.cursor()

            # Get the schema version.
            version = 0 # new database
            if self._table_exists(c, 'SchemaVersion'):
                c.execute("select version from SchemaVersion")
                version = c.fetchone()[0]
            elif self._table_exists(c, 'Deployments'):
                version = 1

            if version == self.current_schema:
                pass
            elif version == 0:
                self._create_schema(c)
            elif version < self.current_schema:
                if version <= 1: self._upgrade_1_to_2(c)
                if version <= 2: self._upgrade_2_to_3(c)
                c.execute("update SchemaVersion set version = ?", (self.current_schema,))
            else:
                raise Exception("this NixOps version is too old to deal with schema version {0}".format(version))

        self.db = db

    def close(self):
        self.db.close()

    def query_deployments(self):
        """Return the UUIDs of all deployments in the database."""
        c = self.db.cursor()
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
                sys.stderr.write("skipping deployment ‘{0}’: {1}\n".format(uuid, str(e)))
        return res

    def _find_deployment(self, uuid=None):
        c = self.db.cursor()
        if not uuid:
            c.execute("select uuid from Deployments")
        else:
            c.execute("select uuid from Deployments d where uuid = ? or exists (select 1 from DeploymentAttrs where deployment = d.uuid and name = 'name' and value = ?)", (uuid, uuid))
        res = c.fetchall()
        if len(res) == 0:
            if uuid:
                # try the prefix match
                c.execute("select uuid from Deployments where uuid glob ?", (uuid + '*', ))
                res = c.fetchall()
                if len(res) == 0:
                    return None
            else:
                return None
        if len(res) > 1:
            if uuid:
                raise Exception("state file contains multiple deployments with the same name, so you should specify one using its UUID")
            else:
                raise Exception("state file contains multiple deployments, so you should specify which one to use using ‘-d’, or set the environment variable NIXOPS_DEPLOYMENT")
        return nixops.deployment.Deployment(self, res[0][0], sys.stderr)

    def open_deployment(self, uuid=None):
        """Open an existing deployment."""
        deployment = self._find_deployment(uuid=uuid)
        if deployment: return deployment
        raise Exception("could not find specified deployment in state file ‘{0}’".format(self.db_file))

    def create_deployment(self, uuid=None):
        """Create a new deployment."""
        if not uuid:
            import uuid
            uuid = str(uuid.uuid1())
        with self.db:
            self.db.execute("insert into Deployments(uuid) values (?)", (uuid,))
        return nixops.deployment.Deployment(self, uuid, sys.stderr)

    def _table_exists(self, c, table):
        c.execute("select 1 from sqlite_master where name = ? and type='table'", (table,));
        return c.fetchone() != None

    def _delete_deployment(self, deployment_uuid):
        """NOTE: This is UNSAFE, it's guarded in nixops/deployment.py. Do not call this function except from there!"""
        with self.db:
            self.db.execute("delete from Deployments where uuid = '{}'".format(deployment_uuid))

    def clone_deployment(self, deployment_uuid):
        with self.db:
            new = self.create_deployment()
            self.db.execute("insert into DeploymentAttrs (deployment, name, value) " +
                             "select '{}', name, value from DeploymentAttrs where deployment = '{}'"
                             .format(new.uuid, deployment_uuid)
            )
            new.configs_path = None
            return new


    def _create_schemaversion(self, c):
        c.execute(
            '''create table if not exists SchemaVersion(
                 version integer not null
               );''')

        c.execute("insert into SchemaVersion(version) values (?)", (self.current_schema,))

    def _create_schema(self, c):
        self._create_schemaversion(c)

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

    def _upgrade_1_to_2(self, c):
        sys.stderr.write("updating database schema from version 1 to 2...\n")
        self._create_schemaversion(c)

    def _upgrade_2_to_3(self, c):
        sys.stderr.write("updating database schema from version 2 to 3...\n")
        c.execute("alter table Machines rename to Resources")
        c.execute("alter table MachineAttrs rename to ResourceAttrs")

#     ###############################################################################################
#     ## Deployment
    def get_resources_for(self, deployment):
        """Get all the resources for a certain deployment"""
        with self.db:
            resources = {}

            rows = self.db.execute("select id, name, type from Resources where deployment = '{}'".format(deployment.uuid)).fetchall()
            for (id, name, type) in rows:
                r = self._create_state(deployment, type, name, id)
                resources[name] = r
        return resources


    def set_deployment_attrs(self, deployment_uuid, attrs):
        """Update deployment attributes in the state."""
        with self.db:
            for name, value in attrs.iteritems():
                if value == None:
                    self.db.execute("delete from DeploymentAttrs where deployment = '{}' and name = '{}'"
                                    .format(deployment_uuid, name)
                    )
                else:
                    if self.get_deployment_attr(deployment_uuid, name) == nixops.util.undefined:
                        self.db.execute("insert into DeploymentAttrs(deployment, name, value) values ('{}', '{}', {!r})"
                                        .format(deployment_uuid, name, value)
                        )
                    else:
                        self.db.execute("update DeploymentAttrs set value={!r} where deployment='{}' and name='{}'"
                                        .format(value, deployment_uuid, name)
                        )


    def del_deployment_attr(self, deployment_uuid, attr_name):
        with self.db:
            self.db.execute("delete from DeploymentAttrs where deployment = '{}' and name = {!r}"
                            .format(deployment_uuid, attr_name)
            )


    def get_deployment_attr(self, deployment_uuid, name):
        """Get a deployment attribute from the state."""
        with self.db:
            rows = self.db.execute("select value from DeploymentAttrs where deployment = '{}' and name = {!r}"
                                   .format(deployment_uuid, name)).fetchall()
            for row in rows:
                return row[0]
            return nixops.util.undefined


    def get_all_deployment_attrs(self, deployment_uuid):
        with self.db:
            rows = self.db.execute("select name, value from DeploymentAttrs where deployment = '{}'"
                                   .format(deployment_uuid)).fetchall()
            res = {row[0]: row[1] for row in rows}
            return res


    def get_deployment_lock(self, deployment):
        lock_dir = os.environ.get("HOME", "") + "/.nixops/locks"
        if not os.path.exists(lock_dir): os.makedirs(lock_dir, 0700)
        lock_file_path = lock_dir + "/" + deployment.uuid
        class DeploymentLock(object):
            def __init__(self, logger, path):
                self._lock_file_path = path
                self._logger = logger
                self._lock_file = None
            def __enter__(self):
                self._lock_file = open(self._lock_file_path, "w")
                fcntl.fcntl(self._lock_file, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
                try:
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    self._logger.log(
                        "waiting for exclusive deployment lock..."
                    )
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX)
            def __exit__(self, exception_type, exception_value, exception_traceback):
                if self._lock_file:
                    self._lock_file.close()
        return DeploymentLock(deployment.logger, lock_file_path)

#     ###############################################################################################
#     ## Resources

    def create_resource(self, deployment, name, type):
        count = self.db.execute("select count(id) from Resources where deployment = '{}' and name = {!r}"
                                 .format(deployment.uuid, name)).fetchone()[0]

        if count != 0:
            raise Exception("resource already exists in database!")

        result = self.db.execute("insert into Resources(deployment, name, type) values ('{}', {!r}, {!r})"
                                  .format(deployment.uuid, name, type))

        id = result.lastrowid
        r = self._create_state(deployment, type, name, id)
        return r


    def delete_resource(self, deployment_uuid, res_id):
        with self.db:
            self.db.execute("delete from Resources where deployment = '{}' and id = {!r}"
                             .format(deployment_uuid, res_id))


    def _rename_resource(self, deployment_uuid, resource_id, new_name):
        """NOTE: Invariants are checked in nixops/deployment.py#rename"""
        with self.db:
            self.db.execute("update Resources set name = '{}' where deployment = '{}' and id = {!r}"
                             .format(new_name, deployment_uuid, resource_id))


    def set_resource_attrs(self, _deployment_uuid, resource_id, attrs):
        with self.db:
            for name, value in attrs.iteritems():
                if value == None:
                    self.db.execute("delete from ResourceAttrs where machine = '{}' and name = '{}'"
                                      .format(resource_id, name))
                else:
                    if self.get_resource_attr(_deployment_uuid, resource_id, name) == nixops.util.undefined:
                        self.db.execute("insert into ResourceAttrs(machine, name, value) values ('{}', '{}', '{}')"
                                         .format(resource_id, name, value)
                        )
                    else:
                        self.db.execute("update ResourceAttrs set value={!r} where machine='{}' and name='{}'"
                                         .format(value, resource_id, name)
                        )


    def del_resource_attr(self, _deployment_uuid, resource_id, name):
        with self.db:
            self.db.execute("delete from ResourceAttrs where machine = {!r} and name = {!r}"
                             .format(resource_id, name))


    def get_resource_attr(self, _deployment_uuid, resource_id, name):
        with self.db:
            """Get a machine attribute from the state file."""
            rows = self.db.execute("select value from ResourceAttrs where machine = '{}' and name = '{}'"
                                    .format(resource_id, name)).fetchall()
            for row in rows:
                return row[0]
            return nixops.util.undefined


    def get_all_resource_attrs(self, deployment_uuid, resource_id):
        with self.db:
            rows = self.db.execute("select name, value from ResourceAttrs where machine = {!r}"
                                    .format(resource_id)).fetchall()
            res = {row[0]: row[1] for row in rows}
            return res


#     ### STATE

    def _create_state(self, depl, type, name, id):
        """Create a resource state object  of the desired type."""

        for cls in _subclasses(nixops.resources.ResourceState):
            if type == cls.get_type():
                return cls(depl, name, id)

        raise nixops.deployment.UnknownBackend("unknown resource type ‘{!r}’"
                                               .format(type))
