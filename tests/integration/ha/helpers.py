#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import socket
import subprocess
from pathlib import Path
from typing import Dict, Optional

import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, retry, stop_after_attempt, wait_fixed

from literals import SERVER_PORT

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
PROCESS = "/snap/opensearch-dashboards/current/usr/share/opensearch-dashboards/node/bin/node"
DB_PROCESS = "org.opensearch.bootstrap.OpenSearch"
SERVICE_DEFAULT_PATH = "/etc/systemd/system/snap.charmed-zookeeper.daemon.service"
PEER = "cluster"


class ProcessError(Exception):
    """Raised when a process fails."""


class ProcessRunningError(Exception):
    """Raised when a process is running when it is not expected to be."""


@retry(
    wait=wait_fixed(5),
    stop=stop_after_attempt(60),
    reraise=True,
)
def reachable(host: str, port: int) -> bool:
    """Attempting a socket connection to a host/port."""
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((host, port))
        return True
    except Exception as e:
        logger.error(e)
        return False
    finally:
        s.close()


def get_hosts_from_status(
    ops_test: OpsTest, app_name: str = APP_NAME, port: int = SERVER_PORT
) -> dict[str, str]:
    """Manually calls `juju status` and grabs the host addresses from there for a given application.

    Needed as after an ip change (e.g network cut test), OpsTest does not recognise the new address.

    Args:
        ops_test: OpsTest
        app_name: the Juju application to get hosts from
            Defaults to `opensearch-dashboards`

    Returns:
        List of Opensearch Dashboards server addresses and ports
    """
    ips = subprocess.check_output(
        f"JUJU_MODEL={ops_test.model_full_name} juju status {app_name} | grep '{APP_NAME}/[0-9]' "
        " | sed -e s/\*// | awk -F ' *' '{ print $1 \":\" $5 }'",  # noqa
        shell=True,
        universal_newlines=True,
    ).split()

    return {ip.split(":")[0]: ip.split(":")[1] for ip in ips}


def get_unit_state_from_status(
    ops_test: OpsTest, unit_name: str, app_name: str = APP_NAME, port: int = SERVER_PORT
) -> list[str]:
    """Manually calls `juju status` and grabs the host addresses from there for a given application.

    Needed as after an ip change (e.g network cut test), OpsTest does not recognise the new address.

    Args:
        ops_test: OpsTest
        app_name: the Juju application to get hosts from
            Defaults to `opensearch-dashboards`

    Returns:
        List of Opensearch Dashboards server addresses and ports
    """
    state = subprocess.check_output(
        f"JUJU_MODEL={ops_test.model_full_name} juju status {app_name} | grep '{unit_name} ' "
        " | sed -e s/\*// | awk -F ' *' '{ print $2 \":\" $3 }'",  # noqa
        shell=True,
        universal_newlines=True,
    ).strip()

    return state.split(":")


def get_hosts(ops_test: OpsTest, app_name: str = APP_NAME, port: int = SERVER_PORT) -> str:
    """Gets all addresses for a given application.

    Args:
        ops_test: OpsTest
        app_name: the Juju application to get hosts from
            Defaults to `zookeeper`
        port: the desired port.
            Defaults to `2181`

    Returns:
        Comma-delimited string of server addresses and ports
    """
    return ",".join(
        [
            f"{unit.public_address}:{str(port)}"
            for unit in ops_test.model.applications[app_name].units
        ]
    )


def get_unit_host(
    ops_test: OpsTest, unit_name: str, app_name: str = APP_NAME, port: int = 2181
) -> str:
    """Gets server address for a given unit name.

    Args:
        ops_test: OpsTest
        unit_name: the Juju unit to get host from
        app_name: the Juju application the unit belongs to
            Defaults to `zookeeper`
        port: the desired port.
            Defaults to `2181`

    Returns:
        String of server address and port
    """
    return [
        f"{unit.public_address}:{str(port)}"
        for unit in ops_test.model.applications[app_name].units
        if unit.name == unit_name
    ][0]


def get_unit_name_from_host(ops_test: OpsTest, host: str, app_name: str = APP_NAME) -> str:
    """Gets unit name for a given server address.

    Args:
        ops_test: OpsTest
        host: the ip address and port
        app_name: the Juju application the server belongs to
            Defaults to `zookeeper`

    Returns:
        String of unit name
    """
    return [
        unit.name
        for unit in ops_test.model.applications[app_name].units
        if unit.public_address == host.split(":")[0]
    ][0]


async def get_unit_machine_name(ops_test: OpsTest, unit_name: str) -> str:
    """Gets current LXD machine name for a given unit name.

    Args:
        ops_test: OpsTest
        unit_name: the Juju unit name to get from

    Returns:
        String of LXD machine name
            e.g juju-123456-0
    """
    _, raw_hostname, _ = await ops_test.juju("ssh", unit_name, "hostname")
    return raw_hostname.strip()


def cut_unit_network(machine_name: str) -> None:
    """Cuts network access for a given LXD container (will result in an IP address change).

    Args:
        machine_name: the LXD machine name to cut network for
            e.g `juju-123456-0`
    """
    cut_network_command = f"lxc config device add {machine_name} eth0 none"
    subprocess.check_call(cut_network_command.split())


def restore_unit_network(machine_name: str) -> None:
    """Restores network access for a given LXD container. IP change if eth0 was set as 'none'.

    Args:
        machine_name: the LXD machine name to restore network for
            e.g `juju-123456-0`
    """
    restore_network_command = f"lxc config device remove {machine_name} eth0"
    subprocess.check_call(restore_network_command.split())


