from .create_certificate import (
    check_ips,
    generate_certificate,
)

import logging
import os
import re
import subprocess
from configparser import ConfigParser
from pathlib import Path


_logger = logging.getLogger(__name__)


CLIENT_EMAIL = "saasclient@odoo-saas.webkul.com"
WEBROOT_PATH = "/usr/share/nginx/html/"

SUDO_BIN = "/usr/bin/sudo"
NGINX_BIN = "/usr/sbin/nginx"

DOMAIN_RE = re.compile(
    r"^((?=[a-z0-9-]{1,63}\.)"
    r"(xn--)?[a-z0-9]+(-[a-z0-9]+)*\.)+"
    r"[a-z]{2,63}$"
)

BACKEND_RE = re.compile(
    r"^127\.0\.0\.1:([0-9]{1,5})$"
)

PROXY_PASS_RE = re.compile(
    r"proxy_pass\s+http://([^;\s]+)\s*;"
)


def _normalize_domain(value):
    domain = (value or "").strip().lower().rstrip(".")

    if not DOMAIN_RE.fullmatch(domain):
        raise ValueError("Invalid domain name")

    return domain


def _validate_backend(value):
    backend = (value or "").strip()

    match = BACKEND_RE.fullmatch(backend)

    if not match:
        raise ValueError(
            "Invalid local backend"
        )

    port = int(match.group(1))

    if port < 1 or port > 65535:
        raise ValueError(
            "Invalid backend port"
        )

    return backend


def _vhost_base(docker_vhosts):
    base = Path(docker_vhosts).resolve()

    if not base.is_dir():
        raise ValueError(
            "Invalid vhost directory"
        )

    return base


def _safe_vhost_path(docker_vhosts, domain):
    domain = _normalize_domain(domain)
    base = _vhost_base(docker_vhosts)

    path = base / f"{domain}.conf"

    if path.exists() and path.is_symlink():
        raise ValueError(
            "Symlink vhost files are not permitted"
        )

    if path.parent.resolve() != base:
        raise ValueError(
            "Invalid vhost path"
        )

    return path


def _safe_template_path(docker_vhosts, filename):
    base = _vhost_base(docker_vhosts)
    path = base / filename

    if not path.is_file():
        raise ValueError(
            "Vhost template not found"
        )

    if path.is_symlink():
        raise ValueError(
            "Symlink templates are not permitted"
        )

    return path


