#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import re
from pathlib import Path

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    CONFIG_OPTS,
    DASHBOARD_QUERY_PARAMS,
    TLS_CERTIFICATES_APP_NAME,
    TLS_STABLE_CHANNEL,
    access_all_dashboards,
    access_all_prometheus_exporters,
    all_dashboards_unavailable,
    check_full_status,
    client_run_all_dashboards_request,
    client_run_db_request,
    count_lines_with,
    destroy_cluster,
    get_address,
    get_file_contents,
    get_relations,
    get_unit_relation_data,
)

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
COS_AGENT_APP_NAME = "grafana-agent"
COS_AGENT_RELATION_NAME = "cos-agent"
DB_CLIENT_APP_NAME = "application"

NUM_UNITS_APP = 3
NUM_UNITS_DB = 3


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(
    ops_test: OpsTest, charm: str, application_charm: str, series: str
):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    await ops_test.model.deploy(
        charm, application_name=APP_NAME, num_units=NUM_UNITS_APP, series=series
    )
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    config = {"ca-common-name": "CN_CA"}
    await ops_test.model.deploy(COS_AGENT_APP_NAME, series=series)
    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/edge",
        num_units=NUM_UNITS_DB,
        config=CONFIG_OPTS,
    )
    await ops_test.model.deploy(
        TLS_CERTIFICATES_APP_NAME, channel=TLS_STABLE_CHANNEL, config=config
    )
    await ops_test.model.deploy(application_charm, application_name=DB_CLIENT_APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # integrate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME],
        status="active",
        timeout=1000,
    )

    async with ops_test.fast_forward():
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == NUM_UNITS_APP
        )
        await ops_test.model.wait_for_idle(apps=[APP_NAME], timeout=1000, idle_period=30)

    assert ops_test.model.applications[APP_NAME].status == "blocked"

    # Relate both Dashboards and the Client to Opensearch
    await ops_test.model.integrate(OPENSEARCH_APP_NAME, APP_NAME)
    await ops_test.model.integrate(DB_CLIENT_APP_NAME, OPENSEARCH_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, DB_CLIENT_APP_NAME, OPENSEARCH_APP_NAME],
        status="active",
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_dashboard_access(ops_test: OpsTest):
    """Test HTTP access to each dashboard unit."""

    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]
    assert await access_all_dashboards(ops_test, opensearch_relation.id)
    assert await access_all_prometheus_exporters(ops_test)


