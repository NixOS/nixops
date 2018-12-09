#! /usr/bin/env python2
import json
from pprint import pprint

# curl -O https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json
with open('index.json') as f:
    data = json.load(f)

instanceTypes = {}
for p in data['products'].keys():
    product = data['products'][p]['attributes']
    if 'operatingSystem' in product and product['operatingSystem'] in ('NA', 'Linux') \
       and 'tenancy' in product and product['tenancy'] == 'Shared' \
       and product['location'] == 'US East (N. Virginia)':
           ebsOptimized = 'ebsOptimized' in product
           instanceType = product['instanceType']
           cores = product['vcpu']
           memory = int(float(product['memory'].replace(',','').split(' ')[0]) * 1024)
           supportsNVMe = 'NVMe' in product['storage'] 
           if instanceType in instanceTypes and not ebsOptimized:
               continue
           instanceTypes[product['instanceType']] = '  "'+instanceType+'" = { cores = '+cores+'; memory = '+str(memory)+'; allowsEbsOptimized = '+('true' if ebsOptimized else 'false')+'; nitro = '+('true' if supportsNVMe else 'false')+'; };'

print '{'
for instanceType in sorted(instanceTypes.keys()):
    print instanceTypes[instanceType]
print '}'
