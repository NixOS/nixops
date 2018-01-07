#! /usr/bin/env nix-shell
#! nix-shell -i python -p pythonPackages.boto3 -I channel:nixos-unstable

import json
import os
import boto3
import sys

session = boto3.session.Session()
client = session.client('route53')

domain = sys.argv[1]
if not domain.endswith('.'):
    domain += '.'

zone_id = client.list_hosted_zones_by_name(DNSName=domain)['HostedZones'][0]['Id']
records = client.list_resource_record_sets(HostedZoneId=zone_id)['ResourceRecordSets']

by_hostname = {}
for record in records:
    name = record['Name']
    if not name in by_hostname:
        by_hostname[name] = []
    by_hostname[name].append(record)

count = {k : len(v) for (k, v) in by_hostname.items()}

def print_record(record):
    if record['Type'] in ( 'NS', 'SOA') :
        return

    if len(record['ResourceRecords']) > 1:
        raise Exception('Too many values')

    res = record['Name'][:-(len(domain)+1)]
    if count[record['Name']] > 1:
        res = res + "-" +  record['SetIdentifier']
    print('    "{0}" = {{ resources, ... }}: {{'.format(res))
    print('      zoneId = resources.route53HostedZones.hs;')
    print('      inherit accessKeyId;')
    print('      domainName = "{}";'.format(record['Name']))
    if 'SetIdentifier' in record:
        print('      setIdentifier = "{}";'.format(record['SetIdentifier']))
    print('      ttl = {};'.format(record['TTL']))
    print('      recordValues = [ "{}" ];'.format(record['ResourceRecords'][0]['Value']))
    print('      recordType = "{}";'.format(record['Type']))
    print('    };')


print('''
{{ accessKeyId ? "nixos-tests" }}:
{{
  resources.route53HostedZones.hs =
    {{ name = "{}";
      comment = "Hosted zone for nixos.org";
      inherit accessKeyId;
    }};
'''.format(domain))
print('  resources.route53RecordSets = {')
map(print_record, records)
print('  };')
print('}')
