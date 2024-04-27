#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

# from .helpers import (
#     access_dashboard,
#     access_dashboard_https,
#     count_lines_with,
#     get_application_relation_data,
#     get_dashboard_ca_cert,
#     get_leader_id,
#     get_leader_name,
#     get_private_address,
#     get_secret_by_label,
#     get_user_password,
#     ping_servers,
#     set_opensearch_user_password,
#     set_password,
# )

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

NUM_UNITS_APP = 3
NUM_UNITS_DB = 2


def create_traefik_model():

    commands1 = [
        "sudo snap install microk8s --classic --channel=1.25-strict/stable",
        "sudo usermod -a -G snap_microk8s $USER",
    ]
    import pdb

    pdb.set_trace()
    output = subprocess.run(";".join(commands1), capture_output=True, shell=True)
    commands2 = [
        "sg snap_microk8s microk8s enable storage",
        "sg snap_microk8s microk8s enable dns",
        "sg snap_microk8s microk8s status --wait-ready",
        "sg snap_microk8s juju bootstrap microk8s k8s-traefik",
        # "sg snap_microk8s mkdir -p .local/share",
        # "juju add-model traefik",
    ]
    output2 = subprocess.run(";".join(commands2), capture_output=True, shell=True)
    commands2 = [
        "sudo microk8s enable storage",
        "sudo microk8s enable dns",
        "microk8s status --wait-ready",
        "juju bootstrap microk8s",
        "mkdir -p .local/share",
        "juju add-model traefik",
    ]


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.charm
async def test_deploy_active(ops_test: OpsTest):

    retval = create_traefik_model()

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # Pinning down opensearch revision to the last 2.10 one
    # NOTE: can't access 2/stable from the tests, only 'edge' available
    test_charm_path = "./tests/integration/opensearch-operator"
    opensearch_new_charm = await ops_test.build_charm(test_charm_path)
    await ops_test.model.deploy(
        opensearch_new_charm, application_name=OPENSEARCH_APP_NAME, num_units=NUM_UNITS_DB
    )

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

    assert access_all_dashboards()
