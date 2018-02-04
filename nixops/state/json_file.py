# -*- coding: utf-8 -*-

import nixops.deployment
import os
import os.path
import sys
import threading
import fcntl
import re
import json
import copy

from uuid import uuid1 as gen_uuid

def _subclasses(cls):
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]

class TransactionalJsonFile:
    """
        Transactional access to a JSON file, with support
        of nested transactions.

        This is made possible by keeping track of the transaction nest level.
        If a transaction is started, the current JSON file is flocked() and read into memory.
        All modifications to the document are kept in memory, until the last nested context is
        exited again.

        Then, the in memory dict written to a temporary file, which is moved in place of
        the original file to prevent partial writes.
    """

    # Implementation notes:
    # if self.nesting > 0, then no write will propagate.
    def __init__(self, db_file):

        lock_file_path = re.sub("\.json$", ".lock", db_file)
        self._lock_file = open(lock_file_path, "w")
        fcntl.fcntl(self._lock_file, fcntl.F_SETFD, fcntl.FD_CLOEXEC) # to not keep the lock in child processes

        self._db_file = db_file
        self.nesting = 0
        self.lock = threading.RLock()

        ## Make sure that a JSON database file is in place.
        with self:
            pass

    def read(self):
        if self.nesting == 0:
            with open(self._db_file,"r") as f:
                return json.load(f)
        else:
            assert self.nesting > 0
            return self._current_state

    # Implement Python's context management protocol so that "with db"
    # automatically commits or rolls back.
    def __enter__(self):
        self.lock.acquire()
        if self.nesting == 0:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX)
            self._ensure_db_exists()
            self.must_rollback = False
            json = self.read()
            self._backup_state = copy.deepcopy(json)
            self._current_state = copy.deepcopy(json)
        self.nesting = self.nesting + 1

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if exception_type != None: self.must_rollback = True
        self.nesting = self.nesting - 1
        assert self.nesting >= 0
        if self.nesting == 0:
            if self.must_rollback:
                self._rollback()
            else:
                self._commit()
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        self.lock.release()

    def _rollback(self):
        self._backup_state  = None
        self._current_state = None
        pass

    def set(self, state):
        self._current_state = state

    def _commit(self):
        assert self.nesting == 0

        # TODO: write to temp file, then mv
        with open(self._db_file, "w") as f:
          json.dump(self._current_state, f,indent=2)

        self._backup_state  = None
        self._current_state = None

    def _ensure_db_exists(self):
        db_exists = os.path.exists(self._db_file)
        if not db_exists:
            initial_db = {
              "schemaVersion": 0,
              "deployments": {}
            }

            with open(self._db_file, "w", 0o600) as f:
                json.dump(initial_db, f)
                f.close()

    def schema_version(self):
        version = self.read()["schemaVersion"]
        if version is None:
            raise "illegal datafile" #TODO: proper exception
        else:
            return version