def network_throttle(machine_name: str) -> None:
    """Cut network from a lxc container (without causing the change of the unit IP address).

    Args:
        machine_name: lxc container hostname
    """
    override_command = f"lxc config device override {machine_name} eth0"
    try:
        subprocess.check_call(override_command.split())
    except subprocess.CalledProcessError:
        # Ignore if the interface was already overridden.
        pass
    limit_set_command = f"lxc config device set {machine_name} eth0 limits.egress=0kbit"
    subprocess.check_call(limit_set_command.split())
    limit_set_command = f"lxc config device set {machine_name} eth0 limits.ingress=1kbit"
    subprocess.check_call(limit_set_command.split())
    limit_set_command = f"lxc config device set {machine_name} eth0 limits.priority=10"
    subprocess.check_call(limit_set_command.split())


def network_release(machine_name: str) -> None:
    """Restore network from a lxc container (without causing the change of the unit IP address).

    Args:
        machine_name: lxc container hostname
    """
    limit_set_command = f"lxc config device set {machine_name} eth0 limits.priority="
    subprocess.check_call(limit_set_command.split())
    restore_unit_network(machine_name=machine_name)


async def send_control_signal(
    ops_test: OpsTest, unit_name: str, signal: str, app_name: str = APP_NAME
) -> None:
    """Issues given job control signals to a server process on a given Juju unit.

    Args:
        ops_test: OpsTest
        unit_name: the Juju unit running the server process
        signal: the signal to issue
            e.g `SIGKILL`, `SIGSTOP`, `SIGCONT` etc
        app_name: the Juju application
    """
    process = PROCESS if app_name == APP_NAME else DB_PROCESS
    kill_cmd = f"exec --unit {unit_name} -- pkill --signal {signal} -f {process}"
    return_code, stdout, stderr = await ops_test.juju(*kill_cmd.split())

    if return_code != 0:
        raise Exception(
            f"Expected kill command {kill_cmd} to succeed instead it failed: {return_code}, {stdout}, {stderr}"
        )


async def get_password(
    ops_test, user: Optional[str] = "super", app_name: Optional[str] = None
) -> str:
    if not app_name:
        app_name = APP_NAME
    secret_data = await get_secret_by_label(ops_test, f"{PEER}.{app_name}.app", app_name)
    return secret_data.get(f"{user}-password")


async def get_secret_by_label(ops_test, label: str, owner: Optional[str] = None) -> Dict[str, str]:
    secrets_meta_raw = await ops_test.juju("list-secrets", "--format", "json")
    secrets_meta = json.loads(secrets_meta_raw[1])

    for secret_id in secrets_meta:
        if owner and not secrets_meta[secret_id]["owner"] == owner:
            continue
        if secrets_meta[secret_id]["label"] == label:
            break

    secret_data_raw = await ops_test.juju("show-secret", "--format", "json", "--reveal", secret_id)
    secret_data = json.loads(secret_data_raw[1])
    return secret_data[secret_id]["content"]["Data"]


async def is_down(ops_test: OpsTest, unit: str, app_name: str = APP_NAME) -> bool:
    """Check if a unit zookeeper process is down."""
    process = "node" if app_name == APP_NAME else "java"
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
            with attempt:
                search_db_process = f"exec --unit {unit} pgrep -x {process}"
                _, processes, _ = await ops_test.juju(*search_db_process.split())
                # splitting processes by "\n" results in one or more empty lines, hence we
                # need to process these lines accordingly.
                processes = [proc for proc in processes.split("\n") if len(proc) > 0]
                if len(processes) > 0:
                    raise ProcessRunningError
    except RetryError:
        return False

    return True


async def is_service_down(ops_test: OpsTest, unit: str) -> bool:
    result = subprocess.check_output(
        ["bash", "-c", f"JUJU_MODEL={ops_test.model.name} juju ssh {unit} snap status {APP_NAME}"],
        text=True,
    )
    return True if "running" in result else False


async def all_db_processes_down(ops_test: OpsTest) -> bool:
    """Verifies that all units of the charm do not have the DB process running."""
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
            with attempt:
                for unit in ops_test.model.applications[APP_NAME].units:
                    search_db_process = f"exec --unit {unit.name} pgrep -x java"
                    _, processes, _ = await ops_test.juju(*search_db_process.split())
                    # splitting processes by "\n" results in one or more empty lines, hence we
                    # need to process these lines accordingly.
                    processes = [proc for proc in processes.split("\n") if len(proc) > 0]
                    if len(processes) > 0:
                        raise ProcessRunningError
    except RetryError:
        return False

    return True


async def patch_restart_delay(ops_test: OpsTest, unit_name: str, delay: int) -> None:
    """Adds a restart delay in the DB service file.

    When the DB service fails it will now wait for `delay` number of seconds.
    """
    add_delay_cmd = (
        f"exec --unit {unit_name} -- "
        f"sudo sed -i -e '/^[Service]/a RestartSec={delay}' "
        f"{SERVICE_DEFAULT_PATH}"
    )
    await ops_test.juju(*add_delay_cmd.split(), check=True)

    # reload the daemon for systemd to reflect changes
    reload_cmd = f"exec --unit {unit_name} -- sudo systemctl daemon-reload"
    await ops_test.juju(*reload_cmd.split(), check=True)


async def remove_restart_delay(ops_test: OpsTest, unit_name: str) -> None:
    """Removes the restart delay from the service."""
    remove_delay_cmd = (
        f"exec --unit {unit_name} -- sed -i -e '/^RestartSec=.*/d' {SERVICE_DEFAULT_PATH}"
    )
    await ops_test.juju(*remove_delay_cmd.split(), check=True)

    # reload the daemon for systemd to reflect changes
    reload_cmd = f"exec --unit {unit_name} -- sudo systemctl daemon-reload"
    await ops_test.juju(*reload_cmd.split(), check=True)
