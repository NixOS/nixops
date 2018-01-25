# -*- coding: utf-8 -*-

from datadog import initialize, api
import os
import time

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

def get_active_downtimes(uuid):
    downtimes = api.Downtime.get_all()
    if 'errors' in downtimes:
        raise Exception("Failed getting downtimes: "+downtimes['errors'])
    downtimes = filter(lambda dt: dt['scope'] == [ 'uuid:{}'.format(uuid) ] and dt['active'], downtimes)
    return downtimes

def create_downtime(depl):
    if not depl.datadog_downtime: return

    dts = get_active_downtimes(depl.uuid)
    start = int(time.time())
    end = start + depl.datadog_downtime_seconds

    if len(dts) == 0:
        api.Downtime.create(
            scope='uuid:{}'.format(depl.uuid),
            start=start,
            end=end
        )
    elif len(dts) == 1:
        if depl.logger.confirm("Found one active Datadog downtime with scope uuid:{}, would you like to update this downtime in stead of creating a new one?".format(depl.uuid)):
            api.Downtime.update(
                dts[0]['id'],
                scope='uuid:{}'.format(depl.uuid),
                start=start,
                end=end,
                message=''
            )
        else:
            api.Downtime.create(
                scope='uuid:{}'.format(depl.uuid),
                start=start,
                end=end
            )
    else:
        raise Exception("Found more than one active Datadog downtimes with scope uuid:{}.".format(depl.uuid))

def delete_downtime(depl):
    if not depl.datadog_downtime: return
    initializeDatadog()

    dts = get_active_downtimes(depl.uuid)

    if len(dts) == 0:
        depl.logger.warn("Could not find an active Datadog downtime with scope uuid:{}.".format(depl.uuid))
    elif len(dts) == 1:
        depl.logger.log("deleting Datadog downtime with id {}".format(dts[0]['id']))
        api.Downtime.delete(dts[0]['id'])
    else:
        if depl.logger.confirm("Found more than one Datadog downtimes with scope uuid:{}, would you like to delete them all? If no, nixops will not delete any.".format(depl.uuid)):
            for dt in dts:
                depl.logger.log("deleting Datadog downtime with id {}".format(dt['id']))
                api.Downtime.delete(dt['id'])

def create_event(depl, title, text='', tags=[]):
    if not depl.datadog_notify: return
    initializeDatadog()

    try:
        api.Event.create(title=title, text=text, tags=tags + [ 'uuid:{}'.format(depl.uuid), 'deployment:{}'.format(depl.name)])
    except:
        depl.logger.warn('Failed creating event in datadog, ignoring.')
