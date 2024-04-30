#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    access_all_dashboards,
    access_dashboard,
    count_lines_with,
    get_leader_id,
    get_leader_name,
    get_private_address,
    get_secret_by_label,
    get_user_password,
    ping_servers,
    set_password,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
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

NUM_UNITS_APP = 3
NUM_UNITS_DB = 2


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.charm
async def test_deploy_active(ops_test: OpsTest):

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # Pinning down opensearch revision to the last 2.10 one
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB)

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    async with ops_test.fast_forward():
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == NUM_UNITS_APP
        )
        await ops_test.model.wait_for_idle(apps=[APP_NAME], timeout=1000, idle_period=30)

    assert ops_test.model.applications[APP_NAME].status == "blocked"

    pytest.relation = await ops_test.model.relate(OPENSEARCH_APP_NAME, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, APP_NAME], status="active", timeout=1000
    )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access(ops_test: OpsTest):
    """Test HTTP access to each dashboard unit."""

    dashboard_credentials = await get_secret_by_label(
        ops_test, f"opensearch-client.{pytest.relation.id}.user.secret"
    )
    dashboard_password = dashboard_credentials["password"]

    for unit in ops_test.model.applications[APP_NAME].units:
        host = get_private_address(ops_test.model.name, unit.name)
        assert access_dashboard(host=host, username="kibanaserver", password=dashboard_password)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access_https(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    assert access_all_dashboards(ops_test, pytest.relation, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_password_rotation(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    db_leader_name = await get_leader_name(ops_test, OPENSEARCH_APP_NAME)
    db_leader_unit = ops_test.model.units.get(db_leader_name)
    user = "kibanaserver"

    action = await db_leader_unit.run_action("set-password", **{"username": user})
    await action.wait()

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, OPENSEARCH_APP_NAME], status="active", timeout=1000, idle_period=30
    )

    assert access_all_dashboards(ops_test, pytest.relation, https=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_local_password_rotation(ops_test: OpsTest):
    """Test password rotation for local users -- in case we decide to have any."""
    user = "monitor"
    password = await get_user_password(ops_test, user)
    assert len(password) == 32

    leader_num = await get_leader_id(ops_test)

    # Change both passwords
    result = await set_password(ops_test, username=user, num_unit=leader_num)
    assert f"{user}-password" in result.keys()

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=30
    )
    assert ops_test.model.applications[APP_NAME].status == "active"
    assert ping_servers(ops_test)

    new_password = await get_user_password(ops_test, user)

    assert password != new_password
    assert len(password) == 32


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.log_level_change
async def test_log_level_change(ops_test: OpsTest):

    for unit in ops_test.model.applications[APP_NAME].units:
        assert count_lines_with(
            ops_test.model_full_name,
            unit.name,
            "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
            "debug",
        )

        await ops_test.model.applications[APP_NAME].set_config({"log_level": "ERROR"})

        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", timeout=1000, idle_period=30
        )

        debug_lines = count_lines_with(
            ops_test.model_full_name,
            unit.name,
            "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
            "debug",
        )

        assert (
            count_lines_with(
                ops_test.model_full_name,
                unit.name,
                "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
                "debug",
            )
            == debug_lines
        )

    # Reset default loglevel
    await ops_test.model.applications[APP_NAME].set_config({"log_level": "INFO"})

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=30
    )
