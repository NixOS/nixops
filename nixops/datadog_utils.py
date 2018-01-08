# -*- coding: utf-8 -*-

from datadog import initialize, api
import os

def initializeDatadog(api_key = None, app_key = None):
    if not api_key: api_key = os.environ.get('DATADOG_API_KEY')
    if not app_key: app_key = os.environ.get('DATADOG_APP_KEY')
    if not api_key or not app_key:
        raise Exception("please set the datadog apiKey and appKey options (or the environment variables DATADOG_API_KEY and DATADOG_APP_KEY)")
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

def get_base_url():
    return "https://app.datadoghq.com/"

def create_event(depl, title, text=''):
    if not depl.datadog_notify: return

    try:
        initializeDatadog()
    except:
        return

    try:
        api.Event.create(title=title, text=text, tags=[ 'uuid:{}'.format(depl.uuid), 'deployment:{}'.format(depl.name)])
    except:
        depl.logger.warn('Failed creating event in datadog, ignoring.')
