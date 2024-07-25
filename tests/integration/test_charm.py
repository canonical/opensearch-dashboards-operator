#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from time import sleep

import pytest
import yaml
from dateutil.parser import parse
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_RELATION_NAME = "opensearch-client"
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
COS_AGENT_APP_NAME = "grafana-agent"

NUM_UNITS_APP = 3
NUM_UNITS_DB = 2


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
@pytest.mark.usefixtures("application_charm_libs")
async def test_build_and_deploy(ops_test: OpsTest):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    config = {"ca-common-name": "CN_CA"}
    await asyncio.gather(
        ops_test.model.deploy(OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB),
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config),
    )

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # integrate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    async with ops_test.fast_forward():
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == NUM_UNITS_APP
        )
        await ops_test.model.wait_for_idle(apps=[APP_NAME], timeout=1000, idle_period=30)

    assert ops_test.model.applications[APP_NAME].status == "blocked"

    # Relate both Dashboards and the Client to Opensearch
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, OPENSEARCH_APP_NAME],
        status="active",
        timeout=1000,
    )


class Status:
    """Model class for status."""

    def __init__(self, kind: str, value: str, since: str, message: str | None = None):
        self.kind = kind
        self.value = value
        self.since = parse(since, ignoretz=True)
        self.message = message

    def __repr__(self):
        return f"Status ({self.kind}): {self.value}\n    since: {self.since}\n    status message: {self.message}\n"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_status_changes(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    # integrate it to OpenSearch to set up TLS.

    await ops_test.juju("remove-relation", "opensearch", "opensearch-dashboards")
    await ops_test.model.wait_for_idle(apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000)
    sleep(240)

    #
    # We would like to execute this
    #
    # async with ops_test.fast_forward("30s"):
    #     await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked")
    #
    await ops_test.model.wait_for_idle(apps=[APP_NAME])

    juju_status = json.loads(
        subprocess.check_output(
            f"juju status --model {ops_test.model.info.name} {APP_NAME} --format=json".split()
        )
    )["applications"][APP_NAME]

    print(juju_status)

    app_status = Status(
        kind="application-status",
        value=juju_status["application-status"]["current"],
        since=juju_status["application-status"]["since"],
        message=juju_status["application-status"].get("message"),
    )
    print(f"Application status information for application {APP_NAME}:\n {app_status}")

    for u_name, unit in juju_status["units"].items():
        workload_status = Status(
            kind="workload-status",
            value=unit["workload-status"]["current"],
            since=unit["workload-status"]["since"],
            message=unit["workload-status"].get("message"),
        )
        agent_status = Status(
            kind="agent-status",
            value=unit["juju-status"]["current"],
            since=unit["juju-status"]["since"],
        )
        print(f"Full status information for unit {u_name}:\n {workload_status} {agent_status}")

    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked")

    # This check should be executed but now it will fail
    #
    # assert ops_test.model.applications[APP_NAME].status == "blocked"
    # assert all(
    #     unit.workload_status == "blocked" for unit in ops_test.model.applications[APP_NAME].units
    # )
