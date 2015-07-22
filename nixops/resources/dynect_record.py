# -*- coding: utf-8 -*-

import re
import nixops.util
import threading
import traceback
import os

from nixops.resources import ResourceDefinition
from nixops.resources import ResourceState
from dyn.tm.session import DynectSession
from dyn.tm.zones import Zone
from dyn.tm.records import ARecord
from dyn.tm.errors import DynectGetError


class DynectRecordDefination(ResourceDefinition):
    """TODO: Documentation"""
    supported_records = ['aRecord']

    @classmethod
    def get_type(cls):
        return "dynect-record"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)
        defination = self._get_value(xml)
        records = filter(lambda x: x is not None,
                         map(lambda x: x if x in defination and defination[x] != None else None,
                             DynectRecordDefination.supported_records))
        if not len(records) == 1:
            raise Exception(
                "None or more than one records are present {0}".format(records))
        self.record_type = records[0]
        try:
            self.record_defn = self.parse_record(self.record_type, defination)
        except KeyError as e:
            raise Exception(
                "{0} is missing in the nix expression".format(
                    e.args))

    def parse_record(self, record_type, defi):
        record = {
            "ttl": defi["ttl"],
            "fqdn": defi["fqdn"],
            "zone": defi["zone"]
        }
        if (record_type == "aRecord"):
            record["address"] = defi["aRecord"]["address"]
        else:
            raise Exception("Unsupported type {0}".format(self.record_type))
        return record

    # TODO: Move this code into the base class
    def _get_value(self, attr):
        value = None
        _type = attr.tag
        if _type == "list":
            value = []
            for x in attr:
                value.append(self._get_value(x))
        elif _type == "attrs":
            value = {}
            for x in attr:
                value[x.attrib['name']] = self._get_value(x)
        elif _type == "attr":
            if len(attr) > 1:
                raise Exception("More than 1 child elements")
            value = self._get_value(attr[0])
        elif _type == "string":
            value = attr.get("value")
        elif _type == "int":
            value = int(attr.get("value"))
        elif _type == "bool":
            value = bool(attr.get("value"))
        elif _type == "null":
            value = None
        else:
            raise Exception("Unknown {0} type".format(_type))
        return value

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.record_type)


class DynectRecordState(ResourceState):

    nix_name = "dynectRecords"
    record_type = nixops.util.attr_property("dynect.record_type", None)
    record = nixops.util.attr_property("dynect.record", {}, 'json')
    dyn_record_id = nixops.util.attr_property("dynect.dyn_record_id", None)
    rlock = threading.RLock()

    @classmethod
    def get_type(cls):
        return "dynect-record"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        """A short description of the type of resource this is"""
        return "{0} [{1}]".format(self.get_type(), self.record_type)

    @property
    def resource_id(self):
        return self.name

    def create(self, defn, check, allow_reboot, allow_recreate):
        # Ignore the check flag
        self.logger.log("DynectDNS resource state is {0}".format(self.state))
        record_type = defn.record_type
        self.name = defn.name
        record_defn = defn.record_defn
        if self.state == self.UNKNOWN:
            self.logger.log("Resource state is Unknown. Creating..")
            create = self._get_def(record_type, "create")
            record = create(record_type, record_defn)
        else:
            get = self._get_def(record_type, "get")
            record = get(
                self.record,
                self.dyn_record_id) if self.dyn_record_id is not None else None
            if record is None:
                self.logger.log("Resource not found on Dynect. Creating..")
                create = self._get_def(record_type, "create")
                record = create(record_type, record_defn)
            elif self._changes(self.record, self.record_type, record_defn, record_type):
                self.logger.log(
                    "Resource defination has been change. Updating..")
                update = self._get_def(record_type, "update")
                update(record, record_defn)
            else:
                self.logger.log("Resource is up to date")

        self.dyn_record_id = record.record_id
        self.record_type = record_type
        self.record = record_defn
        self.state = self.UP

    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.logger.log("Destroying..")
            get = self._get_def(self.record_type, "get")
            record = get(self.record, self.dyn_record_id)

            def delete_record(record): record.delete()
            self._make_changes(self.record['zone'], delete_record, record)
        return True

    def _changes(self, record, record_type, record_defn, record_defn_type):
        changes = False
        if record_type != record_defn_type:
            raise Exception(
                "Can't change the record type from {0} to {1}".format(
                    record_type, record_defn_type))
        if record != record_defn:
            if record['fqdn'] != record_defn['fqdn']:
                raise Exception("Can't change fqdn of the record")
            elif self.record['zone'] != record_defn['zone']:
                raise Exception("Can't change fqdn of the record")
            else:
                changes = True
        return changes

    def _make_changes(self, zone_name, change_def, *change_params):
        self._build_session()
        val = change_def(*change_params)
        zone = Zone(zone_name)
        zone.publish()
        return val

    def _build_session(self):
        def get_env_var(var):
            value = os.environ.get(var)
            if value is None:
                raise Exception("Env var {0} is not set".format(var))
            return value

        user_name = get_env_var('DYN_USER_NAME')
        customer_name = get_env_var('DYN_CUSTOMER_NAME')
        password = get_env_var('DYN_PASSWORD')
        # So ghetto, but race causes a NullPointer error
        with DynectRecordState.rlock:
            DynectSession(customer_name, user_name, password)

    # TODO: Instead have a class hierachy
    # DynectDyn api has side effects in constructor which makes it hard
    # to use
    def _get_def(self, record_type, op):
        if record_type == "aRecord":
            if op == "create":
                return self._create_arecord
            elif op == "get":
                return self._get_arecord
            elif op == "update":
                return self._update_arecord
            else:
                raise Exception("Unsupported {0} for aRecord".format(op))
        else:
            raise Exception("Unsupported type {0}".format(record_type))

    def _create_arecord(self, record_type, record_defn):
        zone_name = record_defn['zone']
        fqdn = record_defn['fqdn']
        ttl = record_defn['ttl']
        address = record_defn['address']
        params = {'address': address, 'ttl': ttl}

        def create_record(
            zone_name,
            fqdn,
            params): return ARecord(
            zone_name,
            fqdn,
            **params)
        return self._make_changes(
            zone_name, create_record, zone_name, fqdn, params)

    def _update_arecord(self, dyn_record, record_defn):
        zone_name = record_defn['zone']

        def update_record(dyn_record, record_defn):
            dyn_record.address = record_defn['address']
            dyn_record.ttl = record_defn['ttl']
        return self._make_changes(
            zone_name, update_record, dyn_record, record_defn)

    def _get_arecord(self, record, record_id):
        self.logger.log("Fetching record {0}".format(record_id))
        self._build_session()
        fqdn = record['fqdn']
        zone = record['zone']
        try:
            record = ARecord(zone, fqdn, record_id=record_id)
        except DynectGetError as e:
            # Hope that it is RecordNotFound (aka 404)
            self.logger.warn(
                traceback.format_exc()) if nixops.deployment.debug else None
            return None
        return record
