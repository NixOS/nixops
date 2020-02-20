#! /usr/bin/env nix-shell
#! nix-shell -i python -p pythonPackages.boto3 -I channel:nixos-unstable

import json
import os
import boto3
import sys

session = boto3.session.Session()
client = session.client("route53")

domain = sys.argv[1]
if not domain.endswith("."):
    domain += "."

zone_id = client.list_hosted_zones_by_name(DNSName=domain)["HostedZones"][0]["Id"]
records = client.list_resource_record_sets(HostedZoneId=zone_id)["ResourceRecordSets"]

by_hostname = {}
for record in records:
    name = record["Name"]
    if not name in by_hostname:
        by_hostname[name] = []
    by_hostname[name].append(record)

count = {
    k: len([x for x in v if x["Type"] == "A"]) for (k, v) in list(by_hostname.items())
}


def print_record(record):
    if record["Type"] in ("NS", "SOA"):
        return

    res = record["Name"][: -(len(domain) + 1)]
    mv = False
    if count[record["Name"]] > 1:
        mv = True
        res = res + "-" + record["SetIdentifier"]
    if res == "":
        res = record["Type"] + "-record"

    print(('    "{0}" = {{ resources, ... }}: {{'.format(res)))
    print("      zoneId = resources.route53HostedZones.hs;")
    print("      inherit accessKeyId;")
    print(('      routingPolicy = "{}";'.format("multivalue" if mv else "simple")))
    print(('      domainName = "{}";'.format(record["Name"])))
    if "SetIdentifier" in record:
        print(('      setIdentifier = "{}";'.format(record["SetIdentifier"])))
    if "TTL" in record:
        print(("      ttl = {};".format(record["TTL"])))

    if "ResourceRecords" in record:
        print("      recordValues = [")
        for v in record["ResourceRecords"]:
            print(('        "{}"'.format(v["Value"])))
        print("      ];")

    if "AliasTarget" in record:
        print(('      aliasDNSName = "{}";'.format(record["AliasTarget"]["DNSName"])))
        print(
            (
                "      aliasEvaluateTargetHealth = {};".format(
                    record["AliasTarget"]["EvaluateTargetHealth"]
                )
            )
        )
        print(
            (
                '      aliasHostedZoneId = "{}";'.format(
                    record["AliasTarget"]["HostedZoneId"]
                )
            )
        )

    print(('      recordType = "{}";'.format(record["Type"])))
    print("    };")


print(
    (
        """
{{ accessKeyId ? "nixos-tests" }}:
{{
  resources.route53HostedZones.hs =
    {{ name = "{}";
      comment = "Hosted zone for nixos.org";
      inherit accessKeyId;
    }};
""".format(
            domain
        )
    )
)
print("  resources.route53RecordSets = {")
list(map(print_record, records))
print("  };")
print("}")
