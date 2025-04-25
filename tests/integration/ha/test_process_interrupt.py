#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from ..helpers import (
    CONFIG_OPTS,
    TLS_STABLE_CHANNEL,
    access_all_dashboards,
    get_leader_name,
    get_relations,
)
from .helpers import (
    is_down,
    patch_restart_delay,
    remove_restart_delay,
    send_control_signal,
)

# from subprocess import CalledProcessError


logger = logging.getLogger(__name__)

CLIENT_TIMEOUT = 10
RESTART_DELAY = 60
UPDATE_STATUS_INTERVAL = 60

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    "update-status-hook-interval": f"{UPDATE_STATUS_INTERVAL}s",
    "cloudinit-userdata": """postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    """,
}
OPENSEARCH_RELATION_NAME = "opensearch-client"
TLS_CERT_APP_NAME = "self-signed-certificates"
APP_AND_TLS = [APP_NAME, TLS_CERT_APP_NAME]
PEER = "dashboard_peers"
SERVER_PORT = 5601

NUM_UNITS_APP = 2
NUM_UNITS_DB = 3

LONG_TIMEOUT = 3000
LONG_WAIT = 30


@pytest.fixture()
async def restart_delay(ops_test: OpsTest):
    for unit in ops_test.model.applications[APP_NAME].units:
        await patch_restart_delay(ops_test=ops_test, unit_name=unit.name, delay=RESTART_DELAY)
    yield
    for unit in ops_test.model.applications[APP_NAME].units:
        await remove_restart_delay(ops_test=ops_test, unit_name=unit.name)


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
        OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB, config=CONFIG_OPTS
    )

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERT_APP_NAME, channel=TLS_STABLE_CHANNEL, config=config)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERT_APP_NAME], wait_for_active=True, timeout=1000
    )

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(OPENSEARCH_APP_NAME, TLS_CERT_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERT_APP_NAME], wait_for_active=True, timeout=1000
    )

    # Opensearch Dashboards
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            wait_for_exact_units=NUM_UNITS_APP,
            timeout=1000,
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


async def _recover_from_signal(
    ops_test: OpsTest,
    signal: str,
    units: list[str],
    app_name: str = APP_NAME,
    https: bool = False,
):

    # In attempt to prevent flaky behavior
    # The process is restarted so fast, slow pipelines may not "catch" it in time
    for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True):
        with attempt:
            logger.info(f"Sending {signal} {app_name}:{units}...")
            await asyncio.gather(
                *[send_control_signal(ops_test, unit, signal, app_name) for unit in units]
            )

            # Check that process is down
            logger.info(f"Waiting for {app_name}:{units} to be down...")
            assert all(await asyncio.gather(*[is_down(ops_test, unit) for unit in units]))

    logger.info("Waiting a bit, so the process could safely restart...")
    await asyncio.sleep(UPDATE_STATUS_INTERVAL + 2)

    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, APP_NAME], wait_for_active=True, timeout=1000
    )

    logger.info("Checking OSD access...")
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]
    assert await access_all_dashboards(ops_test, opensearch_relation.id, https)


##############################################################################
# Tests
##############################################################################


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM"])
async def test_signal_opensearch_process_leader(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    db_leader_name = await get_leader_name(ops_test, app_name=OPENSEARCH_APP_NAME)
    await _recover_from_signal(ops_test, signal, [db_leader_name], app_name=OPENSEARCH_APP_NAME)


@pytest.mark.skip(reason="Opensearch is not possible to contact after recovery")
@pytest.mark.abort_on_fail
async def test_sigstop_opensearch_process_leader(ops_test: OpsTest):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_leader_name = await get_leader_name(ops_test, app_name=OPENSEARCH_APP_NAME)
    await _recover_from_signal(ops_test, "SIGSTOP", [db_leader_name], app_name=OPENSEARCH_APP_NAME)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM", "SIGSTOP"])
async def test_signal_dashboard_process_leader(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    leader_name = await get_leader_name(ops_test)
    await _recover_from_signal(ops_test, signal, [leader_name])


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM"])
async def test_signal_opensearch_process_cluster(ops_test: OpsTest, signal):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_units = [unit.name for unit in ops_test.model.applications[OPENSEARCH_APP_NAME].units]
    await _recover_from_signal(ops_test, signal, db_units, app_name=OPENSEARCH_APP_NAME)


@pytest.mark.skip(reason="Opensearch is not possible to contact after recovery")
@pytest.mark.abort_on_fail
async def test_sigstop_opensearch_process_cluster(ops_test: OpsTest):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_units = [unit.name for unit in ops_test.model.applications[OPENSEARCH_APP_NAME].units]
    await _recover_from_signal(ops_test, "SIGSTOP", db_units, app_name=OPENSEARCH_APP_NAME)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM", "SIGSTOP"])
async def test_signal_dashboard_process_cluster(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    units = [unit.name for unit in ops_test.model.applications[APP_NAME].units]
    await _recover_from_signal(ops_test, signal, units)


##############################################################################


@pytest.mark.abort_on_fail
async def test_set_tls(ops_test: OpsTest):
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
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM"])
async def test_signal_opensearch_process_leader_https(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    db_leader_name = await get_leader_name(ops_test, app_name=OPENSEARCH_APP_NAME)
    await _recover_from_signal(
        ops_test, signal, [db_leader_name], app_name=OPENSEARCH_APP_NAME, https=True
    )


@pytest.mark.skip(reason="Opensearch is not possible to contact after recovery")
@pytest.mark.abort_on_fail
async def test_sigstop_opensearch_process_leader_https(ops_test: OpsTest):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_leader_name = await get_leader_name(ops_test, app_name=OPENSEARCH_APP_NAME)
    await _recover_from_signal(
        ops_test, "SIGSTOP", [db_leader_name], app_name=OPENSEARCH_APP_NAME, https=True
    )


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM", "SIGSTOP"])
async def test_signal_dashboard_process_leader_https(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    leader_name = await get_leader_name(ops_test)
    await _recover_from_signal(ops_test, signal, [leader_name], https=True)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM"])
async def test_signal_opensearch_process_cluster_https(ops_test: OpsTest, signal):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_units = [unit.name for unit in ops_test.model.applications[OPENSEARCH_APP_NAME].units]
    await _recover_from_signal(
        ops_test, signal, db_units, app_name=OPENSEARCH_APP_NAME, https=True
    )


@pytest.mark.skip(reason="Opensearch is not possible to contact after recovery")
@pytest.mark.abort_on_fail
async def test_sigstop_opensearch_process_cluster_https(ops_test: OpsTest):
    """Signals Opensearch leader process and checks recovery + re-election."""
    db_units = [unit.name for unit in ops_test.model.applications[OPENSEARCH_APP_NAME].units]
    await _recover_from_signal(ops_test, "SIGSTOP", db_units, https=True)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGTERM", "SIGSTOP"])
async def test_signal_dashboard_process_cluster_https(ops_test: OpsTest, signal):
    """Signals OSD leader process and checks recovery + re-election."""
    units = [unit.name for unit in ops_test.model.applications[APP_NAME].units]
    await _recover_from_signal(ops_test, signal, units, https=True)
