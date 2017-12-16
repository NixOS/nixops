# -*- coding: utf-8 -*-

# Automatic provisioning of AWS Route53 RecordSets.

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

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")


        def getOptionalXmlAttr(xml_doc, attrName):
            node = xml_doc.find("attrs/attr[@name='{0}']/string".format(attrName))
            if node is None:
                return None
            else:
                return node.get("value")

        self.zone_id = getOptionalXmlAttr(xml, "zoneId")

        self.zone_name = getOptionalXmlAttr(xml, "zoneName")
        self.domain_name = getOptionalXmlAttr(xml, "domainName")

        self.ttl = int(xml.find("attrs/attr[@name='ttl']/int").get("value"))
        self.record_type = xml.find("attrs/attr[@name='recordType']/string").get("value")
        self.record_value = xml.find("attrs/attr[@name='recordValue']/string").get("value")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.domain_name)


class Route53RecordSetState(nixops.resources.ResourceState):
    """State of a Route53 Recordset."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("route53.accessKeyId", None)

    zone_id = nixops.util.attr_property("route53.zoneId", None)
    zone_name = nixops.util.attr_property("route53.zoneName", None)
    domain_name = nixops.util.attr_property("route53.domainName", None)
    ttl = nixops.util.attr_property("route53.ttl", None)
    record_type = nixops.util.attr_property("route53.recordType", None)
    record_value = nixops.util.attr_property("route53.recordValue", None)

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
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

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
                # We have a zoneId, look up the zoneName
                hosted_zone = client.get_hosted_zone(Id = defn.zone_id)
                zone_name = hosted_zone["HostedZone"]["Name"]
                None
        else:
            if defn.zone_id is not None:
                raise Exception("Both zoneName and zoneId are set for Route 53 Recordset '{0}'".format(defn.domain_name))
            else:
                # We have the zoneName, find the zoneId
                response = client.list_hosted_zones_by_name(DNSName=defn.zone_name)
                zone = filter((lambda zone: zone["Name"] == defn.zone_name), response["HostedZones"])[0]
                if zone is None:
                    raise Exception("Can't find zone id")
                else:
                    zone_id = zone["Id"]

        # zone name should be suffix of the dns name, if the zone name is set.
        if not defn.domain_name.endswith(zone_name):
            raise Exception("The domain name '{0}' does not end in the zone name '{1}'. You have to specify the FQDN for the zone name.".format(defn.domain_name, self.zone_name))


        # Don't care about the state for now. We'll just upsert!
        # TODO: Copy properties_changed function used in GCE/Azure's
        # check output of operation. It now just barfs an exception if something doesn't work properly
        change_result = client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': defn.domain_name,
                            'Type': defn.record_type,
                            'TTL': defn.ttl,
                            'ResourceRecords': [
                                {
                                    'Value': defn.record_value
                                },
                            ]
                        }
                    },
                ]
            }
        )

        with self.depl._db:
            self.state = self.UP
            self.zone_name = zone_name
            self.zone_id = zone_id
            self.domain_name = defn.domain_name
            self.record_type = defn.record_type
            self.record_value = defn.record_value
            self.ttl = defn.ttl

        return True

    def destroy(self, wipe=False):
        if self.state == self.UP:
            client = self.boto_session().client("route53")
            # TODO: catch exception
            change_result = client.change_resource_record_sets(
                HostedZoneId=self.zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'DELETE',
                            'ResourceRecordSet': {
                                'Name': self.domain_name,
                                'Type': self.record_type,
                                'TTL': int(self.ttl),
                                'ResourceRecords': [
                                    {
                                        'Value': self.record_value
                                    },
                                ]
                            }
                        },
                    ]
                }
            )
            with self.depl._db:
                self.state = self.MISSING

