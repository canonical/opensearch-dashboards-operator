#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

import pytest
from pytest_operator.plugin import OpsTest

from ..helpers import (
    APP_NAME,
    CONFIG_OPTS,
    OPENSEARCH_APP_NAME,
    SERIES,
    TLS_CERTIFICATES_APP_NAME,
    TLS_STABLE_CHANNEL,
    access_all_dashboards,
    access_all_prometheus_exporters,
    for_machines,
    get_relation,
)

logger = logging.getLogger(__name__)


DEFAULT_NUM_UNITS = 3


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test: OpsTest, lxd_spaces) -> None:
    """Build and deploy OpenSearch Dashboards.

    For this test, we will create a machine in multiple spaces and inject
    the a record into /etc/hosts, as follows:
        127.0.1.1  <fqdn>

    More information: gh:canonical/opensearch-dashboards-operator#121
    """
    osd_charm = await ops_test.build_charm(".")

    for _ in range(DEFAULT_NUM_UNITS):
        subprocess.check_output(
            [
                "juju",
                "add-machine",
                f"--model={ops_test.model.name}",
                "--constraints=spaces=alpha,cluster,backup,client",
                f"--series={SERIES}",
            ]
        )

    await for_machines(ops_test, machines=list(range(DEFAULT_NUM_UNITS)))

    # Now, we should SSH to each machine and inject the record into /etc/hosts
    machine_ip = "127.0.1.1"
    for machine_id in range(DEFAULT_NUM_UNITS):
        subprocess.check_output(
            [
                "juju",
                "ssh",
                f"--model={ops_test.model.name}",
                str(machine_id),
                "--",
                "sudo",
                "sed",
                "-i",
                f'"1i\\{machine_ip} $(hostname -f)"',
                "/etc/hosts",
            ]
        )

    await ops_test.model.deploy(
        osd_charm,
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        constraints="spaces=alpha,client,cluster,backup",
        bind={"": "cluster"},
        to=[str(i) for i in range(DEFAULT_NUM_UNITS)],
    )
    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(
        TLS_CERTIFICATES_APP_NAME,
        channel=TLS_STABLE_CHANNEL,
        constraints="spaces=alpha,client,cluster,backup",
        bind={"": "cluster"},
        config=config,
    )
    await ops_test.model.deploy(
        "opensearch",
        channel="2/edge",
        constraints="spaces=alpha,client,cluster,backup",
        bind={"": "cluster"},
        num_units=3,
        config=CONFIG_OPTS,
    )
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME, APP_NAME, OPENSEARCH_APP_NAME],
        status="active",
        timeout=3000,
    )
    assert len(ops_test.model.applications[APP_NAME].units) == DEFAULT_NUM_UNITS


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access_http(ops_test: OpsTest):
    """Test HTTP access to each dashboard unit."""
    assert await access_all_dashboards(ops_test, get_relation(ops_test).id)
    assert await access_all_prometheus_exporters(ops_test)


##############################################################################


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_tls_on(ops_test: OpsTest) -> None:
    """Not a real test, but only switching on TLS"""
    # Relate Dashboards to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=3000, idle_period=30
    )


##############################################################################


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access_https(ops_test: OpsTest):
    """Test HTTP access to each dashboard unit."""
    assert await access_all_dashboards(ops_test, get_relation(ops_test).id, https=True)
    assert await access_all_prometheus_exporters(ops_test)
