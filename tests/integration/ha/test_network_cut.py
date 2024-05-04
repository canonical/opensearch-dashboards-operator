#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path
from subprocess import CalledProcessError

import integration.ha.helpers as ha_helpers
import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import access_all_dashboards, extra_secure_wait_for_idle, get_leader_name

logger = logging.getLogger(__name__)


CLIENT_TIMEOUT = 10
RESTART_DELAY = 60

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    # "update-status-hook-interval": "1m",
    "cloudinit-userdata": """postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    """,
}
TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"
APP_AND_TLS = [APP_NAME, TLS_CERTIFICATES_APP_NAME]

NUM_UNITS_APP = 2
NUM_UNITS_DB = 3


# @pytest.fixture()
# async def restart_delay(ops_test: OpsTest):
#     for unit in ops_test.model.applications[ha_helpers.APP_NAME].units:
#         await ha_helpers.patch_restart_delay(
#             ops_test=ops_test, unit_name=unit.name, delay=RESTART_DELAY
#         )
#     yield
#     for unit in ops_test.model.applications[ha_helpers.APP_NAME].units:
#         await ha_helpers.remove_restart_delay(ops_test=ops_test, unit_name=unit.name)
#
#
# @pytest.fixture()
# async def no_lxd_dnsmasq():
#     ha_helpers.disable_lxd_dnsmasq()
#     yield
#     ha_helpers.enable_lxd_dnsmasq()


@pytest.mark.group(1)
@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_deploy_active(ops_test: OpsTest):
    """Tests that the charm deploys safely, without DNS resolution from LXD dnsmasq."""
    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB)

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await extra_secure_wait_for_idle(ops_test, [OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME])

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
        apps=[OPENSEARCH_APP_NAME, APP_NAME], status="active", timeout=1000
    )


# @pytest.mark.group(1)
# @pytest.mark.abort_on_fail
# async def test_network_cut_leader(ops_test: OpsTest, request):
#     """SIGKILLs leader process and checks recovery + re-election."""
#     old_leader_name = await get_leader_name(ops_test)
#
#     assert await access_all_dashboards(ops_test, pytest.relation.id)
#
#     logger.info("Cutting leader unit from network...")
#     machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)
#     ha_helpers.cut_unit_network(machine_name)
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
#
#     logger.info("Checking leader re-election...")
#     # new_leader_name = ha_helpers.get_leader_name(ops_test, non_leader_hosts)
#     new_leader_name = await get_leader_name(ops_test)
#     assert new_leader_name != old_leader_name
#
#     # Check all nodes but the old leader
#     logger.info("Checking Dashboard access for the rest of the nodes...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id, skip=[old_leader_name])
#
#     logger.info("Restoring network...")
#     try:
#         ha_helpers.restore_unit_network(machine_name)
#     except CalledProcessError:  # in case it was already cleaned up
#         pass
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await extra_secure_wait_for_idle(ops_test)
#
#     logger.info("Checking Dashboard access...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id)
#
#
# @pytest.mark.group(1)
# @pytest.mark.abort_on_fail
# async def test_network_throttle_leader(ops_test: OpsTest, request):
#     """SIGKILLs leader process and checks recovery + re-election."""
#     old_leader_name = await get_leader_name(ops_test)
#
#     assert await access_all_dashboards(ops_test, pytest.relation.id)
#
#     logger.info("Cutting leader unit from network...")
#     machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)
#     ha_helpers.network_throttle(machine_name)
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
#
#     logger.info("Checking leader re-election...")
#     # new_leader_name = ha_helpers.get_leader_name(ops_test, non_leader_hosts)
#     new_leader_name = await get_leader_name(ops_test)
#     assert new_leader_name != old_leader_name
#
#     # Check all nodes but the old leader
#     logger.info("Checking Dashboard access for the rest of the nodes...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id, skip=[old_leader_name])
#
#     logger.info("Restoring network...")
#     try:
#         ha_helpers.network_release(machine_name)
#     except CalledProcessError:  # in case it was already cleaned up
#         pass
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await extra_secure_wait_for_idle(ops_test)
#
#     logger.info("Checking Dashboard access...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id)
#
#
# @pytest.mark.group(1)
# @pytest.mark.abort_on_fail
# async def test_network_cut_application(ops_test: OpsTest, request):
#     """SIGKILLs leader process and checks recovery + re-election."""
#     logger.info("Cutting all units from network...")
#
#     machines = []
#     for unit in ops_test.model.applications[APP_NAME].units:
#         machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
#         ha_helpers.cut_unit_network(machine_name)
#         machines.append(machine_name)
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     ha_helpers.restore_unit_network(machine_name)
#     await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
#
#     # Check all nodes but the old leader
#     logger.info("Checking Dashboard access for the rest of the nodes...")
#     assert not (await access_all_dashboards(ops_test, pytest.relation.id))
#
#     logger.info("Restoring network...")
#     for machine_name in machines:
#         try:
#             ha_helpers.restore_unit_network(machine_name)
#         except CalledProcessError:  # in case it was already cleaned up
#             pass
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await extra_secure_wait_for_idle(ops_test)
#
#     logger.info("Checking Dashboard access...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id)
#
#
# @pytest.mark.group(1)
# @pytest.mark.abort_on_fail
# async def test_network_throttle_application(ops_test: OpsTest, request):
#     """SIGKILLs leader process and checks recovery + re-election."""
#     logger.info("Cutting all units from network...")
#
#     machines = []
#     for unit in ops_test.model.applications[APP_NAME].units:
#         machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
#         ha_helpers.network_throttle(machine_name)
#         machines.append(machine_name)
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
#
#     # Check all nodes but the old leader
#     logger.info("Checking Dashboard access for the rest of the nodes...")
#     assert not (await access_all_dashboards(ops_test, pytest.relation.id))
#
#     logger.info("Restoring network...")
#     for machine_name in machines:
#         try:
#             ha_helpers.network_release(machine_name)
#         except CalledProcessError:  # in case it was already cleaned up
#             pass
#
#     await asyncio.sleep(RESTART_DELAY * 2)
#     await extra_secure_wait_for_idle(ops_test)
#
#     logger.info("Checking Dashboard access...")
#     assert await access_all_dashboards(ops_test, pytest.relation.id)


