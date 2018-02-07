# -*- coding: utf-8 -*-

import nixops.deployment
import os
import os.path
import urlparse
import sys
import threading
import fcntl

import sqlalchemy

def _subclasses(cls):
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]


def get_default_state_file():
    home = os.environ.get("HOME", "") + "/.nixops"
    if not os.path.exists(home):
        old_home = os.environ.get("HOME", "") + "/.charon"
        if os.path.exists(old_home):
            sys.stderr.write("renaming {!r} to {!r}...\n".format(old_home, home))
            os.rename(old_home, home)
            if os.path.exists(home + "/deployments.charon"):
                os.rename(home + "/deployments.charon", home + "/deployments.nixops")
        else:
            os.makedirs(home, 0700)
    return os.environ.get("NIXOPS_STATE", os.environ.get("CHARON_STATE", home + "/deployments.nixops"))


class SQLConnection(object):
    """NixOps db uri."""

    current_schema = 3

    def __init__(self, db_uri):
        url = urlparse.urlparse(db_uri)
        self.db_uri = db_uri

        db_engine = sqlalchemy.create_engine(db_uri)
        db = db_engine.connect()
        if url.scheme == "sqlite":
            db.execute("pragma journal_mode = wal;")
            db.execute("pragma foreign_keys;")
        version = 0 # new database

        if db_engine.dialect.has_table(db, 'SchemaVersion'):
            version = db.execute("select version from SchemaVersion").scalar()
        elif db_engine.dialect.has_table(db, 'Deployments'):
            version = 1

        if version == self.current_schema:
            pass
        elif version == 0:
            self._create_schema(db)
        elif version < self.current_schema:
            if version <= 1:
                self._upgrade_1_to_2(db)
            if version <= 2:
                self._upgrade_2_to_3(db)
            db.execute("update SchemaVersion set version = {!r}".format(self.current_schema))
        else:
            raise Exception("this NixOps version is too old to deal with schema version {!r}".format(version))

        self.db = db

    def close(self):
        self.db.close()

    ###############################################################################################
    ## Deployment

    def query_deployments(self):
        """Return the UUIDs of all deployments in the database."""
        rows = self.db.execute("select uuid from Deployments")
        return [x[0] for x in rows]


    def get_all_deployments(self):
        """Return Deployment objects for every deployment in the database."""
        uuids = self.query_deployments()
        res = []
        for uuid in uuids:
            try:
                res.append(self.open_deployment(uuid=uuid))
            except nixops.deployment.UnknownBackend as e:
                sys.stderr.write("skipping deployment '{}': {!r}\n".format(uuid, str(e)))

        return res


    def _find_deployment(self, uuid=None):
        if not uuid:
            rows = self.db.execute("select count(uuid), uuid from Deployments")
        else:
            rows = self.db.execute("select count(uuid), uuid from Deployments d where uuid = '{}' or exists (select 1 from DeploymentAttrs where deployment = d.uuid and name = 'name' and value = '{}')".format(uuid, uuid))
        row_count = 0
        deployment = None
        for row in rows:
            row_count = row[0]
            deployment = row[1]
            break

        if row_count == 0:
            if uuid:
                # try the prefix match
                rows = self.db.execute("select count(uuid), uuid from Deployments where uuid glob '{}'".format(uuid + '*'))
                for row in rows:
                    row_count = row[0]
                    deployment = row[1]
                    break

                if row_count == 0:
                    return None
            else:
                return None

        if row_count > 1:
            if uuid:
                raise Exception("state file contains multiple deployments with the same name, so you should specify one using its UUID")
            else:
                raise Exception("state file contains multiple deployments, so you should specify which one to use using ‘-d’, or set the environment variable NIXOPS_DEPLOYMENT")
        return nixops.deployment.Deployment(self, deployment, sys.stderr)


    def open_deployment(self, uuid=None):
        """Open an existing deployment."""
        deployment = self._find_deployment(uuid=uuid)

        if deployment: return deployment
        raise Exception("could not find specified deployment in state file {!r}".format(self.db_uri))


    def create_deployment(self, uuid=None):
        """Create a new deployment."""
        if not uuid:
            import uuid
            uuid = str(uuid.uuid1())
        self.db.execute("insert into Deployments(uuid) values ('{}')".format(uuid))
        return nixops.deployment.Deployment(self, uuid, sys.stderr)


    def _delete_deployment(self, deployment_uuid):
        """NOTE: This is UNSAFE, it's guarded in nixops/deployment.py. Do not call this function except from there!"""
        self.db.execute("delete from Deployments where uuid = '{}'".format(deployment_uuid))


    def clone_deployment(self, deployment_uuid):
        new = self.create_deployment()
        self.db.execute("insert into DeploymentAttrs (deployment, name, value) " +
                        "select '{}', name, value from DeploymentAttrs where deployment = '{}'"
                        .format(new.uuid, deployment_uuid)
        )
        new.configs_path = None
        return new


    def get_resources_for(self, deployment):
        """Get all the resources for a certain deployment"""
        resources = {}

        rows = self.db.execute("select id, name, type from Resources where deployment = '{}'".format(deployment.uuid))
        for (id, name, type) in rows:
            r = self._create_state(deployment, type, name, id)
            resources[name] = r
        return resources


    def set_deployment_attrs(self, deployment_uuid, attrs):
        """Update deployment attributes in the state."""
        for name, value in attrs.iteritems():
            if value == None:
                self.db.execute("delete from DeploymentAttrs where deployment = '{}' and name = '{}'"
                                .format(deployment_uuid, name)
                )
            else:
                self.db.execute("insert or replace into DeploymentAttrs(deployment, name, value) values ('{}', '{}', {!r})"
                                .format(deployment_uuid, name, value)
                )


    def del_deployment_attr(self, deployment_uuid, attr_name):
        self.db.execute("delete from DeploymentAttrs where deployment = '{}' and name = {!r}"
                        .format(deployment_uuid, attr_name)
        )


    def get_deployment_attr(self, deployment_uuid, name):
        """Get a deployment attribute from the state."""
        rows = self.db.execute("select value from DeploymentAttrs where deployment = '{}' and name = {!r}"
                               .format(deployment_uuid, name))
        for row in rows:
            return row[0]
        return nixops.util.undefined


    def get_all_deployment_attrs(self, deployment_uuid):
        rows = self.db.execute("select name, value from DeploymentAttrs where deployment = '{}'"
                               .format(deployment_uuid))
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

    ###############################################################################################
    ## Resources

    def create_resource(self, deployment, name, type):
        count = self.db.execute("select count(id) from Resources where deployment = '{}' and name = {!r}"
                               .format(deployment.uuid, name)).scalar()

        if count != 0:
            raise Exception("resource already exists in database!")

        result = self.db.execute("insert into Resources(deployment, name, type) values ('{}', {!r}, {!r})"
                               .format(deployment.uuid, name, type))

        id = result.lastrowid
        r = self._create_state(deployment, type, name, id)
        return r


    def delete_resource(self, deployment_uuid, res_id):
        self.db.execute("delete from Resources where deployment = '{}' and id = {!r}"
                        .format(deployment_uuid, res_id))


    def _rename_resource(self, deployment_uuid, resource_id, new_name):
        """NOTE: Invariants are checked in nixops/deployment.py#rename"""
        self.db.execute("update Resources set name = '{}' where deployment = '{}' and id = {!r}"
                        .format(new_name, deployment_uuid, resource_id))


    def set_resource_attrs(self, _deployment_uuid, resource_id, attrs):
        for name, value in attrs.iteritems():
            if value == None:
                self.db.execute("delete from ResourceAttrs where machine = '{}' and name = '{}'"
                                .format(resource_id, name))
            else:
                self.db.execute("insert or replace into ResourceAttrs(machine, name, value) values ('{}', '{}', {!r})"
                                .format(resource_id, name, value))


    def del_resource_attr(self, _deployment_uuid, resource_id, name):
        self.db.execute("delete from ResourceAttrs where machine = {!r} and name = {!r}"
                        .format(resource_id, name))


    def get_resource_attr(self, _deployment_uuid, resource_id, name):
        """Get a machine attribute from the state file."""
        rows = self.db.execute("select value from ResourceAttrs where machine = {!r} and name = {!r}"
                               .format(resource_id, name))
        if rows is not None:
            return row[0][0]
        return nixops.util.undefined


    def get_all_resource_attrs(self, deployment_uuid, resource_id):
        rows = self.db.execute("select name, value from ResourceAttrs where machine = {!r}"
                               .format(resource_id))
        res = {row[0]: row[1] for row in rows}
        return res


    ### STATE
    def _create_state(self, depl, type, name, id):
        """Create a resource state object of the desired type."""

        for cls in _subclasses(nixops.resources.ResourceState):
            if type == cls.get_type():
                return cls(depl, name, id)

        raise nixops.deployment.UnknownBackend("unknown resource type ‘{!r}’"
                                               .format(type))


    def _create_schemaversion(self, c):
        c.execute(
            '''create table if not exists SchemaVersion(
                 version integer not null
               );''')

        c.execute("insert into SchemaVersion(version) values ({!r})"
                  .format(self.current_schema))

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
