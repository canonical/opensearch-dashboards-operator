#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    access_dashboard,
    check_key,
    get_address,
    get_user_password,
    ping_servers,
    set_password,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.password_rotation
async def test_deploy_active(ops_test: OpsTest):
    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=1)

    async with ops_test.fast_forward():
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == 1
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", timeout=1000, idle_period=30
        )

    assert ops_test.model.applications[APP_NAME].status == "active"


# @pytest.mark.abort_on_fail
# @pytest.mark.log_level_change
# async def test_log_level_change(ops_test: OpsTest):
#
#     for unit in ops_test.model.applications[APP_NAME].units:
#         assert (
#             count_lines_with(
#                 ops_test.model_full_name,
#                 unit.name,
#                 "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
#                 "DEBUG",
#             )
#             == 0
#         )
#
#     await ops_test.model.applications[APP_NAME].set_config({"log-level": "DEBUG"})
#
#     await ops_test.model.wait_for_idle(
#         apps=[APP_NAME], status="active", timeout=1000, idle_period=30
#     )
#
#     for unit in ops_test.model.applications[APP_NAME].units:
#         assert (
#             count_lines_with(
#                 ops_test.model_full_name,
#                 unit.name,
#                 "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
#                 "DEBUG",
#             )
#             == 0
#         )
#
#     await ops_test.model.applications[APP_NAME].set_config({"log-level": "INFO"})
#
#     await ops_test.model.wait_for_idle(
#         apps=[APP_NAME], status="active", timeout=1000, idle_period=30
#     )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.password_rotation
async def test_password_rotation(ops_test: OpsTest):
    """Test password rotation action."""
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

    await asyncio.sleep(30)

    host = await get_address(ops_test, APP_NAME, leader_num)
    access_dashboard(host=host, username=user, password=new_password)

    # Check key in all units
    for unit in ops_test.model.applications[APP_NAME].units:
        host = await get_address(ops_test, APP_NAME, unit.name.split("/")[-1])
        check_key(host=host, password=new_password)
