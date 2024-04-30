#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import access_all_dashboards

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
TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"

HTTP_UNITS = [0, 1, 2]
HTTPS_UNITS = [3, 4, 5]


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.charm
async def test_build_and_deploy(ops_test: OpsTest):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=1)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(OPENSEARCH_APP_NAME, channel="2/edge", num_units=1)

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config)

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


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_http(ops_test: OpsTest) -> None:
    """Testing that newly added units are functional."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    amount = len(HTTP_UNITS) - 1

    # scale up
    await ops_test.model.applications[APP_NAME].add_unit(count=amount)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count + amount

    assert await access_all_dashboards(ops_test, pytest.relation.id)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_http(ops_test: OpsTest) -> None:
    """Testing that decreasing units keeps functionality."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    amount = len(HTTP_UNITS[1:])

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(
        *[f"{APP_NAME}/{cnt}" for cnt in HTTP_UNITS[1:]]
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - amount

    assert await access_all_dashboards(ops_test, pytest.relation.id)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_http(ops_test: OpsTest) -> None:
    """Testing that scaling down to 0 units is possible."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    unit_id = HTTP_UNITS[0]

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(f"{APP_NAME}/{unit_id}")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, wait_for_exact_units=0
    )
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 1


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_https(ops_test: OpsTest) -> None:
    """Testing that new added are functional with TLS on."""
    await ops_test.model.applications[APP_NAME].add_unit(count=1)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    amount = len(HTTPS_UNITS[1:])

    # scale up
    await ops_test.model.applications[APP_NAME].add_unit(count=amount)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=1000,
        wait_for_at_least_units=len(ops_test.model.applications[APP_NAME].units),
    )

    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count + amount

    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_https(ops_test: OpsTest) -> None:
    """Testing that decreasing units keeps functionality with TLS on."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    amount = len(HTTPS_UNITS[:-1])

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(
        *[f"{APP_NAME}/{cnt}" for cnt in HTTPS_UNITS[:-1]]
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - amount

    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_https(ops_test: OpsTest) -> None:
    """Testing that scaling down to 0 units is possible."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)
    unit_id = HTTPS_UNITS[-1]

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(f"{APP_NAME}/{unit_id}")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, wait_for_exact_units=0
    )
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 1
