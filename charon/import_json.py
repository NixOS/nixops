# -*- coding: utf-8 -*-

import charon.deployment
import charon.backends
import json

def import_json(db_file, json_file):
    f = open(json_file, 'r')
    state = json.load(f)

    db = charon.deployment.open_database(db_file)

    with db:

        depl = charon.deployment.create_deployment(db, uuid=state['uuid'])
        depl.nix_exprs = state['networkExprs']
        depl.nix_path = state.get('nixPath', [])
        depl.args = state.get('args', {})
        depl.description = state.get('description', None)
        depl.rollback_enabled = state.get('enableRollback', False)
        depl.configs_path = state.get('vmsPath', None)

        for n, x in state['machines'].iteritems():
            c = depl._db.cursor()
            type = x['targetEnv']
            c.execute("insert into Machines(deployment, name, type) values (?, ?, ?)",
                      (depl.uuid, n, type))
            id = c.lastrowid

            m = charon.backends.create_state(depl, type, n, id, depl._log_file)
            depl.machines[n] = m

            m.index = x.get('index', None)
            m.state = x.get('state', charon.backends.MachineState.UNKNOWN)
            m.obsolete = x.get('obsolete', False)
            m.vm_id = x.get('vmId', None)
            m.ssh_pinged = x.get('sshPinged', False)
            m.public_vpn_key = x.get('publicVpnKey', None)
            m.store_keys_on_machine = x.get('storeKeysOnMachine', True)
            m.cur_configs_path = x.get('vmsPath', None)
            m.cur_toplevel = x.get('toplevel', None)

            if type == "none":
                m.target_host = x['targetHost']

            elif type == "virtualbox":
                m.private_ipv4 = x.get('privateIpv4', None)
                y = x.get('virtualbox')
                m.disk = y.get('disk', None)
                m.disk_attached = y.get('diskAttached', False)
                m._client_private_key = y.get('clientPrivateKey', None)
                m._client_public_key = y.get('clientPublicKey', None)
                m._headless = y.get('headless', False)

            elif type == "ec2":
                m.public_ipv4 = x.get('ipv4', None)
                m.private_ipv4 = x.get('privateIpv4', None)
                y = x.get('ec2')
                m.elastic_ipv4 = y.get('elasticIPv4', None)
                m.access_key_id = y.get('accessKeyId', None)
                m.region = y.get('region', None)
                m.zone = y.get('zone', None)
                m.controller = y.get('controller', None)
                m.ami = y.get('ami', None)
                m.instance_type = y.get('instanceType', None)
                m.key_pair = y.get('keyPair', None)
                m.public_host_key = y.get('publicHostKey', None)
                m.private_key_file = y.get('privateKey', None)
                m.security_groups = y.get('securityGroups', None)
                m.tags = y.get('tags', {})
                m.block_device_mapping = y.get('blockDeviceMapping', {})
                m.root_device_type = y.get('rootDeviceType', None)
                m.backups = x.get('backups', {})
                z = x.get('route53', {})
                m.dns_hostname = z.get('hostname', None)
                m.dns_ttl = z.get('ttl', None)
                m.route53_access_key_id = z.get('accessKeyId', None)

        return depl
