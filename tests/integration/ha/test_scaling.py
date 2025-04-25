#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    CONFIG_OPTS,
    TLS_CERTIFICATES_APP_NAME,
    TLS_STABLE_CHANNEL,
    access_all_dashboards,
    get_relation,
)

logger = logging.getLogger(__name__)

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

HTTP_UNITS = [0, 1, 2]
HTTPS_UNITS = [3, 4, 5]

APP_AND_TLS = [APP_NAME, TLS_CERTIFICATES_APP_NAME]


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm: str, series: str):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=1, series=series)

    # Opensearch
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME, channel="2/edge", num_units=2, config=CONFIG_OPTS
    )

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(
        TLS_CERTIFICATES_APP_NAME, channel=TLS_STABLE_CHANNEL, config=config
    )

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], wait_for_exact_units=1, timeout=1000, idle_period=30
        )

    assert ops_test.model.applications[APP_NAME].status == "blocked"

    pytest.relation = await ops_test.model.integrate(OPENSEARCH_APP_NAME, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, APP_NAME], status="active", timeout=1000
    )


##############################################################################
# Helper functions
##############################################################################


async def scale_up(ops_test: OpsTest, amount: int, https: bool = False) -> None:
    """Testing that newly added units are functional."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    expected = init_units_count + amount

    # scale up
    logger.info(f"Adding {amount} units")
    await ops_test.model.applications[APP_NAME].add_unit(count=amount)

    logger.info(f"Waiting for {amount} units to be added and stable")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        wait_for_exact_units=expected,
        timeout=1000,
        idle_period=30,
    )

    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == expected

    logger.info("Checking the functionality of the new units")
    assert await access_all_dashboards(ops_test, pytest.relation.id, https)


async def scale_down(ops_test: OpsTest, unit_ids: list[str], https: bool = False) -> None:
    """Testing that decreasing units keeps functionality."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    amount = len(unit_ids)
    expected = init_units_count - amount

    # scale down
    logger.info(f"Removing units {unit_ids}")
    await ops_test.model.applications[APP_NAME].destroy_unit(
        *[f"{APP_NAME}/{cnt}" for cnt in unit_ids]
    )

    logger.info(f"Waiting for units {unit_ids} to be removed safely")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        wait_for_exact_units=expected,
        timeout=1000,
        idle_period=30,
    )

    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == expected

    logger.info("Checking the functionality of the remaining units")
    if expected > 0:
        assert await access_all_dashboards(ops_test, pytest.relation.id, https)


##############################################################################
# Tests
##############################################################################


@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_http(ops_test: OpsTest) -> None:
    """Testing that newly added units are functional."""
    await scale_up(ops_test, amount=len(HTTP_UNITS) - 1)


@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_http(ops_test: OpsTest) -> None:
    """Testing that decreasing units keeps functionality."""
    await scale_down(ops_test, unit_ids=HTTP_UNITS[1:])


@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_http(ops_test: OpsTest) -> None:
    """Testing that scaling down to 0 units is possible."""
    await scale_down(ops_test, unit_ids=HTTP_UNITS[0:1])


##############################################################################


@pytest.mark.abort_on_fail
async def test_tls_on(ops_test: OpsTest) -> None:
    """Not a real test, but only switching on TLS"""
    await ops_test.model.applications[APP_NAME].add_unit(count=1)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, wait_for_exact_units=1
    )

    # Relate Dashboards to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=3000, idle_period=30
    )

    # Note: due to https://bugs.launchpad.net/juju/+bug/2064876 we have a workaround for >1 units
    # However, a single unit would only pick up config changes on 'update-status'
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=3000)

    assert await access_all_dashboards(ops_test, get_relation(ops_test).id, https=True)


##############################################################################


@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_https(ops_test: OpsTest) -> None:
    """Testing that newly added units are functional with TLS on."""
    await scale_up(ops_test, amount=len(HTTPS_UNITS) - 1, https=True)


@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_https(ops_test: OpsTest) -> None:
    """Testing that decreasing units keeps functionality with TLS on."""
    await scale_down(ops_test, unit_ids=HTTPS_UNITS[1:], https=True)


@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_https(ops_test: OpsTest) -> None:
    """Testing that scaling down to 0 units is possible."""
    await scale_down(ops_test, unit_ids=HTTPS_UNITS[0:1], https=True)


@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_from_zero_https(ops_test: OpsTest) -> None:
    """Testing that scaling up from zero units using TLS works."""
    await scale_up(ops_test, amount=len(HTTPS_UNITS), https=True)
