# -*- coding: utf-8 -*-

# Automatic provisioning of Azure storages.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, StorageResourceState, normalize_location

from azure.mgmt.storage import StorageAccountCreateParameters, StorageAccountUpdateParameters, CustomDomain

from azure.storage.models import StorageServiceProperties

class AzureStorageDefinition(ResourceDefinition):
    """Definition of an Azure Storage"""

    @classmethod
    def get_type(cls):
        return "azure-storage"

    @classmethod
    def get_resource_type(cls):
        return "azureStorages"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.storage_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_option(xml, 'accountType', str, empty = False)
        self.copy_option(xml, 'activeKey', str, empty = False)
        if self.active_key not in ['primary', 'secondary']:
            raise Exception("Allowed activeKey values are: 'primary' and 'secondary'")
        self.copy_location(xml)
        self.copy_option(xml, 'customDomain', str)
        self.copy_tags(xml)

        self.blob_service_properties = self._parse_service_properties(
                                          xml.find("attrs/attr[@name='blobService']"))
        self.queue_service_properties = self._parse_service_properties(
                                          xml.find("attrs/attr[@name='queueService']"))
        self.table_service_properties = self._parse_service_properties(
                                          xml.find("attrs/attr[@name='tableService']"))
        #FIXME: add table service properties once the API is available

    def _parse_retention_policy(self, xml):
        enable = self.get_option_value(xml, 'enable', bool)
        return {
            'enable': enable,
            'days': self.get_option_value(xml, 'days', int) if enable else None,
        }

    def _parse_metrics(self, xml):
        enable = self.get_option_value(xml, 'enable', bool)
        return {
            'enable': enable,
            'include_apis': self.get_option_value(xml, 'includeAPIs', bool) if enable else None,
            'retention_policy': self._parse_retention_policy(
                                    xml.find("attrs/attr[@name='retentionPolicy']")),
        }

    def _parse_service_properties(self, xml):
        logging_xml = xml.find("attrs/attr[@name='logging']")
        return {
            'logging': {
                'delete': self.get_option_value(logging_xml, 'delete', bool),
                'read': self.get_option_value(logging_xml, 'read', bool),
                'write': self.get_option_value(logging_xml, 'write', bool),
                'retention_policy': self._parse_retention_policy(
                                        logging_xml.find("attrs/attr[@name='retentionPolicy']")),
            },
            'hour_metrics': self._parse_metrics(
                                xml.find("attrs/attr[@name='hourMetrics']")),
            'minute_metrics': self._parse_metrics(
                                  xml.find("attrs/attr[@name='minuteMetrics']")),
        }

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureStorageState(StorageResourceState):
    """State of an Azure Storage"""

    storage_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    account_type = attr_property("azure.accountType", None)
    custom_domain = attr_property("azure.customDomain", None)
    tags = attr_property("azure.tags", {}, 'json')

    blob_service_properties = attr_property("azure.blobServiceProperties", {}, 'json')
    queue_service_properties = attr_property("azure.queueServiceProperties", {}, 'json')
    table_service_properties = attr_property("azure.tableServiceProperties", {}, 'json')

    active_key = attr_property("azure.activeKey", None)
    primary_key = attr_property("azure.primaryKey", None)
    secondary_key = attr_property("azure.secondaryKey", None)

    @classmethod
    def get_type(cls):
        return "azure-storage"

    def show_type(self):
        s = super(AzureStorageState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.storage_name

    @property
    def full_name(self):
        return "Azure storage '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.smc().storage_accounts.get_properties(self.resource_group,self.resource_id).storage_account
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.smc().storage_accounts.delete(self.resource_group, self.resource_id)

    @property
    def access_key(self):
        return ((self.active_key == 'primary') and self.primary_key) or self.secondary_key


    # for StorageResourceState compatibility
    def get_key(self):
        return self.access_key

    def get_storage_name(self):
        return self.storage_name


    # blob/table/queue/file service properties handling
    def _set_retention_policy_from_dict(self, obj, props):
        obj.enabled = props.get('enable', False)
        obj.days = props.get('days', None) if obj.enabled else None

    def _set_metrics_properties_from_dict(self, obj, props):
        obj.enabled = props.get('enable', False)
        obj.include_apis = props.get('include_apis', None)
        self._set_retention_policy_from_dict(obj.retention_policy,
                                             props.get('retention_policy', {}))

    def _dict_to_storage_service_properties(self, props):
        result =  StorageServiceProperties()

        logging_props = props.get('logging', {})
        result.logging.delete = logging_props.get('delete', False)
        result.logging.read = logging_props.get('read', False)
        result.logging.write = logging_props.get('write', False)
        self._set_retention_policy_from_dict(result.logging.retention_policy,
                                             logging_props.get('retention_policy', {}))
        self._set_metrics_properties_from_dict(result.hour_metrics,
                                               props.get('hour_metrics', {}))
        self._set_metrics_properties_from_dict(result.minute_metrics,
                                               props.get('minute_metrics', {}))
        return result


    def _check_retention_policy(self, expected, actual, service_name):
        #workaround for broken RetentionPolicy.get_days
        _actual_days = actual.__dict__['days']
        actual_days = None if _actual_days is None else int(_actual_days)

        return {
            'enable': self.warn_if_changed(expected.get('enable', False),
                                           actual.enabled, 'retention policy enable',
                                           resource_name = service_name),
            'days': self.warn_if_changed(expected.get('days', None),
                                         actual_days, 'retention policy days',
                                         resource_name = service_name),
        }

    def _check_metrics_properties(self, expected, actual, service_name):
        # a workaround for broken API
        include_apis = (True if actual.include_apis == 'true' else 
                       (False if actual.include_apis == 'false' else
                        actual.include_apis))
        return {
            'enable': self.warn_if_changed(expected.get('enable', False),
                                           actual.enabled, 'metrics enable',
                                           resource_name = service_name),
            'include_apis': self.warn_if_changed(expected.get('include_apis', False),
                                                 include_apis, 'includeAPIs',
                                                 resource_name = service_name),
            'retention_policy': self._check_retention_policy(expected.get('retention_policy', {}),
                                                             actual.retention_policy,
                                                             "{0} metrics".format(service_name))
        }

    def _check_storage_service_properties(self, expected, actual, service_name):
        expected_logging = expected.get('logging', {})
        return {
            'logging': {
                'delete': self.warn_if_changed(expected_logging.get('delete', False),
                                               actual.logging.delete, 'delete',
                                               resource_name = service_name),
                'read': self.warn_if_changed(expected_logging.get('read', False),
                                             actual.logging.read, 'read',
                                             resource_name = service_name),
                'write': self.warn_if_changed(expected_logging.get('write', False),
                                              actual.logging.write, 'write',
                                              resource_name = service_name),
                'retention_policy': self._check_retention_policy(expected_logging.get('retention_policy', {}),
                                                                 actual.logging.retention_policy,
                                                                 "{0} logging".format(service_name)),
            },
            'hour_metrics': self._check_metrics_properties(expected.get('hour_metrics', {}),
                                                           actual.hour_metrics,
                                                           '{0} hour'.format(service_name)),
            'minute_metrics': self._check_metrics_properties(expected.get('minute_metrics', {}),
                                                             actual.minute_metrics,
                                                             '{0} minute'.format(service_name)),
        }


    defn_properties = [ 'location', 'account_type', 'tags', 'custom_domain' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.storage_name = defn.storage_name
        self.resource_group = defn.resource_group
        self.active_key = defn.active_key

        if check:
            storage = self.get_settled_resource()
            if not storage:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(storage)
                self.handle_changed_property('location', normalize_location(storage.location),
                                             can_fix = False)
                self.handle_changed_property('account_type', storage.account_type)
                self.handle_changed_property('tags', storage.tags)
                self.handle_changed_property('custom_domain', (storage.custom_domain and storage.custom_domain.name) or "")

                keys = self.smc().storage_accounts.list_keys(self.resource_group, self.storage_name).storage_account_keys
                self.handle_changed_property('primary_key', keys.key1)
                self.handle_changed_property('secondary_key', keys.key2)

                self.blob_service_properties = self._check_storage_service_properties(
                                                   self.blob_service_properties,
                                                   self.bs().get_blob_service_properties(),
                                                   'BLOB service')

                self.queue_service_properties = self._check_storage_service_properties(
                                                   self.queue_service_properties,
                                                   self.qs().get_queue_service_properties(),
                                                   'queue service')

                self.table_service_properties = self._check_storage_service_properties(
                                                   self.table_service_properties,
                                                   self.ts().get_table_service_properties(),
                                                   'table service')
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a storage that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self.smc().storage_accounts.create(defn.resource_group, defn.storage_name,
                                               StorageAccountCreateParameters(
                                                   account_type = defn.account_type,
                                                   location = defn.location,
                                                   tags = defn.tags))
            self.state = self.UP
            self.copy_properties(defn)
            self.custom_domain = ""
            # getting keys fails until the storage is fully provisioned
            self.log("waiting for the storage to settle; this may take several minutes...")
            self.get_settled_resource()
            keys = self.smc().storage_accounts.list_keys(self.resource_group, self.storage_name).storage_account_keys
            self.primary_key = keys.key1
            self.secondary_key = keys.key2

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            # as per Azure documentation, this API can only
            # change one property per call, so we call it 3 times
            if self.tags != defn.tags:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(tags = defn.tags))
                self.tags = defn.tags

            if self.account_type != defn.account_type:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(
                                                       account_type = defn.account_type))
                self.account_type = defn.account_type

            if self.custom_domain != defn.custom_domain:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(
                                                       custom_domain =
                                                           CustomDomain(name = defn.custom_domain)))
                self.custom_domain = defn.custom_domain

        if self.blob_service_properties != defn.blob_service_properties:
            self.log("updating BLOB service properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.bs().set_blob_service_properties(
                self._dict_to_storage_service_properties(defn.blob_service_properties))
            self.blob_service_properties = defn.blob_service_properties

        if self.queue_service_properties != defn.queue_service_properties:
            self.log("updating queue service properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.qs().set_queue_service_properties(
                self._dict_to_storage_service_properties(defn.queue_service_properties))
            self.queue_service_properties = defn.queue_service_properties

        if self.table_service_properties != defn.table_service_properties:
            self.log("updating table service properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.ts().set_table_service_properties(
                self._dict_to_storage_service_properties(defn.table_service_properties))
            self.table_service_properties = defn.table_service_properties


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}