def _run_nginx(args):
    args = tuple(args)

    allowed = {
        ("-t",),
        ("-s", "reload"),
    }

    if args not in allowed:
        raise ValueError(
            "Unsupported nginx command"
        )

    try:
        result = subprocess.run(
            [
                SUDO_BIN,
                "-n",
                NGINX_BIN,
                *args,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )

    except (OSError, subprocess.TimeoutExpired):
        _logger.error(
            "Nginx command execution failed"
        )
        return False

    if result.returncode != 0:
        _logger.error(
            "Nginx command failed"
        )
        return False

    return True


def reload_nginx():
    if not _run_nginx(("-t",)):
        _logger.error(
            "Nginx configuration test failed"
        )
        return False

    if not _run_nginx(("-s", "reload")):
        _logger.error(
            "Nginx reload failed"
        )
        return False

    return True


def _restore_vhost(path, old_data):
    restore_tmp = path.with_name(
        f".{path.name}.{os.getpid()}.restore"
    )

    try:
        if old_data is None:
            if path.exists():
                path.unlink()

        else:
            restore_tmp.write_bytes(
                old_data
            )
            os.chmod(
                restore_tmp,
                0o644,
            )
            os.replace(
                restore_tmp,
                path,
            )

    finally:
        if restore_tmp.exists():
            restore_tmp.unlink()


def _commit_vhost(path, content):
    if path.exists() and path.is_symlink():
        raise ValueError(
            "Symlink vhost files are not permitted"
        )

    old_data = (
        path.read_bytes()
        if path.exists()
        else None
    )

    tmp = path.with_name(
        f".{path.name}.{os.getpid()}.tmp"
    )

    try:
        tmp.write_text(
            content,
            encoding="utf-8",
        )

        os.chmod(
            tmp,
            0o644,
        )

        os.replace(
            tmp,
            path,
        )

        if reload_nginx():
            return True

        _logger.error(
            "Rolling back invalid vhost"
        )

        _restore_vhost(
            path,
            old_data,
        )

        reload_nginx()

        return False

    finally:
        if tmp.exists():
            tmp.unlink()


def grep_backends_from_conf(
    odoo_saas_data,
    subdomain,
):
    path = _safe_vhost_path(
        odoo_saas_data,
        subdomain,
    )

    if not path.is_file():
        raise ValueError(
            "Source SaaS vhost not found"
        )

    odoo_backend = None
    websocket_backend = None

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        match = PROXY_PASS_RE.search(
            line
        )

        if not match:
            continue

        if "#WEBSOCKETBACKEND" in line:
            websocket_backend = (
                match.group(1)
            )

        elif "#ODOOBACKEND" in line:
            odoo_backend = (
                match.group(1)
            )

    if not odoo_backend:
        raise ValueError(
            "Odoo backend marker not found"
        )

    if not websocket_backend:
        raise ValueError(
            "Websocket backend marker not found"
        )

    return (
        _validate_backend(
            odoo_backend
        ),
        _validate_backend(
            websocket_backend
        ),
    )


def _render_template(
    template_path,
    custom_domain,
    odoo_backend,
    longpolling_backend,
    ssl_enabled=False,
):
    custom_domain = _normalize_domain(
        custom_domain
    )

    odoo_backend = _validate_backend(
        odoo_backend
    )

    longpolling_backend = (
        _validate_backend(
            longpolling_backend
        )
    )

    text = Path(
        template_path
    ).read_text(
        encoding="utf-8"
    )

    text = text.replace(
        "DOMAIN_TO_BE_REPLACED",
        custom_domain,
    )

    text = text.replace(
        "BACKEND_TO_BE_REPLACED",
        odoo_backend,
    )

    text = text.replace(
        "LONG_BACKEND_TO_BE_REPLACED",
        longpolling_backend,
    )

    if ssl_enabled:
        cert_path = (
            f"/etc/letsencrypt/live/"
            f"{custom_domain}/fullchain.pem"
        )

        key_path = (
            f"/etc/letsencrypt/live/"
            f"{custom_domain}/privkey.pem"
        )

        text, cert_count = re.subn(
            r"(?m)^\s*ssl_certificate\s+[^;]+;\s*$",
            f" ssl_certificate {cert_path};",
            text,
            count=1,
        )

        text, key_count = re.subn(
            r"(?m)^\s*ssl_certificate_key\s+[^;]+;\s*$",
            f" ssl_certificate_key {key_path};",
            text,
            count=1,
        )

        text, tls_count = re.subn(
            r"(?m)^\s*ssl_protocols\s+[^;]+;\s*$",
            " ssl_protocols TLSv1.2 TLSv1.3;",
            text,
            count=1,
        )

        if (
            cert_count != 1
            or key_count != 1
            or tls_count != 1
        ):
            raise ValueError(
                "HTTPS template structure is invalid"
            )

    placeholders = (
        "DOMAIN_TO_BE_REPLACED",
        "BACKEND_TO_BE_REPLACED",
        "LONG_BACKEND_TO_BE_REPLACED",
    )

    if any(
        item in text
        for item in placeholders
    ):
        raise ValueError(
            "Unresolved vhost placeholder"
        )

    return text


def replace_placeholders(
    vhost_file,
    odoo_backend,
    longpolling_backend,
    custom_domain,
):
    custom_domain = _normalize_domain(
        custom_domain
    )

    path = Path(
        vhost_file
    ).resolve()

    if path.name != f"{custom_domain}.conf":
        raise ValueError(
            "Unexpected vhost filename"
        )

    content = path.read_text(
        encoding="utf-8"
    )

    content = content.replace(
        "DOMAIN_TO_BE_REPLACED",
        custom_domain,
    )

    content = content.replace(
        "BACKEND_TO_BE_REPLACED",
        _validate_backend(
            odoo_backend
        ),
    )

    content = content.replace(
        "LONG_BACKEND_TO_BE_REPLACED",
        _validate_backend(
            longpolling_backend
        ),
    )

    return _commit_vhost(
        path,
        content,
    )


def create_vhost_redirect(
    custom_domain,
    docker_vhosts,
):
    custom_domain = _normalize_domain(
        custom_domain
    )

    path = _safe_vhost_path(
        docker_vhosts,
        custom_domain,
    )

    template = (
        _vhost_base(
            docker_vhosts
        )
        / "vhosttemplateredirect.txt"
    )

    if not path.is_file():
        return False

    if not template.is_file():
        _logger.warning(
            "Redirect vhost template is not installed"
        )
        return False

    content = path.read_text(
        encoding="utf-8"
    )

    redirect = template.read_text(
        encoding="utf-8"
    ).replace(
        "DOMAIN_TO_BE_REPLACED",
        custom_domain,
    )

    return _commit_vhost(
        path,
        content + "\n\n" + redirect,
    )


def create_vhost_https(
    subdomain,
    custom_domain,
    odoo_backend,
    longpolling_backend,
    docker_vhosts=(
        "/opt/odoo/Odoo-SAAS-Data/"
        "docker_vhosts"
    ),
):
    del subdomain

    custom_domain = _normalize_domain(
        custom_domain
    )

    path = _safe_vhost_path(
        docker_vhosts,
        custom_domain,
    )

    template = _safe_template_path(
        docker_vhosts,
        "vhosttemplatehttps.txt",
    )

    content = _render_template(
        template,
        custom_domain,
        odoo_backend,
        longpolling_backend,
        ssl_enabled=True,
    )

    return _commit_vhost(
        path,
        content,
    )


def create_vhost_http(
    subdomain,
    custom_domain,
    odoo_backend,
    longpolling_backend,
    docker_vhosts=(
        "/opt/odoo/Odoo-SAAS-Data/"
        "docker_vhosts"
    ),
    ssl_flag=False,
):
    del subdomain
    del ssl_flag

    custom_domain = _normalize_domain(
        custom_domain
    )

    path = _safe_vhost_path(
        docker_vhosts,
        custom_domain,
    )

    template = _safe_template_path(
        docker_vhosts,
        "vhosttemplatehttp.txt",
    )

    content = _render_template(
        template,
        custom_domain,
        odoo_backend,
        longpolling_backend,
        ssl_enabled=False,
    )

    return _commit_vhost(
        path,
        content,
    )


def remove_vhost(
    domain,
    docker_vhosts,
):
    domain = _normalize_domain(
        domain
    )

    path = _safe_vhost_path(
        docker_vhosts,
        domain,
    )

    if not path.exists():
        _logger.info(
            "Custom domain vhost does not exist"
        )
        return True

    old_data = path.read_bytes()

    path.unlink()

    if reload_nginx():
        return True

    _logger.error(
        "Restoring custom domain vhost after nginx failure"
    )

    _restore_vhost(
        path,
        old_data,
    )

    reload_nginx()

    return False


def read_path_saas_conf(module_path):
    saas_conf_path = os.path.join(
        module_path,
        "models/lib/saas.conf",
    )

    parser = ConfigParser()
    parser.read(
        saas_conf_path
    )

    return parser.get(
        "options",
        "odoo_saas_data",
    )


def run_certbot(
    custom_domain,
    client_email,
    webroot_path,
    dry_run,
):
    custom_domain = _normalize_domain(
        custom_domain
    )

    _logger.info(
        "Starting certificate generation for %s",
        custom_domain,
    )

    result = generate_certificate(
        custom_domain,
        client_email,
        webroot_path,
        dry_run,
    )

    if not result.get("status"):
        _logger.error(
            "Certificate generation failed for %s",
            custom_domain,
        )
        return False

    _logger.info(
        "Certificate generation completed for %s",
        custom_domain,
    )

    return True


def main_remove(
    custom_domain,
    module_path,
):
    try:
        custom_domain = _normalize_domain(
            custom_domain
        )

        odoo_saas_data = (
            read_path_saas_conf(
                module_path
            )
        )

        docker_vhosts = os.path.join(
            odoo_saas_data,
            "docker_vhosts",
        )

        if not remove_vhost(
            custom_domain,
            docker_vhosts,
        ):
            return {
                "status": False,
                "message": (
                    "Unable to remove custom "
                    "domain vhost"
                ),
            }

        return {
            "status": True,
            "message": True,
        }

    except Exception as exc:
        _logger.error(
            "Custom domain removal failed: %s",
            type(exc).__name__,
        )

        return {
            "status": False,
            "message": (
                "Custom domain removal failed"
            ),
        }


def main_add(
    subdomain,
    custom_domain,
    ssl_flag,
    module_path,
):
    try:
        subdomain = _normalize_domain(
            subdomain
        )

        custom_domain = _normalize_domain(
            custom_domain
        )

        odoo_saas_data = (
            read_path_saas_conf(
                module_path
            )
        )

        docker_vhosts = os.path.join(
            odoo_saas_data,
            "docker_vhosts",
        )

        check_ips(
            custom_domain,
            subdomain,
        )

        (
            odoo_backend,
            longpolling_backend,
        ) = grep_backends_from_conf(
            docker_vhosts,
            subdomain,
        )

        if not create_vhost_http(
            subdomain,
            custom_domain,
            odoo_backend,
            longpolling_backend,
            docker_vhosts=docker_vhosts,
        ):
            return {
                "status": False,
                "message": (
                    "HTTP vhost generation failed"
                ),
            }

        if ssl_flag:
            if not run_certbot(
                custom_domain,
                client_email=CLIENT_EMAIL,
                webroot_path=WEBROOT_PATH,
                dry_run=False,
            ):
                return {
                    "status": False,
                    "message": (
                        "SSL certificate generation failed"
                    ),
                }

            if not create_vhost_https(
                subdomain,
                custom_domain,
                odoo_backend,
                longpolling_backend,
                docker_vhosts=docker_vhosts,
            ):
                return {
                    "status": False,
                    "message": (
                        "HTTPS vhost generation failed"
                    ),
                }

        return {
            "status": True,
            "message": (
                "Custom domain configured successfully"
            ),
        }

    except Exception as exc:
        _logger.error(
            "Custom domain configuration failed: %s",
            type(exc).__name__,
        )

        return {
            "status": False,
            "message": (
                "Custom domain configuration failed"
            ),
        }


def main_add_domain(
    subdomain,
    custom_domain,
    ssl_flag,
    module_path,
):
    try:
        subdomain = _normalize_domain(
            subdomain
        )

        custom_domain = _normalize_domain(
            custom_domain
        )

        odoo_saas_data = (
            read_path_saas_conf(
                module_path
            )
        )

        docker_vhosts = os.path.join(
            odoo_saas_data,
            "docker_vhosts",
        )

        check_ips(
            custom_domain,
            subdomain,
        )

        (
            odoo_backend,
            longpolling_backend,
        ) = grep_backends_from_conf(
            docker_vhosts,
            custom_domain,
        )

        if ssl_flag:
            if not run_certbot(
                custom_domain,
                client_email=CLIENT_EMAIL,
                webroot_path=WEBROOT_PATH,
                dry_run=False,
            ):
                return {
                    "status": False,
                    "message": (
                        "SSL certificate generation failed"
                    ),
                }

            if not create_vhost_https(
                subdomain,
                custom_domain,
                odoo_backend,
                longpolling_backend,
                docker_vhosts=docker_vhosts,
            ):
                return {
                    "status": False,
                    "message": (
                        "HTTPS vhost generation failed"
                    ),
                }

        else:
            if not create_vhost_http(
                subdomain,
                custom_domain,
                odoo_backend,
                longpolling_backend,
                docker_vhosts=docker_vhosts,
            ):
                return {
                    "status": False,
                    "message": (
                        "HTTP vhost generation failed"
                    ),
                }

        return {
            "status": True,
            "message": (
                "Custom domain configured successfully"
            ),
        }

    except Exception as exc:
        _logger.error(
            "Client custom domain configuration failed: %s",
            type(exc).__name__,
        )

        return {
            "status": False,
            "message": (
                "Custom domain configuration failed"
            ),
        }
