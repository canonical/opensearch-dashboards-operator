#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from subprocess import CalledProcessError

import integration.ha.helpers as ha_helpers
import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    CONFIG_OPTS,
    TLS_STABLE_CHANNEL,
    access_all_dashboards,
    all_dashboards_unavailable,
    get_address,
    get_leader_name,
)

logger = logging.getLogger(__name__)


CLIENT_TIMEOUT = 10
RESTART_DELAY = 60

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    "cloudinit-userdata": """postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    """,
}
TLS_CERT_APP_NAME = "self-signed-certificates"

ALL_APPS = [APP_NAME, TLS_CERT_APP_NAME, OPENSEARCH_APP_NAME]
APP_AND_TLS = [APP_NAME, TLS_CERT_APP_NAME]
PEER = "dashboard_peers"
SERVER_PORT = 5601

NUM_UNITS_APP = 2
NUM_UNITS_DB = 2

LONG_TIMEOUT = 3000
LONG_WAIT = 30


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm: str, series: str):
    """Tests that the charm deploys safely"""
    await ops_test.model.deploy(
        charm, application_name=APP_NAME, num_units=NUM_UNITS_APP, series=series
    )

    # Opensearch
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/edge",
        num_units=NUM_UNITS_DB,
        config=CONFIG_OPTS,
    )

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERT_APP_NAME, channel=TLS_STABLE_CHANNEL, config=config)

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(OPENSEARCH_APP_NAME, TLS_CERT_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERT_APP_NAME],
        wait_for_active=True,
        timeout=LONG_TIMEOUT,
    )

    # Opensearch Dashboards
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            wait_for_exact_units=NUM_UNITS_APP,
            timeout=LONG_TIMEOUT,
            idle_period=30,
        )

    assert ops_test.model.applications[APP_NAME].status == "blocked"

    pytest.relation = await ops_test.model.relate(OPENSEARCH_APP_NAME, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, APP_NAME], wait_for_active=True, timeout=1000
    )


##############################################################################
# Helper functions
##############################################################################


