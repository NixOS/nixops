# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Networks.

import os
import libcloud.common.google
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

from nixops.util import attr_property
import nixops.resources


class GCENetworkDefinition(nixops.resources.ResourceDefinition):
    """Definition of a GCE Network"""

    @classmethod
    def get_type(cls):
        return "gce-network"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

        self.network_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.addressRange = xml.find("attrs/attr[@name='addressRange']/string").get("value")

        # FIXME: factor this out
        self.project = xml.find("attrs/attr[@name='project']/string").get("value")
        self.service_account = xml.find("attrs/attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = xml.find("attrs/attr[@name='accessKey']/string").get("value")


        def parse_allowed(x):
          if x.find("list") is not None:
            return( [v.get("value") for v in x.findall("list/string")] +
                    [str(v.get("value")) for v in x.findall("list/int")] )
          else: return None

        def parse_fw(x):
          result =  {
            "sourceRanges": [sr.get("value") for sr in x.findall("attrs/attr[@name='sourceRanges']/list/string")],
            "sourceTags": [st.get("value") for st in x.findall("attrs/attr[@name='sourceTags']/list/string")],
            "allowed": {a.get("name"): parse_allowed(a) for a in x.findall("attrs/attr[@name='allowed']/attrs/attr")}
          }
          if len(result['allowed']) == 0:
              raise Exception("Firewall rule ‘{0}‘ in network ‘{1}‘ must provide at least one protocol/port specification".
                              format(x.get("name"), self.network_name) )
          return result

        self.firewall = {fw.get("name"): parse_fw(fw) for fw in xml.findall("attrs/attr[@name='firewall']/attrs/attr")}

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.addressRange)


