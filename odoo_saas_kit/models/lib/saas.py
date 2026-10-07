import os,time,sys
import random, string
import json
import subprocess
# import imp,re,shutil
import argparse
import logging
from . import saas_remote
from . import saas_localhost

_logger = logging.getLogger(__name__)

try:
    import paramiko
except ImportError as e:
    _logger.info("Paramiko Library not installed!!")

def isitaccessible(details):
    _logger.error(
        "Remote SaaS connectivity is disabled until hardened transport is configured"
    )
    return False

def create_db_template(db_template = None, modules = None, config_path = None, host_server = None, db_server = None, version = "19.0", is_enterprise = False, enterprise_addons_path = None):
    _logger.info("SaaS request received; sensitive context redacted")
    if host_server.get('server_type') == "self":
        _logger.info("On local Server")
        _logger.info("Saas Calling saas_localhost.create_db_template script ")
        return saas_localhost.create_db_template(**locals())
    elif host_server.get('server_type') == "remote":
        _logger.info("On remote Server")
        if not isitaccessible(host_server):
            _logger.error( str({"status": "Remote host not reachable"}))
            raise Exception("Remote Server not reachable")
        else:
            _logger.info("Connected")
        _logger.info("Saas Calling saas_remote.create_db_template script ")
        return saas_remote.create_db_template(**locals())

def main(context=None):
    _logger.info("SaaS request received; sensitive context redacted")
    if context['host_server']['server_type'] == "self":
        _logger.info("On local Server")
        _logger.info("Saas Calling saas_localhost.main script ")
        return saas_localhost.main(context)
    elif context['host_server']['server_type'] == "remote":
        if not isitaccessible(context['host_server']):
            _logger.error( str({"status": "Remote host not reachable"}))
            raise Exception("Remote Server not reachable")
        else:
            _logger.info("Connected")
        _logger.info("Saas Calling saas_remote.main script ")
        return saas_remote.main(context)

def rebuild(context=None):
    _logger.info("SaaS request received; sensitive context redacted")
    if context['host_server']['server_type'] == "self":
        _logger.info("On local Server")
        _logger.info("Saas Calling saas_localhost.main script ")
        return saas_localhost.rebuild(context)
    elif context['host_server']['server_type'] == "remote":
        if not isitaccessible(context['host_server']):
            _logger.error( str({"status": "Remote host not reachable"}))
            raise Exception("Remote Server not reachable")
        else:
            _logger.info("Connected")
        _logger.info("Saas Calling saas_remote.main script ")
        return saas_remote.rebuild(context)