##############################################################################


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_set_tls(ops_test: OpsTest, request):
    """Not a real test but a separate stage to start TLS testing"""
    logger.info("Initializing TLS Charm connections")
    await ops_test.model.relate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    await extra_secure_wait_for_idle(ops_test, APP_AND_TLS)

    logger.info("Checking Dashboard access after TLS is configured")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


##############################################################################


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_network_cut_leader_https(ops_test: OpsTest, request):
    """SIGKILLs leader process and checks recovery + re-election."""
    old_leader_name = await get_leader_name(ops_test)
    logger.info("Cutting leader unit from network...")
    machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)
    # ip = get_hosts_from_status(ops_test).get(old_leader_name)
    ha_helpers.cut_unit_network(machine_name)

    await asyncio.sleep(RESTART_DELAY * 2)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    logger.info("Checking leader re-election...")
    # new_leader_name = ha_helpers.get_leader_name(ops_test, non_leader_hosts)
    new_leader_name = await get_leader_name(ops_test)
    assert new_leader_name != old_leader_name

    # Check all nodes but the old leader
    logger.info("Checking Dashboard access for the rest of the nodes...")
    assert await access_all_dashboards(
        ops_test, pytest.relation.id, skip=[old_leader_name], https=True
    )

    logger.info("Restoring network...")
    try:
        ha_helpers.restore_unit_network(machine_name)
    except CalledProcessError:  # in case it was already cleaned up
        pass

    await asyncio.sleep(RESTART_DELAY * 2)
    await extra_secure_wait_for_idle(ops_test, APP_AND_TLS)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_network_throttle_leader_https(ops_test: OpsTest, request):
    """SIGKILLs leader process and checks recovery + re-election."""
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)
    old_leader_name = await get_leader_name(ops_test)

    logger.info("Cutting leader unit from network...")
    machine_name = await ha_helpers.get_unit_machine_name(ops_test, old_leader_name)
    ha_helpers.network_throttle(machine_name)

    await asyncio.sleep(RESTART_DELAY * 2)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    logger.info("Checking leader re-election...")
    # new_leader_name = ha_helpers.get_leader_name(ops_test, non_leader_hosts)
    new_leader_name = await get_leader_name(ops_test)
    assert new_leader_name != old_leader_name

    # Check all nodes but the old leader
    logger.info("Checking Dashboard access for the rest of the nodes...")
    assert await access_all_dashboards(
        ops_test, pytest.relation.id, skip=[old_leader_name], https=True
    )

    logger.info("Restoring network...")
    try:
        ha_helpers.network_release(machine_name)
    except CalledProcessError:  # in case it was already cleaned up
        pass

    await asyncio.sleep(RESTART_DELAY * 2)
    await extra_secure_wait_for_idle(ops_test, APP_AND_TLS)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_network_cut_application_https(ops_test: OpsTest, request):
    """SIGKILLs leader process and checks recovery + re-election."""
    logger.info("Cutting all units from network...")

    machines = []
    for unit in ops_test.model.applications[APP_NAME].units:
        machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
        ha_helpers.cut_unit_network(machine_name)
        machines.append(machine_name)

    await asyncio.sleep(RESTART_DELAY * 2)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    # Check all nodes but the old leader
    logger.info("Checking lack of Dashboard access...")
    assert not (await access_all_dashboards(ops_test, pytest.relation.id, https=True))

    logger.info("Restoring network...")
    for machine_name in machines:
        try:
            ha_helpers.restore_unit_network(machine_name)
        except CalledProcessError:  # in case it was already cleaned up
            pass

    await asyncio.sleep(RESTART_DELAY * 2)
    await extra_secure_wait_for_idle(ops_test, APP_AND_TLS)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_network_throttle_application_https(ops_test: OpsTest, request):
    """SIGKILLs leader process and checks recovery + re-election."""
    logger.info("Cutting all units from network...")

    machines = []
    for unit in ops_test.model.applications[APP_NAME].units:
        machine_name = await ha_helpers.get_unit_machine_name(ops_test, unit.name)
        ha_helpers.network_throttle(machine_name)
        machines.append(machine_name)

    await asyncio.sleep(RESTART_DELAY * 2)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    # Check all nodes but the old leader
    logger.info("Checking lack of Dashboard access...")
    assert not (await access_all_dashboards(ops_test, pytest.relation.id, https=True))

    logger.info("Restoring network...")
    for machine_name in machines:
        try:
            ha_helpers.network_release(machine_name)
        except CalledProcessError:  # in case it was already cleaned up
            pass

    await asyncio.sleep(RESTART_DELAY * 2)
    await extra_secure_wait_for_idle(ops_test, APP_AND_TLS)

    logger.info("Checking Dashboard access...")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)
