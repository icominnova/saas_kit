import os,time,sys
import random, string
import json
import subprocess
# import imp,re,shutil
import argparse
import logging
import psycopg2
from . import check_connectivity
_logger = logging.getLogger(__name__)

def ishostaccessible(details):
    if details.get("server_type") == "self":
        return True

    _logger.warning(
        "Remote host accessibility check blocked by security policy"
    )
    return False

class connect_exception(Exception):
    def __init__(self,message):
        print(message)





def isdbaccessible(host_server, db_server, config_path=None):
    response = {
        "status": True,
        "message": "Success",
    }

    if host_server.get("server_type") != "self":
        _logger.warning(
            "Remote SaaS host DB check blocked by security policy"
        )
        return {
            "status": False,
            "message": (
                "Remote SaaS host connectivity is disabled until "
                "hardened transport is configured"
            ),
        }

    if db_server.get("server_type") != "self":
        _logger.warning(
            "Remote PostgreSQL check blocked by security policy"
        )
        return {
            "status": False,
            "message": (
                "Remote database connectivity is disabled until "
                "hardened transport is configured"
            ),
        }

    host_result = check_connectivity.ishostaccessible(
        host_server
    )

    if not host_result.get("status"):
        return host_result

    _logger.info(
        "Local database accessibility check requested"
    )

    connection = None

    try:
        connection = psycopg2.connect(
            dbname="postgres",
            user=db_server["user"],
            password=db_server["password"],
            host=db_server["host"],
            port=db_server["port"],
        )

    except Exception as exc:
        _logger.warning(
            "Local database accessibility check failed: %s",
            type(exc).__name__,
        )

        response["status"] = False
        response["message"] = "Database connection failed"

    finally:
        if connection is not None:
            connection.close()

    return response
