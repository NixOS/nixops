# -*- coding: utf-8 -*-

# Automatic provisioning of AWS Route53 RecordSets.

import os
import time
import botocore
import boto3
import nixops.util
import nixops.resources
import nixops.ec2_utils
#boto3.set_stream_logger(name='botocore')

class Route53RecordSetDefinition(nixops.resources.ResourceDefinition):
    """Definition of an Route53 RecordSet."""

    @classmethod
    def get_type(cls):
        return "aws-route53-recordset"

    @classmethod
    def get_resource_type(cls):
        return "route53RecordSets"

    def __init__(self, xml, config):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.access_key_id = config["accessKeyId"]

        self.zone_id = config["zoneId"]
        self.set_identifier = config["setIdentifier"]
        self.weight = config["weight"]

        self.zone_name = config["zoneName"]
        self.domain_name = config["domainName"]

        self.ttl = config["ttl"]
        self.routing_policy = config["routingPolicy"]
        self.record_type = config["recordType"]
        self.record_values = config["recordValues"]
        self.health_check_id = config["healthCheckId"]

    def show_type(self):
        return "{0}".format(self.get_type())


class Route53RecordSetState(nixops.resources.ResourceState):
    """State of a Route53 Recordset."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("route53.accessKeyId", None)

    zone_id = nixops.util.attr_property("route53.zoneId", None)
    set_identifier = nixops.util.attr_property("route53.setIdentifier", None)
    weight = nixops.util.attr_property("route53.weight", 0, int)

    zone_name = nixops.util.attr_property("route53.zoneName", None)
    domain_name = nixops.util.attr_property("route53.domainName", None)
    ttl = nixops.util.attr_property("route53.ttl", None, int)
    routing_policy = nixops.util.attr_property("route53.routingPolicy", None)
    record_type = nixops.util.attr_property("route53.recordType", None)
    record_values = nixops.util.attr_property("route53.recordValues", None, 'json')
    health_check_id = nixops.util.attr_property("route53.healthCheckId", None)

    @classmethod
    def get_type(cls):
        return "aws-route53-recordset"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._boto_session = None


    @property
    def resource_id(self):
        return self.domain_name

    def get_definition_prefix(self):
        return "resources.route53RecordSets."

    def boto_session(self):
        if self._boto_session is None:
            (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
            self._boto_session = boto3.session.Session(
                                               aws_access_key_id=access_key_id,
                                               aws_secret_access_key=secret_access_key)
        return self._boto_session

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        if not (self.access_key_id or os.environ['AWS_ACCESS_KEY_ID']):
             raise Exception("please set ‘accessKeyId’ or $AWS_ACCESS_KEY_ID")

        # Sanity checks for configuration
        if defn.domain_name is None:
            raise Exception("No domain name set for Route 53 RecordSet '{0}'".format(defn.name))

        if len(defn.domain_name) > 253:
            raise Exception("domain name ‘{0}’ is longer than 253 characters.".format(defn.domain_name))

        client = self.boto_session().client("route53")

        zone_name = defn.zone_name
        zone_id = defn.zone_id

        # Check if zone name || zone id set
        if defn.zone_name is None:
            # Now zoneId should be defined.
            if defn.zone_id is None:
                raise Exception("Neither zoneName nor zoneId is set for Route 53 Recordset '{0}'".format(defn.domain_name))
            else:
                if zone_id.startswith("res-"):
                    hs = self.depl.get_typed_resource(zone_id[4:], "aws-route53-hosted-zone")
                    if not hs.zone_id:
                        raise Exception("cannot create record set in not-yet created hosted zone: ‘{0}’". format(defn.domain_name))
                    zone_id = hs.zone_id

                # We have a zoneId, look up the zoneName
                hosted_zone = client.get_hosted_zone(Id = zone_id)
                zone_name = hosted_zone["HostedZone"]["Name"][:-1]
        else:
            if defn.zone_id is not None:
                raise Exception("Both zoneName and zoneId are set for Route 53 Recordset '{0}'".format(defn.domain_name))
            else:
                # We have the zoneName, find the zoneId
                response = self.route53_retry(lambda: client.list_hosted_zones_by_name(DNSName=defn.zone_name))
                zone_name = defn.zone_name if defn.zone_name.endswith('.') else (defn.zone_name + '.')
                zones = filter((lambda zone: zone["Name"] == zone_name), response["HostedZones"])
                if len(zones) == 0:
                    raise Exception("Can't find zone id")
                elif len(zones) > 1:
                    raise Exception("Found more than one hosted zone for {}, please remove one, or define the zone ID explicitly.".format(defn.zone_name))
                else:
                    zone_id = zones[0]["Id"]

        if self.routing_policy and self.routing_policy != defn.routing_policy:
            raise Exception("Cannot change record routing policy from '{}' to '{}'".format(self.routing_policy, defn.routing_policy))
        if self.domain_name and self.domain_name != defn.domain_name:
            raise Exception("Cannot change record domain name from '{}' to '{}'".format(self.domain_name, defn.domain_name))
        if self.record_type and self.record_type != defn.record_type:
            raise Exception("Cannot change record type from '{}' to '{}'".format(self.record_type, defn.record_type))
        if self.zone_id and self.zone_id != zone_id:
            raise Exception("Cannot change zone id from '{}' to '{}'.".format(self.zone_id, zone_id))
        if self.set_identifier and self.set_identifier != defn.set_identifier:
            raise Exception("Cannot change set identifier for a record from '{}' to '{}'.".format(self.set_identifier, defn.set_identifier))
        if not zone_name.endswith('.'):
            zone_name += '.'
        # zone name should be suffix of the dns name, if the zone name is set.
        if not defn.domain_name.endswith(zone_name):
            raise Exception("The domain name '{0}' does not end in the zone name '{1}'. You have to specify the FQDN for the zone name.".format(defn.domain_name, self.zone_name))

        def resolve_machine_ip(v):
            if v.startswith('res-'):
                m = self.depl.get_machine(v[4:])
                if not m.public_ipv4:
                    raise Exception("cannot create record set for a machine that has not yet been created")
                return m.public_ipv4
            else:
                return v

        defn.record_values = map(resolve_machine_ip , defn.record_values)

        changed = self.record_values != defn.record_values \
               or self.ttl != defn.ttl \
               or self.weight != defn.weight \
               or self.health_check_id != defn.health_check_id

        if not changed and not check:
            return

        self.log('creating/updating record set ({})'.format(self.to_string(defn)))

        # Don't care about the state for now. We'll just upsert!
        # TODO: Copy properties_changed function used in GCE/Azure's
        # check output of operation. It now just barfs an exception if something doesn't work properly
        change_result = self.route53_retry(lambda: client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch=self.make_batch('UPSERT', defn)
        ))

        with self.depl._state.db:
            self.state = self.UP
            self.zone_name = zone_name
            self.zone_id = zone_id
            self.domain_name = defn.domain_name
            self.record_type = defn.record_type
            self.routing_policy = defn.routing_policy
            self.record_values = defn.record_values
            self.ttl = defn.ttl
            self.set_identifier = defn.set_identifier
            self.weight = defn.weight
            self.health_check_id = defn.health_check_id

        return True

    def make_batch(self, action, obj):
        batch = {
            'Changes': [
                {
                    'Action': action,
                    'ResourceRecordSet': {
                        'Name': obj.domain_name,
                        'Type': obj.record_type,
                        'TTL': int(obj.ttl),
                        'ResourceRecords': map(lambda rv: { 'Value': rv }, obj.record_values)
                    }
                },
            ]
        }

        rs_batch = batch['Changes'][0]['ResourceRecordSet']

        if obj.set_identifier and obj.set_identifier != "":
            rs_batch.update({ 'SetIdentifier': obj.set_identifier })

        if obj.routing_policy == "multivalue":
            rs_batch.update({ 'MultiValueAnswer': True })

        if obj.routing_policy == "weighted":
            rs_batch.update({ 'Weight': int(obj.weight) })


        def resolve_health_check(v):
            if v.startswith('res-'):
                hc = self.depl.get_typed_resource(v[4:], "aws-route53-health-check")
                if not hc.health_check_id:
                    raise Exception("cannot refer to a health check resource that has not yet been created")
                return hc.health_check_id
            else:
                return v

        if obj.health_check_id and obj.health_check_id != "":
            rs_batch.update({ 'HealthCheckId': resolve_health_check(obj.health_check_id) })

        return batch

    def to_string(self, obj):
        res = "{}/{}".format(obj.record_type, obj.domain_name)
        if obj.set_identifier:
             res += "/{}".format(obj.set_identifier)
        return res

    def destroy(self, wipe=False):
        if self.state == self.UP and self.depl.logger.confirm("are you sure you want to destroy record: {}".format(self.to_string(self))):
            self.log('destroying record set ({})'.format(self.to_string(self)))
            client = self.boto_session().client("route53")

            # TODO: catch exception
            change_result = self.route53_retry(lambda: client.change_resource_record_sets(
                HostedZoneId=self.zone_id,
                ChangeBatch=self.make_batch('DELETE', self)))

            with self.depl._state.db:
                self.state = self.MISSING
            return True

    def route53_retry(self, f):
        return nixops.ec2_utils.retry(f, error_codes=[ 'Throttling', 'PriorRequestNotComplete' ], logger=self)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.route53_hosted_zone.Route53HostedZoneState) or
                isinstance(r, nixops.resources.route53_health_check.Route53HealthCheckState) or
                isinstance(r, nixops.backends.MachineState)}

