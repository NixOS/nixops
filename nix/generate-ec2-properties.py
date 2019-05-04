#! /usr/bin/env python2
import json
from pprint import pprint
#FIXME: AWS support adviced against the use of this index file for anything other than pricing
# This file also do not provide a way to confidently check if an instance use nvme or not
# and there is currently no API that can provide such information. So manuall fixes is needed
# after running this script.
# A feature request is in place to provide an endpoint that can cover our need.
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
           if instanceType in instanceTypes and not ebsOptimized:
               continue
           instanceTypes[product['instanceType']] = '  "'+instanceType+'" = { cores = '+cores+'; memory = '+str(memory)+'; allowsEbsOptimized = '+('true' if ebsOptimized else 'false')+'; supportsNVMe = '+'false'+';};'

print '{'
for instanceType in sorted(instanceTypes.keys()):
    print instanceTypes[instanceType]
print '}'
