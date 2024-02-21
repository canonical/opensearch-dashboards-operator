#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    access_dashboard,
    access_dashboard_https,
    count_lines_with,
    get_application_relation_data,
    get_dashboard_ca_cert,
    get_private_address,
    get_secret_by_label,
    get_user_password,
    ping_servers,
    set_opensearch_user_password,
    set_password,
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
    opensearch_endpoint = await get_application_relation_data(
        ops_test, APP_NAME, "opensearch_client", "endpoints"
    )

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
@pytest.mark.password_rotation
async def test_deploy_active(ops_test: OpsTest):

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=3)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # Pinning down opensearch revision to the last 2.10 one
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    await ops_test.model.deploy(OPENSEARCH_CHARM, revision=43, channel="2/edge", num_units=1)

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
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == 3
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", timeout=1000, idle_period=30
        )

    assert ops_test.model.applications[APP_NAME].status == "active"

    pytest.relation = await ops_test.model.relate(OPENSEARCH_CHARM, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_CHARM, APP_NAME], status="active", timeout=1000
    )
    await recreate_opensearch_kibanaserver(ops_test)


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
    dashboard_credentials = await get_secret_by_label(
        ops_test, f"opensearch-client.{pytest.relation.id}.user.secret"
    )
    dashboard_password = dashboard_credentials["password"]

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Copying the Dashboard's CA cert locally to use it for SSL verification
    # We only get it once for pipeline efficiency, as it's the same on all units
    get_dashboard_ca_cert(ops_test.model.name, f"{APP_NAME}/0")

    for unit in ops_test.model.applications[APP_NAME].units:
        host = get_private_address(ops_test.model.name, unit.name)
        assert access_dashboard_https(host=host, password=dashboard_password)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_local_password_rotation(ops_test: OpsTest):
    """Test password rotation for local users -- in case we decide to have any."""
    user = "kibanaserver"
    password = await get_user_password(ops_test, user)

    leader = None
    for unit in ops_test.model.applications[APP_NAME].units:
        if await unit.is_leader_from_status():
            leader = unit.name
            break
    leader_num = leader.split("/")[-1]

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

        await ops_test.model.applications[APP_NAME].set_config({"log-level": "ERROR"})

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
    await ops_test.model.applications[APP_NAME].set_config({"log-level": "INFO"})

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=30
    )
