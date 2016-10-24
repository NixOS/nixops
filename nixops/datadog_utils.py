# -*- coding: utf-8 -*-

from datadog import initialize, api

def initializeDatadog(api_key, app_key):
    options = {'api_key': api_key, 'app_key': app_key}
    initialize(**options)
    return (api, options)

def get_template_variables(defn):
    variables = defn.config['templateVariables']
    template_variables = []
    for var in variables:
        tvariable = {}
        tvariable['name'] = var['name']
        tvariable['prefix'] = var['prefix']
        tvariable['default'] = var['default']
        template_variables.append(tvariable)
    return template_variables