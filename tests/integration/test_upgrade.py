#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import subprocess
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from src.literals import MSG_INCOMPATIBLE_UPGRADE

from ..ha.continuous_writes import ContinuousWrites
from .helpers import (
    access_all_dashboards,
    check_full_status,
    get_app_relation_data,
    get_leader_unit,
    get_relations,
)

logger = logging.getLogger(__name__)


OPENSEARCH_CHARM_NAME = "opensearch"
OPENSEARCH_DASHBOARDS_CHARM_NAME = "opensearch-dashboards"
CHANNEL = "2/edge"

STARTING_VERSION = "2.14.0"


OPENSEARCH_VERSION_TO_REVISION = {
    STARTING_VERSION: 143,
    "2.15.0": 144,
    "2.16.0": 161,
}

VERSION_TO_REVISION = {
    STARTING_VERSION: 18,
    "2.15.0": 19,
    "2.16.0": 20,
}


FROM_VERSION_PREFIX = "from_v{}_to_local"

UPGRADE_INITIAL_VERSION = [
    (
        pytest.param(
            version,
            id=FROM_VERSION_PREFIX.format(version),
            marks=pytest.mark.group(FROM_VERSION_PREFIX.format(version)),
        )
    )
    for version in VERSION_TO_REVISION.keys()
]

charm = None


METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]

# FIXME: update this to 'stable' when `pre-upgrade-check` is released to 'stable'
CHANNEL = "edge"

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
OPENSEARCH_RELATION_NAME = "opensearch-client"
TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"

NUM_UNITS_APP = 3
NUM_UNITS_DB = 3


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.charm
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test: OpsTest):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    pytest.charm = await ops_test.build_charm(".")
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    await ops_test.modeGl.deploy(
        OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB, revision=161
    )
    await ops_test.model.deploy(pytest.charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)

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


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_in_place_upgrade_http(ops_test: OpsTest):
    leader_unit = get_leader_unit(ops_test)
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    # ensuring that the upgrade stack is correct
    relation_data = get_app_relation_data(
        model_full_name=ops_test.model_full_name, unit=f"{APP_NAME}/0", endpoint="upgrade"
    )

    assert "upgrade-stack" in relation_data

    assert set(json.loads(relation_data["upgrade-stack"])) == set(
        [int(unit.machine.id) for unit in ops_test.model.applications[APP_NAME].units]
    )

    await ops_test.model.applications[APP_NAME].refresh(path=pytest.charm)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=120
    )

    assert await access_all_dashboards(ops_test)


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_switch_tls_on(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.relate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_in_place_upgrade_https(ops_test: OpsTest):
    leader_unit = get_leader_unit(ops_test)
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    # ensuring that the upgrade stack is correct
    relation_data = get_app_relation_data(
        model_full_name=ops_test.model_full_name, unit=f"{APP_NAME}/0", endpoint="upgrade"
    )

    assert "upgrade-stack" in relation_data
    assert set(json.loads(relation_data["upgrade-stack"])) == set(
        [int(unit.machine.id) for unit in ops_test.model.applications[APP_NAME].units]
    )

    await ops_test.model.applications[APP_NAME].refresh(path=pytest.charm)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=120
    )

    assert await access_all_dashboards(ops_test, https=True)


#######################################################################
#
#  Auxiliary functions
#
#######################################################################


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
async def _build_env(ops_test: OpsTest, version: str) -> None:
    """Deploy OpenSearch cluster from a given revision."""
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    await ops_test.model.deploy(
        OPENSEARCH_CHARM_NAME,
        application_name=APP_NAME,
        num_units=3,
        channel=CHANNEL,
        revision=OPENSEARCH_VERSION_TO_REVISION[version],
    )

    # Deploy TLS Certificates operator.
    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config)

    # Relate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME, APP_NAME],
        status="active",
        timeout=1400,
        idle_period=50,
    )
    assert len(ops_test.model.applications[APP_NAME].units) == 3

    await ops_test.model.deploy(
        OPENSEARCH_DASHBOARDS_CHARM_NAME,
        application_name=APP_NAME,
        num_units=3,
        channel=CHANNEL,
        revision=VERSION_TO_REVISION[version],
    )


#######################################################################
#
#  Tests
#
#######################################################################


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group("happy_path_upgrade")
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_latest_from_channel(ops_test: OpsTest) -> None:
    """Deploy OpenSearch."""
    await _build_env(ops_test, STARTING_VERSION)


@pytest.mark.group("happy_path_upgrade")
@pytest.mark.abort_on_fail
async def test_upgrade_between_versions(
    ops_test: OpsTest, c_writes: ContinuousWrites, c_writes_runner
) -> None:
    """Test upgrade from upstream to currently locally built version."""
    for version, rev in VERSION_TO_REVISION.items():
        if version == STARTING_VERSION:
            # We're starting in this version
            continue

        logger.info(f"Upgrading to version {version}")

        leader_unit = get_leader_unit(ops_test)
        action = await leader_unit.run_action("pre-upgrade-check")
        await action.wait()
        assert action.status == "completed"

        async with ops_test.fast_forward():
            logger.info("Refresh the charm")
            # due to: https://github.com/juju/python-libjuju/issues/1057
            # application = ops_test.model.applications[APP_NAME]
            # await application.refresh(
            #     revision=rev,
            # )
            subprocess.check_output(
                f"juju refresh {OPENSEARCH_CHARM_NAME} --revision={rev}".split()
            )

            logger.info("Refresh is over, waiting for the charm to settle")

            await ops_test.model.wait_for_idle(
                apps=[OPENSEARCH_CHARM_NAME], status="active", timeout=1000, idle_period=120
            )
            logger.info("Opensearch upgrade finished")

            await ops_test.model.wait_for_idle(
                apps=[APP_NAME], status="blocked", timeout=1000, idle_period=120
            )

            assert await check_full_status(
                ops_test, status="blocked", status_msg=MSG_INCOMPATIBLE_UPGRADE
            )

            subprocess.check_output(
                f"juju refresh {OPENSEARCH_DASHBOARDS_CHARM_NAME} --revision={rev}".split()
            )

            logger.info("Refresh is over, waiting for the charm to settle")
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME], status="blocked", timeout=1000, idle_period=120
            )
            logger.info("Opensearch Dashboards upgrade finished")

            opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]
            assert await access_all_dashboards(ops_test, opensearch_relation.id)


