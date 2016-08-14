from datadog import initialize, api
import sys

def initializeDatadog(api_key, app_key):
    options = {'api_key': api_key, 'app_key': app_key}
    initialize(**options)
    return (api, options)