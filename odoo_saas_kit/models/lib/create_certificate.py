import logging
import os
import re
import socket
import subprocess
from pathlib import Path


_logger = logging.getLogger(__name__)

DOMAIN_RE = re.compile(
    r"^((?=[a-z0-9-]{1,63}\.)"
    r"(xn--)?[a-z0-9]+(-[a-z0-9]+)*\.)+"
    r"[a-z]{2,63}$"
)

CERTBOT_HELPER = "/usr/local/sbin/sunsoft-certbot"
SUDO_BIN = "/usr/bin/sudo"
EXPECTED_WEBROOT = Path("/usr/share/nginx/html").resolve()


def _normalize_domain(value):
    domain = (value or "").strip().lower().rstrip(".")

    if not DOMAIN_RE.fullmatch(domain):
        raise ValueError("Invalid domain name")

    return domain


def create_dir(webroot_path="/usr/share/nginx/html/"):
    root = Path(webroot_path).resolve()

    if root != EXPECTED_WEBROOT:
        raise ValueError("Unsupported ACME webroot")

    challenge = root / ".well-known" / "acme-challenge"
    challenge.mkdir(
        parents=True,
        exist_ok=True,
    )

    return str(challenge)


def _resolve_ips(domain):
    results = socket.getaddrinfo(
        domain,
        None,
        type=socket.SOCK_STREAM,
    )

    return {
        item[4][0]
        for item in results
        if item and item[4]
    }


def check_ips(custom_domain, subdomain):
    custom_domain = _normalize_domain(custom_domain)
    subdomain = _normalize_domain(subdomain)

    _logger.info(
        "Checking DNS mapping for custom domain %s",
        custom_domain,
    )

    try:
        custom_ips = _resolve_ips(custom_domain)
        source_ips = _resolve_ips(subdomain)

    except (socket.gaierror, OSError):
        raise Exception(
            "The entered domain could not be resolved. "
            "Please ensure DNS is mapped correctly."
        )

    if not custom_ips or not source_ips:
        raise Exception(
            "Unable to determine DNS addresses."
        )

    if custom_ips.isdisjoint(source_ips):
        raise Exception(
            "Custom domain is not mapped to the SaaS server."
        )

    return True


def generate_certificate(
    domain_name,
    client_email,
    webroot_path,
    dry_run,
):
    del client_email

    try:
        domain = _normalize_domain(domain_name)

        webroot = Path(webroot_path).resolve()

        if webroot != EXPECTED_WEBROOT:
            raise ValueError(
                "Unsupported ACME webroot"
            )

        cmd = [
            SUDO_BIN,
            "-n",
            CERTBOT_HELPER,
            domain,
        ]

        if dry_run:
            cmd.append("--dry-run")

        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
            check=False,
        )

        return {
            "status": proc.returncode == 0,
            "stdout": "",
            "stderr": "",
            "returncode": proc.returncode,
        }

    except subprocess.TimeoutExpired:
        _logger.error(
            "Certificate generation timed out"
        )

    except (OSError, ValueError):
        _logger.error(
            "Certificate generation rejected"
        )

    return {
        "status": False,
        "stdout": "",
        "stderr": "",
        "returncode": 1,
    }
