# -*- coding: utf-8 -*-

from datadog import initialize, api

def initializeDatadog(apiKey, appKey):
    options = {'api_key': apiKey, 'app_key': appKey}
    initialize(**options)
    return (api, options)