# @pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
# @pytest.mark.group("happy_path_upgrade")
# @pytest.mark.abort_on_fail
# async def test_upgrade_to_local(
#     ops_test: OpsTest, c_writes: ContinuousWrites, c_writes_runner
# ) -> None:
#     """Test upgrade from usptream to currently locally built version."""
#     logger.info("Build charm locally")
#     charm = await ops_test.build_charm(".")
#     await assert_upgrade_to_local(ops_test, c_writes, charm)
#
#
# ##################################################################################
# #
# #  test scenarios from each version:
# #    Start with each version, moving to local and then rolling back mid-upgrade
# #    Once this test passes, the 2nd test will rerun the upgrade, this time to
# #    its end.
# #
# ##################################################################################
#
#
# @pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
# @pytest.mark.parametrize("version", UPGRADE_INITIAL_VERSION)
# @pytest.mark.abort_on_fail
# @pytest.mark.skip_if_deployed
# async def test_deploy_from_version(ops_test: OpsTest, version) -> None:
#     """Deploy OpenSearch."""
#     await _build_env(ops_test, version)
#
#
# @pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
# @pytest.mark.parametrize("version", UPGRADE_INITIAL_VERSION)
# @pytest.mark.abort_on_fail
# async def test_upgrade_rollback_from_local(
#     ops_test: OpsTest, c_writes: ContinuousWrites, c_writes_runner, version
# ) -> None:
#     """Test upgrade and rollback to each version available."""
#     app = (await app_name(ops_test)) or APP_NAME
#     units = await get_application_units(ops_test, app)
#     leader_id = [u.id for u in units if u.is_leader][0]
#
#     action = await run_action(
#         ops_test,
#         leader_id,
#         "pre-upgrade-check",
#         app=app,
#     )
#     assert action.status == "completed"
#
#     logger.info("Build charm locally")
#     global charm
#     if not charm:
#         charm = await ops_test.build_charm(".")
#
#     async with ops_test.fast_forward():
#         logger.info("Refresh the charm")
#         # due to: https://github.com/juju/python-libjuju/issues/1057
#         # application = ops_test.model.applications[APP_NAME]
#         # await application.refresh(
#         #     revision=new_rev,
#         # )
#         subprocess.check_output(f"juju refresh opensearch --path={charm}".split())
#
#         await wait_until(
#             ops_test,
#             apps=[app],
#             apps_statuses=["blocked"],
#             units_statuses=["active"],
#             wait_for_exact_units={
#                 APP_NAME: 3,
#             },
#             timeout=1400,
#             idle_period=IDLE_PERIOD,
#         )
#
#         logger.info(f"Rolling back to {version}")
#         # due to: https://github.com/juju/python-libjuju/issues/1057
#         # await application.refresh(
#         #     revision=rev,
#         # )
#
#         # Rollback operation
#         # We must first switch back to the upstream charm, then rollback to the original
#         # revision we were using.
#         subprocess.check_output(
#             f"""juju refresh opensearch
#                  --switch={OPENSEARCH_DASHBOARDS_CHARM_NAME}
#                  --channel={CHANNEL}""".split()
#         )
#
#         # Wait until we are set in an idle state and can rollback the revision.
#         await wait_until(
#             ops_test,
#             apps=[app],
#             apps_statuses=["blocked"],
#             units_statuses=["active"],
#             wait_for_exact_units={
#                 APP_NAME: 3,
#             },
#             timeout=1400,
#             idle_period=IDLE_PERIOD,
#         )
#
#         subprocess.check_output(
#             f"juju refresh opensearch --revision={VERSION_TO_REVISION[version]}".split()
#         )
#
#         await wait_until(
#             ops_test,
#             apps=[app],
#             apps_statuses=["active"],
#             units_statuses=["active"],
#             wait_for_exact_units={
#                 APP_NAME: 3,
#             },
#             timeout=1400,
#             idle_period=IDLE_PERIOD,
#         )
#
#
# @pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
# @pytest.mark.parametrize("version", UPGRADE_INITIAL_VERSION)
# @pytest.mark.abort_on_fail
# async def test_upgrade_from_version_to_local(
#     ops_test: OpsTest, c_writes: ContinuousWrites, c_writes_runner, version
# ) -> None:
#     """Test upgrade from usptream to currently locally built version."""
#     logger.info("Build charm locally")
#     global charm
#     if not charm:
#         charm = await ops_test.build_charm(".")
#     await assert_upgrade_to_local(ops_test, c_writes, charm)
