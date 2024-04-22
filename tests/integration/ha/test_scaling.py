#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    access_all_dashboards,
    get_application_relation_data,
    get_secret_by_label,
    set_opensearch_user_password,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_CHARM = "opensearch"
OPENSEARCH_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    "update-status-hook-interval": "1h",
    "cloudinit-userdata": """postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    """,
}
TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"


async def recreate_opensearch_kibanaserver(ops_test: OpsTest):
    """Temporary helper function."""
    #
    # THIS HAS TO CHANGE AS https://warthogs.atlassian.net/browse/DPE-2944 is processed
    #
    # "Total Hack"
    # Currently the 'kibanaserver' user is deleted on opensearch
    # We are "re-adding" it so we could use it for the opensearch connection
    # We are "re-adding" it using the password shared on the relation for the opensearch-client_<id> user
    # that's currently used by the charm
    #
    # To make it EVEN worse: we set the opensearch charm update period to 1h,
    # since on each status update opensearch is deleting all "unexpected" users :sweat_smile:
    #
    opensearch_endpoints = await get_application_relation_data(
        ops_test, APP_NAME, "opensearch_client", "endpoints"
    )
    opensearch_endpoint = opensearch_endpoints.split(",")[0]

    unit_name = f"{OPENSEARCH_CHARM}/0"
    action = await ops_test.model.units.get(unit_name).run_action("get-password")
    await action.wait()
    opensearch_admin_password = action.results.get("password")

    dashboard_credentials = await get_secret_by_label(
        ops_test, f"opensearch-client.{pytest.relation.id}.user.secret"
    )
    dashboard_password = dashboard_credentials["password"]
    set_opensearch_user_password(
        opensearch_endpoint, opensearch_admin_password, dashboard_password
    )

    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_CHARM, APP_NAME], status="active", timeout=1000
    )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.charm
async def test_build_and_deploy(ops_test: OpsTest):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=1)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # Pinning down opensearch revision to the last 2.10 one
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(OPENSEARCH_CHARM, channel="2/edge", num_units=1)

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(OPENSEARCH_CHARM, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_CHARM, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], wait_for_exact_units=1, status="active", timeout=1000, idle_period=30
        )

    assert ops_test.model.applications[APP_NAME].status == "active"

    pytest.relation = await ops_test.model.relate(OPENSEARCH_CHARM, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_CHARM, APP_NAME], status="active", timeout=1000
    )
    await recreate_opensearch_kibanaserver(ops_test)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_http(ops_test: OpsTest) -> None:
    """Tests that new added are functional."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale up
    await ops_test.model.applications[APP_NAME].add_unit(count=2)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count + 2

    assert await access_all_dashboards(ops_test, pytest.relation.id)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_http(ops_test: OpsTest) -> None:
    """Tests that decreasing units keeps functionality."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(
        *[f"{APP_NAME}/{init_units_count-cnt}" for cnt in range(1, 3)]
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 2

    assert await access_all_dashboards(ops_test, pytest.relation.id)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_http(ops_test: OpsTest) -> None:
    """Tests that decreasing units keeps functionality."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(f"{APP_NAME}/0")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, wait_for_exact_units=0
    )
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 1


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_up_https(ops_test: OpsTest) -> None:
    """Tests that new added are functional with TLS on."""
    await ops_test.model.applications[APP_NAME].add_unit(count=1)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale up
    await ops_test.model.applications[APP_NAME].add_unit(count=2)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count + 2

    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_https(ops_test: OpsTest) -> None:
    """Tests that decreasing units keeps functionality with TLS on."""

    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(
        *[f"{APP_NAME}/{init_units_count-cnt}" for cnt in range(3, 6)]
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 2

    assert await access_all_dashboards(ops_test, pytest.relation.id, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_horizontal_scale_down_to_zero_https(ops_test: OpsTest) -> None:
    """Tests that decreasing units keeps functionality."""
    init_units_count = len(ops_test.model.applications[APP_NAME].units)

    # scale down
    await ops_test.model.applications[APP_NAME].destroy_unit(f"{APP_NAME}/5")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, wait_for_exact_units=0
    )
    num_units = len(ops_test.model.applications[APP_NAME].units)
    assert num_units == init_units_count - 1