class JsonFile(object):
    """NixOps state file."""

    def __init__(self, json_file):
        self.file_path = json_file

        if os.path.splitext(json_file)[1] not in ['.json']:
            raise Exception("state file ‘{0}’ should have extension ‘.json’".format(json_file))

        self.db = TransactionalJsonFile(json_file)

        # Check that we're not using a to new DB schema version.
        with self.db:
            version = self.db.schema_version()
            if version  > 0:
               raise Exception("this NixOps version is too old to deal with JSON schema version {0}".format(version))

    ###############################################################################################
    ## Deployment

    def query_deployments(self):
        """Return the UUIDs of all deployments in the database."""

        return self.db.read()["deployments"].keys()

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
        all_deployments = self.db.read()["deployments"]
        found = []
        if not uuid:
            found = all_deployments
        if not found:
            found = filter(lambda(id): id == uuid, all_deployments)
        if not found:
            found = filter(lambda(id): all_deployments[id]["attributes"].get("name") == uuid, all_deployments)

        if not found:
            found = filter(lambda(id): id.startswith(uuid), all_deployments)

        if not found:
            return None

        if len(found) > 1:
            if uuid:
                raise Exception("state file contains multiple deployments with the same name, so you should specify one using its UUID")
            else:
                raise Exception("state file contains multiple deployments, so you should specify which one to use using ‘-d’, or set the environment variable NIXOPS_DEPLOYMENT")
        return nixops.deployment.Deployment(self, found[0], sys.stderr)

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
            state = self.db.read()
            state["deployments"][uuid] = { "attributes": {}, "resources": {} }
            self.db.set(state)
        return nixops.deployment.Deployment(self, uuid, sys.stderr)

    def _delete_deployment(self, deployment_uuid):
        """NOTE: This is UNSAFE, it's guarded in nixops/deployment.py. Do not call this function except from there!"""
        self.__db.execute("delete from Deployments where uuid = ?", (deployment_uuid,))
        with self.db:
            state = self.db.read()
            state["deployments"].pop(deployment_uuid, None)
            self.db.set(state)

    def clone_deployment(self, deployment_uuid):
        with self.db:
            if not uuid:
                import uuid
                new_uuid = str(uuid.uuid1())
            state = self.db.read()

            cloned_attributes = copy.deepcopy(state["deployments"][deployment_uuid]["attributes"])
            state["deployments"][new_uuid] = {
                "attributes": cloned_attributes,
                "resources": {}
            }

            self.db.set(state)

        return self._find_deployment(new_uuid)

    def get_resources_for(self, deployment):
        """Get all the resources for a certain deployment"""
        resources = {}
        with self.db:
            state = self.db.read()
            state_resources = state["deployments"][deployment.uuid]["resources"]
            for res_id, res in state_resources.items():
                r = self._create_state(deployment, res["type"], res["name"], res_id)
                resources[res["name"]] = r
            self.db.set(state)
        return resources

    def set_deployment_attrs(self, deployment_uuid, attrs):
        """Update deployment attributes in the state."""
        with self.db:
            state = self.db.read()
            for n, v in attrs.iteritems():
                if v == None:
                    state["deployments"][deployment_uuid]["attributes"].pop(n,None)
                else:
                    state["deployments"][deployment_uuid]["attributes"][n] = v
            self.db.set(state)

    def del_deployment_attr(self, deployment_uuid, attr_name):
        with self.db:
            state = self.db.read()
            state["deployments"][deployment_uuid]["attributes"].pop(attr_name,None)
            self.db.set(state)

    def get_deployment_attr(self, deployment_uuid, name):
        """Get a deployment attribute from the state."""
        with self.db:
            state = self.db.read()
            result = state["deployments"][deployment_uuid]["attributes"].get(name)
            if result:
                return result
            else:
                return nixops.util.undefined

    def get_all_deployment_attrs(self, deployment_uuid):
        with self.db:
            state = self.db.read()
            return copy.deepcopy(state["deployments"][deployment]["attributes"])

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
        with self.db:
            state = self.db.read()
            if name in state["deployments"][deployment.uuid]["resources"]:
                raise Exception("resource already exists in database!")
            id = str(gen_uuid())
            state["deployments"][deployment.uuid]["resources"][id] = {
                    "name": name,
                    "type" : type,
                    "attributes" : {}
            }
            self.db.set(state)
            r = self._create_state(deployment, type, name, id)
            return r

    def delete_resource(self, deployment_uuid, res_id):
        with self.db:
            state = self.db.read()
            state["deployments"][deployment_uuid]["resources"].pop(res_id)
            self.db.set(state)

    def _rename_resource(self, deployment_uuid, resource_id, new_name):
        """NOTE: Invariants are checked in nixops/deployment.py#rename"""
        with self.db:
            state = self.db.read()
            state["deployments"][deployment_uuid]["resources"][resource_id]["name"] = new_name
            self.db.set(state)

    def set_resource_attrs(self, deployment_uuid, resource_id, attrs):
        with self.db:
            state = self.db.read()
            resource_attrs = state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"]
            for n, v in attrs.iteritems():
                if v == None:
                    resource_attrs.pop(n, None)
                else:
                    resource_attrs[n] = v
            state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"] = resource_attrs
            self.db.set(state)

    def del_resource_attr(self, deployment_uuid, resource_id, name):
        with self.db:
            state = self.db.read()
            resource_attrs = state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"]
            resource_attrs.pop(name, None)
            state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"] = resource_attrs
            self.db.set(state)

    def get_resource_attr(self, deployment_uuid, resource_id, name):
        """Get a machine attribute from the state file."""
        with self.db:
            state = self.db.read()
            resource_attrs = state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"]
            res = resource_attrs.get(name)
            if res != None: return res
            return nixops.util.undefined

    def get_all_resource_attrs(self, deployment_uuid, resource_id):
        with self.db:
            state = self.db.read()
            resource_attrs = state["deployments"][deployment_uuid]["resources"][resource_id]["attributes"]
            return copy.deepcopy(resource_attrs)

    ### STATE
    def _create_state(self, depl, type, name, id):
        """Create a resource state object of the desired type."""

        for cls in _subclasses(nixops.resources.ResourceState):
            if type == cls.get_type():
                return cls(depl, name, id)

        raise nixops.deployment.UnknownBackend("unknown resource type ‘{0}’".format(type))
