import os,time,sys
import random, string
import json
import subprocess
# import imp,re,shutil
import argparse
import logging
import logging
import psycopg2
_logger = logging.getLogger(__name__)

def ishostaccessible(details):
    response = {
        "status": True,
        "message": "Success",
    }

    if details.get("server_type") == "self":
        return response

    _logger.warning(
        "Remote host connectivity check blocked by security policy"
    )

    return {
        "status": False,
        "message": (
            "Remote host connectivity is disabled until "
            "hardened transport is configured"
        ),
    }

def isdbaccessible(details):
    response = {
        "status": True,
        "message": "Success",
    }

    server_type = details.get("server_type")

    if server_type not in (None, "self"):
        _logger.warning(
            "Remote database connectivity check blocked by security policy"
        )
        return {
            "status": False,
            "message": (
                "Remote database connectivity is disabled until "
                "hardened transport is configured"
            ),
        }

    connection = None

    try:
        connection = psycopg2.connect(
            dbname="postgres",
            user=details["user"],
            password=details["password"],
            host=details["host"],
            port=details["port"],
        )

    except Exception as exc:
        _logger.warning(
            "Database connectivity check failed: %s",
            type(exc).__name__,
        )

        response["status"] = False
        response["message"] = "Database connection failed"

    finally:
        if connection is not None:
            connection.close()

    return response
