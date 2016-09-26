# -*- coding: utf-8 -*-

from datadog import initialize, api

def initializeDatadog(api_key, app_key):
    options = {'api_key': api_key, 'app_key': app_key}
    initialize(**options)
    return (api, options)