async def network_cut_leader(ops_test: OpsTest, https: bool = False):
    """Full network cut for the leader, resulting in IP change."""
    old_leader_name = await get_leader_name(ops_test)
    old_ip = await get_address(ops_test, old_leader_name)
    machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)

    logger.info(
        f"Cutting leader unit from network from {old_leader_name} ({machine_name}/{old_ip})..."
    )
    ha_helpers.cut_unit_network(machine_name)

    logger.info(f"Waiting until unit {old_leader_name} is not reachable")
    await ops_test.model.block_until(
        lambda: not ha_helpers.reachable(old_ip, SERVER_PORT),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info(f"Waiting until unit {old_leader_name} is 'lost'")
    await ops_test.model.block_until(
        lambda: ["unknown", "lost"]
        == ha_helpers.get_unit_state_from_status(ops_test, old_leader_name),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    logger.info("Checking new leader was elected")
    new_leader_name = await get_leader_name(ops_test)
    assert new_leader_name != old_leader_name

    # Check all nodes but the old leader
    logger.info("Checking Dashboard access for the rest of the nodes...")
    assert await access_all_dashboards(ops_test, skip=[old_leader_name], https=https)

    logger.info(f"Restoring network for {old_leader_name}...")
    try:
        ha_helpers.restore_unit_network(machine_name)
    except CalledProcessError:  # in case it was already cleaned up
        pass

    logger.info("Waiting for Juju to detect new IP...")
    await ops_test.model.block_until(
        lambda: old_ip not in ha_helpers.get_hosts_from_status(ops_test).values(),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    new_ip = await get_address(ops_test, old_leader_name)
    assert new_ip != old_ip
    logger.info(f"Old IP {old_ip} has changed to {new_ip}...")

    await ops_test.model.wait_for_idle(apps=ALL_APPS, wait_for_active=True, timeout=LONG_TIMEOUT)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, https=https)


async def network_throttle_leader(ops_test: OpsTest, https: bool = False):
    """Network interrupt for the leader without IP change."""
    old_leader_name = await get_leader_name(ops_test)
    old_ip = await get_address(ops_test, old_leader_name)

    logger.info("Network throttle on {old_leader_name}...")
    machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)
    ha_helpers.network_throttle(machine_name)

    logger.info(f"Waiting until unit {old_leader_name} is not reachable")
    await ops_test.model.block_until(
        lambda: not ha_helpers.reachable(old_ip, SERVER_PORT),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info(f"Waiting until unit {old_leader_name} is 'lost'")
    await ops_test.model.block_until(
        lambda: ["unknown", "lost"]
        == ha_helpers.get_unit_state_from_status(ops_test, old_leader_name),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info("Checking leader re-election...")
    new_leader_name = await get_leader_name(ops_test)
    assert new_leader_name != old_leader_name

    logger.info("Checking Dashboard access for the rest of the nodes...")
    assert await access_all_dashboards(ops_test, skip=[old_leader_name], https=https)

    logger.info("Restoring network...")
    try:
        ha_helpers.network_release(machine_name)
    except CalledProcessError:  # in case it was already cleaned up
        pass

    logger.info(f"Waiting until unit {old_leader_name} is reachable again")
    await ops_test.model.block_until(
        lambda: ha_helpers.reachable(old_ip, SERVER_PORT),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    # Double-checking that the network throttle didn't change the IP
    current_ip = await get_address(ops_test, old_leader_name)
    assert old_ip == current_ip

    await ops_test.model.wait_for_idle(apps=ALL_APPS, wait_for_active=True, timeout=LONG_TIMEOUT)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, https=https)


async def network_cut_application(ops_test: OpsTest, https: bool = False):
    """Full network cut for the whole application, resulting in IP change."""
    logger.info("Cutting all units from network...")

    machines = []
    unit_ip_map = {}
    for unit in ops_test.model.applications[APP_NAME].units:
        machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
        ip = await get_address(ops_test, unit.name)

        logger.info(f"Cutting unit {unit.name} from network...")
        ha_helpers.cut_unit_network(machine_name)

        machines.append(machine_name)
        unit_ip_map[unit.name] = ip

    units = list(unit_ip_map.keys())
    ips = list(unit_ip_map.values())

    logger.info(f"Waiting until units {units} are not reachable")
    await ops_test.model.block_until(
        lambda: not all(ha_helpers.reachable(ip, SERVER_PORT) for ip in ips),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info(f"Waiting until unit {units} are 'lost'")
    await ops_test.model.block_until(
        lambda: all(
            ["unknown", "lost"] == ha_helpers.get_unit_state_from_status(ops_test, unit)
            for unit in units
        ),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info("Checking lack of Dashboard access...")
    assert all_dashboards_unavailable(ops_test, https=https)

    logger.info("Restoring network...")
    for machine_name in machines:
        try:
            ha_helpers.restore_unit_network(machine_name)
        except CalledProcessError:  # in case it was already cleaned up
            pass

    logger.info("Waiting for Juju to detect new IPs...")
    await ops_test.model.block_until(
        lambda: all(
            ha_helpers.get_hosts_from_status(ops_test).get(unit)
            and ha_helpers.get_hosts_from_status(ops_test)[unit] != unit_ip_map[unit]
            for unit in unit_ip_map
        ),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    for unit, old_ip in unit_ip_map.items():
        new_ip = await get_address(ops_test, unit)
        assert new_ip != old_ip
        logger.info(f"Old IP {old_ip} has changed to {new_ip}...")

    await ops_test.model.wait_for_idle(apps=ALL_APPS, wait_for_active=True, timeout=LONG_TIMEOUT)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, https=https)


async def network_throttle_application(ops_test: OpsTest, https: bool = False):
    """Network interrupt for the whole application without IP change."""
    logger.info("Cutting all units from network...")

    machines = []
    unit_ip_map = {}
    for unit in ops_test.model.applications[APP_NAME].units:
        machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
        ip = await get_address(ops_test, unit.name)

        logger.info(f"Cutting unit {unit.name} from network...")
        ha_helpers.network_throttle(machine_name)

        machines.append(machine_name)
        unit_ip_map[unit.name] = ip

    units = list(unit_ip_map.keys())
    ips = list(unit_ip_map.values())

    logger.info(f"Waiting until units {units} are not reachable")
    await ops_test.model.block_until(
        lambda: not all(ha_helpers.reachable(ip, SERVER_PORT) for ip in ips),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info(f"Waiting until unit {units} are 'lost'")
    await ops_test.model.block_until(
        lambda: all(
            ["unknown", "lost"] == ha_helpers.get_unit_state_from_status(ops_test, unit)
            for unit in units
        ),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    logger.info("Checking lack of Dashboard access...")
    assert all_dashboards_unavailable(ops_test, https=https)

    logger.info("Restoring network...")
    for machine_name in machines:
        try:
            ha_helpers.network_release(machine_name)
        except CalledProcessError:  # in case it was already cleaned up
            pass

    logger.info(f"Waiting until units {units} are reachable again")
    await ops_test.model.block_until(
        lambda: all(ha_helpers.reachable(ip, SERVER_PORT) for ip in ips),
        timeout=LONG_TIMEOUT,
        wait_period=LONG_WAIT,
    )

    # Double-checking that the network throttle didn't change the IP
    assert all(
        ha_helpers.get_hosts_from_status(ops_test).get(unit)
        and ha_helpers.get_hosts_from_status(ops_test)[unit] == unit_ip_map[unit]
        for unit in unit_ip_map
    )

    await ops_test.model.wait_for_idle(apps=ALL_APPS, wait_for_active=True, timeout=LONG_TIMEOUT)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, https=https)


##############################################################################
# Tests
##############################################################################


@pytest.mark.abort_on_fail
async def test_network_cut_ip_change_leader_http(ops_test: OpsTest, request):
    await network_cut_leader(ops_test)


@pytest.mark.abort_on_fail
async def test_network_cut_no_ip_change_leader_http(ops_test: OpsTest, request):
    await network_throttle_leader(ops_test)


@pytest.mark.abort_on_fail
async def test_network_cut_ip_change_application_http(ops_test: OpsTest, request):
    await network_cut_application(ops_test)


@pytest.mark.abort_on_fail
async def test_network_no_ip_change_application_http(ops_test: OpsTest, request):
    await network_throttle_application(ops_test)


##############################################################################


@pytest.mark.abort_on_fail
async def test_set_tls(ops_test: OpsTest, request):
    """Not a real test but a separate stage to start TLS testing"""
    logger.info("Initializing TLS Charm connections")
    await ops_test.model.relate(APP_NAME, TLS_CERT_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERT_APP_NAME], wait_for_active=True, timeout=LONG_TIMEOUT
    )

    logger.info("Checking Dashboard access after TLS is configured")
    assert await access_all_dashboards(ops_test, https=True)


##############################################################################


@pytest.mark.abort_on_fail
async def test_network_cut_ip_change_leader_https(ops_test: OpsTest, request):
    await network_cut_leader(ops_test, https=True)


@pytest.mark.abort_on_fail
async def test_network_cut_no_ip_change_leader_https(ops_test: OpsTest, request):
    await network_throttle_leader(ops_test, https=True)


@pytest.mark.abort_on_fail
async def test_network_cut_ip_change_application_https(ops_test: OpsTest, request):
    await network_cut_application(ops_test, https=True)


@pytest.mark.abort_on_fail
async def test_network_cut_no_ip_change_application_https(ops_test: OpsTest, request):
    await network_throttle_application(ops_test, https=True)