class GCENetworkState(nixops.resources.ResourceState):
    """State of a GCE Network"""

    addressRange = attr_property("gce.addressRange", None)
    network_name = attr_property("gce.network_name", None)

    firewall = attr_property("gce.firewall", {}, 'json')

    project = attr_property("gce.project", None)
    service_account = attr_property("gce.serviceAccount", None)
    access_key_path = attr_property("gce.accessKey", None)


    @classmethod
    def get_type(cls):
        return "gce-network"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def show_type(self):
        s = super(GCENetworkState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.addressRange)
        return s


    @property
    def resource_id(self):
        return self.network_name


    def connect(self):
        if self._conn: return self._conn

        service_account = self.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘resources.gceNetworks.$NAME.serviceAccount’ or $GCE_SERVICE_ACCOUNT")

        access_key_path = self.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘resources.gceNetworks.$NAME.accessKey’ or $ACCESS_KEY_PATH")

        project = self.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘resources.gceNetworks.$NAME.project’ or $GCE_PROJECT")

        self._conn = get_driver(Provider.GCE)(service_account, access_key_path, project = project)
        return self._conn

    def network(self):
        return self.connect().ex_get_network(self.network_name)

    def update_firewall(self, k, v):
        x = self.firewall
        if v == None:
            x.pop(k, None)
        else:
            x[k] = v
        self.firewall = x

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                raise Exception("cannot change the project of a deployed GCE Network ‘{0}’".format(self.network_name))
            if self.addressRange != defn.addressRange:
                raise Exception("cannot change the address range of a deployed GCE Network ‘{0}’".format(self.network_name))

        if check:
            try:
                network = self.connect().ex_get_network(defn.network_name)
                if self.state == self.UP:
                    if network.cidr != self.addressRange:
                        raise Exception("address range of a deployed GCE Network ‘{0}’ has unexpectedly changed to {1}".
                                        format(self.network_name, network.cidr))
                else:
                    self.warn("GCE Network ‘{0}’ exists, but isn't supposed to. Probably, this is the result "
                              "of a botched creation attempt and can be fixed by deletion."
                              .format(defn.network_name))
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing network ‘{0}’?".format(defn.network_name)):
                        self.log_start("destroying...")
                        network.destroy()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")
            except libcloud.common.google.ResourceNotFoundError:
                if self.state == self.UP:
                    self.warn("GCE Network ‘{0}’ is supposed to exist, but is missing. Recreating...".format(defn.network_name))
                    self.state = self.MISSING

        if self.state != self.UP:
            self.project = defn.project
            self.service_account = defn.service_account
            self.access_key_path = defn.access_key_path

            self.log_start("Creating GCE Network ‘{0}’...".format(defn.network_name))
            try:
                address = self.connect().ex_create_network(defn.network_name, defn.addressRange)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a network that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")

            self.state = self.UP
            self.addressRange = defn.addressRange
            self.network_name = defn.network_name

        # handle firewall rules
        def trans_allowed(attrs):
          return [ dict( [( "IPProtocol", proto )] + ([("ports", ports )] if ports is not None else []) )
                   for proto, ports in attrs.iteritems() ]

        def normalize_source_tags(tags):
            return( sorted(tags) if tags else [] )

        def normalize_source_ranges(ranges):
          if ranges == ["0.0.0.0/0"]:
              return []
          else:
              return( sorted(ranges) if ranges else [] )

        if check:
            firewalls = [ f for f in self.connect().ex_list_firewalls() if f.network.name == defn.network_name ]

            # delete stray rules and mark changed ones for update
            for fw in firewalls:
                k = next( (k for (k,v) in self.firewall.iteritems() if fw.name == "%s-%s"%(self.network_name, k)), None)
                if k:
                    rule = self.firewall[k]
                    if( (rule == {}) or
                          (normalize_source_ranges(fw.source_ranges) != normalize_source_ranges(rule['sourceRanges'])) or
                          (normalize_source_tags(fw.source_tags) != normalize_source_tags(rule['sourceTags'])) or
                          (fw.allowed != trans_allowed(rule['allowed'])) ):
                        self.warn("firewall rule ‘{0}‘ has changed unexpectedly...".format(fw.name))
                        self.update_firewall(k, {}) # mark for update
                else:
                    self.warn("deleting firewall rule ‘{0}‘ which isn't supposed to exist...".format(fw.name))
                    fw.destroy()

            # find missing firewall rules
            for k, v in self.firewall.iteritems():
                if not any(fw.name == "%s-%s"%(self.network_name, k) for fw in firewalls):
                    self.warn("firewall rule ‘{0}‘ has disappeared...".format(k))
                    self.update_firewall(k, None)

        # add new and update changed
        for k, v in defn.firewall.iteritems():
            if k in self.firewall:
                if v == self.firewall[k]: continue
                self.log_start("updating firewall rule ‘{0}‘...".format(k))
                try:
                    firewall = self.connect().ex_get_firewall("%s-%s"%(self.network_name, k))
                    firewall.allowed = trans_allowed(v['allowed'])
                    firewall.source_ranges = v['sourceRanges'] or ['0.0.0.0/0'] # match firewall creation behavior
                    firewall.source_tags = v['sourceTags']
                    firewall.update();
                except libcloud.common.google.ResourceNotFoundError:
                    raise Exception("Tried updating a firewall rule that doesn't exist. Please run ‘deploy --check’ to fix this.")

            else:
                self.log_start("creating firewall rule ‘{0}‘...".format(k))
                try:
                    self.connect().ex_create_firewall( "%s-%s"%(self.network_name, k), trans_allowed(v['allowed']),
                                                      network= self.network_name,
                                                      source_ranges = v['sourceRanges'],
                                                      source_tags = v['sourceTags']);
                except libcloud.common.google.ResourceExistsError:
                    raise Exception("Tried creating a firewall rule that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end('done.')
            self.update_firewall(k, v)

        # delete unneeded
        for k, v in self.firewall.iteritems():
            if k in defn.firewall: continue
            self.log_start("deleting firewall rule ‘{0}‘...".format(k))
            try:
                fw_n = "%s-%s"%(self.network_name, k);
                self.connect().ex_get_firewall(fw_n).destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy GCE Firewall ‘{0}’ which didn't exist".format(fw_n))
            self.log_end('done.')
            self.update_firewall(k, None)


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                network = self.network()
                if not self.depl.logger.confirm("are you sure you want to destroy GCE Network ‘{0}’?".format(self.network_name)):
                    return False

                for k,v in self.firewall.iteritems():
                    fw_n = "%s-%s"%(self.network_name, k);
                    self.log("destroying GCE Firewall ‘{0}’...".format(fw_n))
                    try:
                        self.connect().ex_get_firewall(fw_n).destroy()
                    except libcloud.common.google.ResourceNotFoundError:
                        self.warn("tried to destroy GCE Firewall ‘{0}’ which didn't exist".format(fw_n))
                    self.update_firewall(k, None)

                self.log("destroying GCE Network ‘{0}’...".format(self.network_name))
                network.destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy GCE Network ‘{0}’ which didn't exist".format(self.network_name))

        return True
