#!/usr/bin/env python3

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path("/usr/src/app/conf/local.yml")
SERVER_CMD = ["python3", "-u", "/usr/src/app/server.py"]

BASE_URL =  "http://localhost:8888"
HEALTH_URL = f"{BASE_URL}/health"
PATCH_URL = f"{BASE_URL}/api/v2/config/main"

CONTACT_CONFIG = {
    "app.contact.dns.socket": {
        "startup": "0.0.0.0:8853",
        "runtime": "78.128.214.240:8853",
    },
    "app.contact.ftp.host": {
        "startup": "0.0.0.0",
        "runtime": "78.128.214.240",
    },
    "app.contact.http": {
        "startup": "http://127.0.0.1:8888",
        "runtime": "https://static-flab3-240.flab.cesnet.cz",
    },
    "app.contact.tcp": {
        "startup": "0.0.0.0:7010",
        "runtime": "78.128.214.240:7010",
    },
    "app.contact.tunnel.ssh.socket": {
        "startup": "0.0.0.0:8022",
        "runtime": "78.128.214.240:8022",
    },
    "app.contact.udp": {
        "startup": "0.0.0.0:7011",
        "runtime": "78.128.214.240:7011",
    },
    "app.contact.websocket": {
        "startup": "0.0.0.0:7012",
        "runtime": "static-flab3-240.flab.cesnet.cz:443",
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

process: subprocess.Popen | None = None


def signal_handler(signum, frame):
    """
    Forward termination signals to the child process.
    """
    global process

    logging.info("Received signal %s", signum)

    if process and process.poll() is None:
        logging.info("Stopping server.py...")

        process.terminate()

        try:
            process.wait(timeout=10)
            logging.info("server.py stopped cleanly.")
        except subprocess.TimeoutExpired:
            logging.warning(
                "server.py did not stop in time. Killing process."
            )
            process.kill()
            process.wait()

    sys.exit(0)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_config(config: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            config,
            file,
            sort_keys=False,
            default_flow_style=False,
        )


def apply_startup_config(config: dict) -> None:
    config.update(
        {
            key: values["startup"]
            for key, values in CONTACT_CONFIG.items()
        }
    )


def build_patch_payload() -> dict:
    return {
        "updates": [
            {
                "prop": key,
                "value": values["runtime"],
            }
            for key, values in CONTACT_CONFIG.items()
        ]
    }


def create_session(api_key: str) -> requests.Session:
    session = requests.Session()

    session.headers.update(
        {
            "KEY": api_key,
            "Content-Type": "application/json",
        }
    )

    return session


def wait_for_server(
    session: requests.Session,
    timeout: int = 60,
) -> None:
    """
    Wait until the service API becomes available.
    """

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:

        if process.poll() is not None:
            raise RuntimeError(
                "server.py exited unexpectedly "
                f"(code {process.returncode})"
            )

        try:
            response = session.get(
                HEALTH_URL,
                timeout=5,
            )

            if response.status_code == 200:
                logging.info("Server health check passed.")
                return

            if response.status_code in (401, 403):
                raise RuntimeError(
                    "Authentication failed during health check."
                )

            logging.debug(
                "Health check returned HTTP %d",
                response.status_code,
            )

        except requests.RequestException as exc:
            logging.debug(
                "Health check failed: %s",
                exc,
            )

        time.sleep(1)

    raise TimeoutError(
        f"Server failed to become healthy within {timeout} seconds."
    )


def patch_runtime_config(
    session: requests.Session,
) -> None:
    """
    Apply real runtime contact configuration.
    """

    response = session.patch(
        PATCH_URL,
        json=build_patch_payload(),
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "Runtime configuration update failed "
            f"({response.status_code}): {response.text}"
        )

    logging.info(
        "Runtime configuration updated successfully."
    )


def main() -> int:
    global process

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info("Loading configuration.")

    config = load_config()

    try:
        api_key = "todo"
    except KeyError:
        raise RuntimeError(
            "Missing required configuration key: api_key_red"
        )

    logging.info(
        "Applying temporary startup configuration."
    )

    apply_startup_config(config)
    save_config(config)

    logging.info(
        "Starting server.py."
    )

    process = subprocess.Popen(
        SERVER_CMD,
    )

    with create_session(api_key) as session:
        wait_for_server(session)
        patch_runtime_config(session)

    logging.info(
        "Initialization complete. "
        "Waiting for server process."
    )

    return process.wait()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Startup failed.")
        sys.exit(1)
