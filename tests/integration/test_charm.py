#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import re
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    DASHBOARD_QUERY_PARAMS,
    access_all_dashboards,
    access_dashboard,
    client_run_all_dashboards_request,
    client_run_db_request,
    count_lines_with,
    get_address,
    get_leader_id,
    get_leader_name,
    get_private_address,
    get_relations,
    get_secret_by_label,
    get_unit_relation_data,
    get_user_password,
    set_password,
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
TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"
COS_AGENT_APP_NAME = "grafana-agent"
COS_AGENT_RELATION_NAME = "cos-agent"
DB_CLIENT_APP_NAME = "application"

NUM_UNITS_APP = 3
NUM_UNITS_DB = 2


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
@pytest.mark.usefixtures("application_charm_libs")
async def test_build_and_deploy(ops_test: OpsTest):
    """Deploying all charms required for the tests, and wait for their complete setup to be done."""

    charm = await ops_test.build_charm(".")
    application_charm_build = await ops_test.build_charm("tests/integration/application-charm")

    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=NUM_UNITS_APP)
    await ops_test.model.set_config(OPENSEARCH_CONFIG)
    # Pinning down opensearch revision to the last 2.10 one
    # NOTE: can't access 2/stable from the tests, only 'edge' available

    config = {"ca-common-name": "CN_CA"}
    await asyncio.gather(
        ops_test.model.deploy(COS_AGENT_APP_NAME, num_units=1),
        ops_test.model.deploy(OPENSEARCH_APP_NAME, channel="2/edge", num_units=NUM_UNITS_DB),
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=config),
        ops_test.model.deploy(application_charm_build, application_name=DB_CLIENT_APP_NAME),
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
    await ops_test.model.integrate(DB_CLIENT_APP_NAME, OPENSEARCH_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, DB_CLIENT_APP_NAME, OPENSEARCH_APP_NAME],
        status="active",
        timeout=1000,
    )
    await ops_test.model.wait_for_idle(apps=[COS_AGENT_APP_NAME], timeout=1000)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access(ops_test: OpsTest):
    """Test HTTP access to each dashboard unit."""

    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]

    dashboard_credentials = await get_secret_by_label(
        ops_test, f"opensearch-client.{opensearch_relation.id}.user.secret"
    )
    dashboard_password = dashboard_credentials["password"]

    for unit in ops_test.model.applications[APP_NAME].units:
        host = get_private_address(ops_test.model.name, unit.name)
        assert access_dashboard(host=host, username="kibanaserver", password=dashboard_password)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_dashboard_access_https(ops_test: OpsTest):
    """Test HTTPS access to each dashboard unit."""
    # integrate it to OpenSearch to set up TLS.
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]

    assert access_all_dashboards(ops_test, opensearch_relation, https=True)


@pytest.mark.group(1)
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
    opensearch_relation = get_relations(ops_test, OPENSEARCH_RELATION_NAME)[0]

    assert access_all_dashboards(ops_test, opensearch_relation, https=True)


@pytest.mark.group(1)
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
            "tls_config": {"ca": ""},
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
