"""Desktop window for Asset Tracking.

Starts a local HTTPS Django server (LAN + localhost) and opens it in a
native window. The phone uses the same server on Wi-Fi. This copy has its
own database and does not share data with c:\\#App\\asset-tracking.
"""

from __future__ import annotations

import os
import secrets
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.serving import run_simple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
load_dotenv(ROOT / ".env", override=True)

import django
import webview
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application

from scripts.make_dev_https_cert import lan_ipv4_addresses

DEFAULT_HTTPS_PORT = "8445"
TEST_RECAPTCHA_PUBLIC = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
TEST_RECAPTCHA_PRIVATE = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"


def https_port() -> str:
    return os.getenv("HTTPS_PORT", DEFAULT_HTTPS_PORT)


def python_exe() -> str:
    return sys.executable


def ensure_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        return
    env_path.write_text(
        "\n".join(
            [
                f"SECRET_KEY={secrets.token_urlsafe(48)}",
                "DEBUG=True",
                "ALLOWED_HOSTS=localhost,127.0.0.1",
                f"HTTPS_PORT={DEFAULT_HTTPS_PORT}",
                "USE_POSTGRES=False",
                f"RECAPTCHA_PUBLIC_KEY={TEST_RECAPTCHA_PUBLIC}",
                f"RECAPTCHA_PRIVATE_KEY={TEST_RECAPTCHA_PRIVATE}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    load_dotenv(env_path, override=True)


def run_manage(*args: str) -> None:
    subprocess.check_call([python_exe(), str(ROOT / "manage.py"), *args], cwd=ROOT)


def first_run_setup() -> None:
    run_manage("migrate", "--noinput")
    run_manage("setup_site")


def make_certs() -> None:
    subprocess.check_call([python_exe(), str(ROOT / "scripts" / "make_dev_https_cert.py")], cwd=ROOT)


def lan_urls(port: str) -> list[str]:
    return [f"https://{ip}:{port}/" for ip in lan_ipv4_addresses()]


def wait_for_server(url: str, timeout: float = 45.0) -> None:
    ctx = ssl._create_unverified_context()
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, context=ctx, timeout=2)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(f"Desktop HTTPS server did not start at {url}: {last_error}")


def start_server(port: str) -> None:
    django.setup()
    cert = str(ROOT / ".certs" / "dev.pem")
    key = str(ROOT / ".certs" / "dev-key.pem")
    app = StaticFilesHandler(get_wsgi_application())

    def serve() -> None:
        run_simple(
            "0.0.0.0",
            int(port),
            app,
            use_reloader=False,
            use_debugger=False,
            threaded=True,
            ssl_context=(cert, key),
        )

    threading.Thread(target=serve, name="asset-https", daemon=True).start()


def main() -> int:
    ensure_env()
    port = https_port()
    os.environ["HTTPS_PORT"] = port
    first_run_setup()
    make_certs()

    local_url = f"https://127.0.0.1:{port}/"
    phones = lan_urls(port)
    phone_line = phones[0] if phones else local_url
    print()
    print("Asset Tracking desktop")
    print(f"  Window: {local_url}")
    for url in phones:
        print(f"  Phone:  {url}scan/")
    print("  Login:  admin / admin123  (change this after first login)")
    print("  This app uses its own database, not the website copy.")
    print()

    start_server(port)
    wait_for_server(f"{local_url}login/")
    try:
        webview.settings["IGNORE_SSL_ERRORS"] = True
    except Exception:
        pass
    webview.create_window(
        f"Asset Tracking  |  Phone scan: {phone_line}scan/",
        local_url,
        width=1400,
        height=900,
        min_size=(960, 640),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