@pytest.mark.abort_on_fail
async def test_dashboard_access_https(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    # integrate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]

    assert await access_all_dashboards(ops_test, opensearch_relation.id, https=True)
    assert await access_all_prometheus_exporters(ops_test)

    # Breaking the relation shouldn't impact service availability
    # A new certificate is requested when the relation is joined again
    await ops_test.juju("remove-relation", APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    # Event thought the TLS connection is not there, we do NOT switch back to HTTP
    with pytest.raises(requests.exceptions.ConnectionError):
        await access_all_dashboards(ops_test, opensearch_relation.id)

    # Instead, HTTPS works uninterrupted
    assert await access_all_dashboards(ops_test, opensearch_relation.id, https=True)

    server_cert = (
        "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/certificates/server.pem"
    )
    unit = ops_test.model.applications[APP_NAME].units[0]
    host_cert = get_file_contents(ops_test, unit, server_cert)

    # Restore relation for further tests
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    new_host_cert = get_file_contents(ops_test, unit, server_cert)
    assert host_cert != new_host_cert


@pytest.mark.abort_on_fail
async def test_dashboard_client_data_access_https(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    client_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME, DB_CLIENT_APP_NAME)[0]

    # Loading data to Opensearch
    dicts = [
        {"index": {"_index": "albums", "_id": "2"}},
        {"artist": "Herbie Hancock", "genre": ["Jazz"], "title": "Head Hunters"},
        {"index": {"_index": "albums", "_id": "3"}},
        {"artist": "Lydian Collective", "genre": ["Jazz"], "title": "Adventure"},
        {"index": {"_index": "albums", "_id": "4"}},
        {
            "artist": "Liquid Tension Experiment",
            "genre": ["Prog", "Metal"],
            "title": "Liquid Tension Experiment 2",
        },
    ]
    data_dicts = [d for d in dicts if "index" not in d.keys()]

    payload = "\n".join([json.dumps(d) for d in dicts]) + "\n"

    unit_name = ops_test.model.applications[DB_CLIENT_APP_NAME].units[0].name
    await client_run_db_request(
        ops_test,
        unit_name,
        client_relation,
        "POST",
        "/_bulk?refresh=true",
        re.escape(payload),
    )

    # # Checking if data got to the DB indeed
    read_db_data = await client_run_db_request(
        ops_test, unit_name, client_relation, "GET", "/albums/_search"
    )
    results = json.loads(read_db_data["results"])
    logging.info(f"Loaded into the database: {results}")

    # Same amount and content of data as uploaded
    assert len(data_dicts) == len(results["hits"]["hits"])
    assert all([hit["_source"] in data_dicts for hit in results["hits"]["hits"]])

    result = await client_run_all_dashboards_request(
        ops_test,
        unit_name,
        client_relation,
        "POST",
        "/internal/search/opensearch-with-long-numerals",
        json.dumps(DASHBOARD_QUERY_PARAMS),
        https=True,
    )

    # Each dashboard query reports the same result as the uploaded data
    assert all(len(data_dicts) == len(res["hits"]["hits"]) for res in result)
    assert all([hit["_source"] in data_dicts for res in result for hit in res["hits"]["hits"]])


@pytest.mark.abort_on_fail
async def test_cos_relations(ops_test: OpsTest):
    await ops_test.model.integrate(COS_AGENT_APP_NAME, APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", timeout=1000, idle_period=30
    )
    await ops_test.model.wait_for_idle(
        apps=[COS_AGENT_APP_NAME], status="blocked", timeout=1000, idle_period=30
    )

    expected_results = [
        {
            "metrics_path": "/metrics",
            "scheme": "http",
        }
    ]
    agent_unit = ops_test.model.applications[COS_AGENT_APP_NAME].units[0]
    for unit in ops_test.model.applications[APP_NAME].units:
        unit_ip = await get_address(ops_test, unit.name)
        relation_data = get_unit_relation_data(
            ops_test.model.name, agent_unit.name, COS_AGENT_RELATION_NAME
        )
        expected_results[0]["static_configs"] = [{"targets": [f"{unit_ip}:9684"]}]
        unit_data = relation_data[unit.name]
        unit_cos_config = json.loads(unit_data["data"]["config"])
        for key, value in expected_results[0].items():
            assert unit_cos_config["metrics_scrape_jobs"][0][key] == value


@pytest.mark.abort_on_fail
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


@pytest.mark.abort_on_fail
async def test_dashboard_status_changes(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""

    logger.info("Breaking opensearch connection")
    await ops_test.juju("remove-relation", "opensearch", "opensearch-dashboards")
    await ops_test.model.wait_for_idle(apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000)

    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked")

    assert await check_full_status(
        ops_test, status="blocked", status_msg="Opensearch connection is missing"
    )

    logger.info("Checking if Dashboards have become unavailable")
    assert all_dashboards_unavailable(ops_test, https=True)

    logger.info("Restoring Opensearch connection")
    await ops_test.model.integrate(APP_NAME, OPENSEARCH_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, OPENSEARCH_APP_NAME], status="active", timeout=1000
    )
    assert ops_test.model.applications[APP_NAME].status == "active"
    assert all(
        unit.workload_status == "active" for unit in ops_test.model.applications[APP_NAME].units
    )

    logger.info("Checking if Dashboards is available again")
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]
    assert await access_all_dashboards(ops_test, opensearch_relation.id, https=True)

    logger.info("Removing an opensearch unit so Opensearch gets in a 'red' state")
    await ops_test.model.applications[APP_NAME].destroy_unit(
        ops_test.model.applications[OPENSEARCH_APP_NAME].units[1].name
    )
    await ops_test.model.applications[APP_NAME].destroy_unit(
        ops_test.model.applications[OPENSEARCH_APP_NAME].units[0].name
    )
    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked")

    assert await check_full_status(
        ops_test,
        status="blocked",
        status_msg="Opensearch service is (partially or fully) down",
    )


@pytest.mark.skip(reason="https://warthogs.atlassian.net/browse/DPE-5073")
async def test_restore_opensearch_restores_osd(ops_test: OpsTest):
    """This test shouldn't be separate but a native continuation of the previous one.

    Should be only split as long as it's not enabled.
    """

    logger.info("Destroying and restoring the Opensearch cluster")
    await destroy_cluster(ops_test, app=OPENSEARCH_APP_NAME)

    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/edge",
        num_units=NUM_UNITS_DB,
        config=CONFIG_OPTS,
    )

    await ops_test.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)
    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(apps=[OPENSEARCH_APP_NAME], status="blocked")

    await ops_test.model.integrate(APP_NAME, OPENSEARCH_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, OPENSEARCH_APP_NAME], status="active", timeout=1000
    )

    logger.info("Checking if Dashboards is available again")
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]
    assert await access_all_dashboards(ops_test, opensearch_relation.id, https=True)
