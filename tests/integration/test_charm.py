#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import json
import logging
import re
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .conftest import Flags
from .helpers import (
    CONFIG_OPTS,
    DASHBOARD_QUERY_PARAMS,
    DUMMY_CHARM,
    OPENSEARCH_APP_NAME,
    TLS_CERTIFICATES_APP_NAME,
    TRAEFIK_APP_NAME,
    access_all_dashboards,
    access_all_prometheus_exporters,
    all_dashboards_unavailable,
    check_full_status,
    client_run_all_dashboards_request,
    client_run_db_request,
    count_lines_with,
    deploy_base,
    destroy_cluster,
    get_address,
    get_file_contents,
    get_relations,
    get_unit_relation_data,
    is_https_enabled,
    wait_for_dashboard_idle,
    wait_for_ingress_blocked,
)

logger = logging.getLogger(__name__)

METADATA_K8s = yaml.safe_load(Path("./kubernetes/metadata.yaml").read_text())
METADATA_VM = yaml.safe_load(Path("./machine/metadata.yaml").read_text())
PROMETHEUS_APP = "prometheus-k8s"
LOKI_APP = "loki-k8s"
GRAFANA_APP = "grafana-k8s"
COS_PORT = "9684"
OPENSEARCH_RELATION_NAME = "opensearch-client"
COS_AGENT_APP_NAME = "grafana-agent"
COS_CHANNEL = "1/stable"
COS_AGENT_RELATION_NAME = "cos-agent"
DB_CLIENT_APP_NAME = "application"

NUM_UNITS_APP = 3
NUM_UNITS_DB = 3


@pytest.mark.abort_on_fail
async def test_build_and_deploy(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    charmvm: str,
    charmk8s: str,
    application_charm: str,
    dashboard_tester_charm: str,
    charm_base: str,
    substrate: str,
    test_flags: Flags,
):
    """Deploying all charms required for the tests, and wait for complete setup."""
    tls = test_flags.test_tls
    traefik = test_flags.traefik
    transfer_traefik_ca = test_flags.transfer_traefik_ca
    charm = charmvm if substrate == "vm" else charmk8s
    app_name = await deploy_base(
        ops_test_vm,
        ops_test,
        charm,
        charm_base,
        substrate,
        num_units_app=NUM_UNITS_APP,
        num_units_db=NUM_UNITS_DB,
    )

    await ops_test_vm.model.deploy(application_charm, application_name=DB_CLIENT_APP_NAME)
    await ops_test_vm.model.integrate(DB_CLIENT_APP_NAME, OPENSEARCH_APP_NAME)

    if substrate == "vm":
        # Base does not work with grafana-agent charm so continuing using series
        series = "jammy" if charm_base == "ubuntu@22.04" else "noble"
        await ops_test_vm.model.deploy(COS_AGENT_APP_NAME, channel=COS_CHANNEL, series=series)
    else:
        for app in [PROMETHEUS_APP, LOKI_APP, GRAFANA_APP]:
            await ops_test.model.deploy(app, application_name=app, channel="2/stable", trust=True)
        await ops_test_vm.model.create_offer(
            endpoint=f"{TLS_CERTIFICATES_APP_NAME}:certificates,send-ca-cert",
            offer_name="self-signed-certificates",
        )
        await ops_test.model.consume(f"admin/{ops_test_vm.model.name}.{TLS_CERTIFICATES_APP_NAME}")

    if substrate == "k8s":
        await wait_for_ingress_blocked(ops_test, app_name, timeout=1000)
    else:
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

    await ops_test_vm.model.wait_for_idle(apps=[DB_CLIENT_APP_NAME], status="active", timeout=1000)

    if traefik:
        await ops_test.model.deploy(TRAEFIK_APP_NAME, channel="latest/stable", trust=True)
        await ops_test.model.wait_for_idle(apps=[TRAEFIK_APP_NAME], status="active", timeout=1000)
        await ops_test.model.integrate(app_name, TRAEFIK_APP_NAME)
        await ops_test.model.wait_for_idle(
            apps=[app_name, TRAEFIK_APP_NAME], status="active", timeout=1000
        )
    if transfer_traefik_ca:
        await ops_test.model.integrate(
            f"{TLS_CERTIFICATES_APP_NAME}:send-ca-cert", TRAEFIK_APP_NAME
        )
        await ops_test.model.wait_for_idle(
            apps=[app_name, TRAEFIK_APP_NAME], status="active", timeout=1000
        )
    if tls:
        await ops_test.model.integrate(app_name, TLS_CERTIFICATES_APP_NAME)
        if not transfer_traefik_ca and traefik:
            await ops_test.model.integrate(
                TRAEFIK_APP_NAME, f"{TLS_CERTIFICATES_APP_NAME}:certificates"
            )
            await ops_test.model.wait_for_idle(
                apps=[app_name, TRAEFIK_APP_NAME], status="active", timeout=1000
            )
        elif not substrate == "k8s" or traefik:
            await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
        else:
            await ops_test.model.deploy(dashboard_tester_charm, application_name=DUMMY_CHARM)
            await wait_for_ingress_blocked(ops_test, app_name, timeout=1000)


@pytest.mark.abort_on_fail
async def test_dashboard_access(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    """Test HTTP/HTTPS access based on the group configuration."""
    tls = test_flags.test_tls
    https_enabled = is_https_enabled(test_flags)

    assert await access_all_dashboards(ops_test_vm, ops_test, https=https_enabled, verify=tls)
    assert await access_all_prometheus_exporters(ops_test, substrate)


@pytest.mark.abort_on_fail
async def test_dashboard_tls_lifecycle(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    """Test HTTPS relation lifecycle (breaking and restoring)."""
    APP_NAME = METADATA_VM["name"] if substrate == "vm" else METADATA_K8s["name"]
    tls = test_flags.test_tls
    traefik = test_flags.traefik
    transfer_traefik_ca = test_flags.transfer_traefik_ca

    if not tls:
        pytest.skip("Skipping TLS lifecycle test as TLS is disabled in this matrix run.")

    server_cert = (
        "/etc/opensearch-dashboards/certificates/server.pem"
        if substrate == "k8s"
        else "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/certificates/server.pem"
    )

    unit = ops_test.model.applications[APP_NAME].units[0]
    host_cert = get_file_contents(ops_test.model.name, unit.name, server_cert)

    # Breaking the relation shouldn't impact service availability
    # A new certificate is requested when the relation is joined again
    await ops_test.juju("remove-relation", APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test_vm.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000
    )

    await wait_for_dashboard_idle(ops_test, traefik)
    # TLS Broken on relation removal; we check the connection on HTTP (https=False)

    # If traefik enabled it's related to TLS. Breaking TLS relation breaks the traefik charm, so we do not do that
    https = not transfer_traefik_ca and traefik and tls
    assert await access_all_dashboards(ops_test_vm, ops_test, https=https, verify=tls)

    # Restore relation for further tests
    await ops_test.model.integrate(APP_NAME, TLS_CERTIFICATES_APP_NAME)
    await ops_test_vm.model.wait_for_idle(
        apps=[TLS_CERTIFICATES_APP_NAME], status="active", timeout=1000, idle_period=20
    )
    await wait_for_dashboard_idle(ops_test, traefik)
    new_host_cert = get_file_contents(ops_test.model.name, unit.name, server_cert)
    assert host_cert != new_host_cert

    # Verify HTTPS is restored
    assert await access_all_dashboards(
        ops_test_vm,
        ops_test,
        https=is_https_enabled(test_flags),
        verify=tls,
    )


@pytest.mark.abort_on_fail
async def test_dashboard_client_data_access(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    """Test API access to each dashboard unit."""
    client_relation = get_relations(ops_test_vm, OPENSEARCH_RELATION_NAME, DB_CLIENT_APP_NAME)[0]

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

    unit_name = ops_test_vm.model.applications[DB_CLIENT_APP_NAME].units[0].name
    await client_run_db_request(
        ops_test_vm,
        unit_name,
        client_relation,
        "POST",
        "/_bulk?refresh=true",
        re.escape(payload),
    )

    # Checking if data got to the DB indeed
    read_db_data = await client_run_db_request(
        ops_test_vm, unit_name, client_relation, "GET", "/albums/_search"
    )
    results = json.loads(read_db_data["results"])
    logging.info(f"Loaded into the database: {results}")

    # Same amount and content of data as uploaded
    assert len(data_dicts) == len(results["hits"]["hits"])
    assert all([hit["_source"] in data_dicts for hit in results["hits"]["hits"]])

    result = await client_run_all_dashboards_request(
        ops_test_vm,
        ops_test,
        unit_name,
        client_relation,
        "POST",
        "/internal/search/opensearch-with-long-numerals",
        json.dumps(DASHBOARD_QUERY_PARAMS),
        https=is_https_enabled(test_flags),
    )

    # Each dashboard query reports the same result as the uploaded data
    assert all(len(data_dicts) == len(res["hits"]["hits"]) for res in result)
    assert all([hit["_source"] in data_dicts for res in result for hit in res["hits"]["hits"]])


@pytest.mark.abort_on_fail
async def test_cos_relations(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    APP_NAME = METADATA_VM["name"] if substrate == "vm" else METADATA_K8s["name"]
    traefik = test_flags.traefik
    if substrate == "k8s":
        await ops_test.model.integrate(f"{APP_NAME}:metrics-endpoint", PROMETHEUS_APP)
        await ops_test.model.integrate(f"{APP_NAME}:logging", LOKI_APP)
        await ops_test.model.integrate(f"{APP_NAME}:grafana-dashboard", GRAFANA_APP)

        await ops_test.model.wait_for_idle(
            apps=[PROMETHEUS_APP, LOKI_APP, GRAFANA_APP],
            status="active",
            timeout=1000,
            idle_period=30,
        )

        if traefik:
            await ops_test.model.wait_for_idle(
                apps=[PROMETHEUS_APP, LOKI_APP, GRAFANA_APP],
                status="active",
                timeout=1000,
                idle_period=30,
            )
        else:
            await wait_for_ingress_blocked(ops_test, APP_NAME, timeout=1000, idle_period=30)

        expected_results = {
            "metrics_path": "/metrics",
            "static_configs": [{"targets": [f"*:{COS_PORT}"]}],
            "scheme": "http",
        }

        prom_unit = ops_test.model.applications[PROMETHEUS_APP].units[0]

        rc, stdout, stderr = await ops_test.juju("show-unit", prom_unit.name, "--format=yaml")
        assert rc == 0, f"Failed to get unit data: {stderr}"

        unit_data = yaml.safe_load(stdout)[prom_unit.name]

        metrics_relation = None
        for relation in unit_data.get("relation-info", []):
            related_units = relation.get("related-units", {})
            if any(unit.startswith(f"{APP_NAME}/") for unit in related_units.keys()):
                metrics_relation = relation
                break

        assert metrics_relation is not None, f"Could not find relation data for {APP_NAME}"

        app_databag = metrics_relation.get("application-data", {})
        published_jobs = json.loads(app_databag.get("scrape_jobs", "[]"))

        assert len(published_jobs) > 0, "No scrape jobs were published to the relation."

        unit_cos_config = published_jobs[0]
        for key, value in expected_results.items():
            assert unit_cos_config[key] == value

    else:
        await ops_test_vm.model.integrate(COS_AGENT_APP_NAME, APP_NAME)
        await ops_test_vm.model.wait_for_idle(
            apps=[APP_NAME], status="active", timeout=1000, idle_period=30
        )
        await ops_test_vm.model.wait_for_idle(
            apps=[COS_AGENT_APP_NAME], status="blocked", timeout=1000, idle_period=30
        )

        expected_results = [
            {
                "metrics_path": "/metrics",
                "scheme": "http",
            }
        ]
        agent_unit = ops_test_vm.model.applications[COS_AGENT_APP_NAME].units[0]
        for unit in ops_test_vm.model.applications[APP_NAME].units:
            unit_ip = await get_address(ops_test_vm, unit.name, APP_NAME, substrate)
            relation_data = get_unit_relation_data(
                ops_test_vm.model.name, agent_unit.name, COS_AGENT_RELATION_NAME
            )
            expected_results[0]["static_configs"] = [{"targets": [f"{unit_ip}:9684"]}]
            unit_data = relation_data[unit.name]
            unit_cos_config = json.loads(unit_data["data"]["config"])
            for key, value in expected_results[0].items():
                assert unit_cos_config["metrics_scrape_jobs"][0][key] == value


@pytest.mark.abort_on_fail
async def test_log_level_change(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    APP_NAME = METADATA_VM["name"] if substrate == "vm" else METADATA_K8s["name"]
    log_path = "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log"
    container = ""
    traefik = test_flags.traefik

    if substrate == "k8s":
        log_path = "/var/log/opensearch-dashboards/opensearch_dashboards.log"
        container = "opensearch-dashboards"

    for unit in ops_test.model.applications[APP_NAME].units:
        assert count_lines_with(ops_test.model_full_name, unit.name, log_path, "debug", container)

        await ops_test.model.applications[APP_NAME].set_config({"log_level": "ERROR"})

        await wait_for_dashboard_idle(ops_test, traefik)
        debug_lines = count_lines_with(
            ops_test.model_full_name, unit.name, log_path, "debug", container
        )

        assert (
            count_lines_with(ops_test.model_full_name, unit.name, log_path, "debug", container)
            == debug_lines
        )

    await ops_test.model.applications[APP_NAME].set_config({"log_level": "INFO"})
    await wait_for_dashboard_idle(ops_test, traefik)


@pytest.mark.abort_on_fail
async def test_dashboard_status_changes(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    """Test status changes based on backend failures."""
    APP_NAME = METADATA_VM["name"] if substrate == "vm" else METADATA_K8s["name"]
    tls = test_flags.test_tls
    traefik = test_flags.traefik
    logger.info("Breaking opensearch connection")
    await ops_test.juju("remove-relation", "opensearch", APP_NAME)
    await ops_test_vm.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000
    )

    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked")

    logger.info("Waiting up to 600s for status OpenSearch connection is missing")
    async with ops_test.fast_forward("30s"):
        timeout = 600
        start_time = time.time()
        status_matched = False

        while time.time() - start_time < timeout:
            status_matched = await check_full_status(
                ops_test,
                app_name=APP_NAME,
                status="blocked",
                status_msg="OpenSearch connection is missing",
            )
            if status_matched:
                break

            await asyncio.sleep(10)

        assert status_matched

    logger.info("Checking if Dashboards have become unavailable")
    assert await all_dashboards_unavailable(ops_test, https=tls)

    logger.info("Restoring Opensearch connection")
    await ops_test.model.integrate(APP_NAME, OPENSEARCH_APP_NAME)
    await ops_test_vm.model.wait_for_idle(
        apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000
    )
    if not substrate == "k8s" or traefik:
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
        assert ops_test.model.applications[APP_NAME].status == "active"
        assert all(
            unit.workload_status == "active"
            for unit in ops_test.model.applications[APP_NAME].units
        )
    else:
        await wait_for_ingress_blocked(ops_test, APP_NAME, timeout=1000)

    logger.info("Checking if Dashboards is available again")
    assert await access_all_dashboards(
        ops_test_vm,
        ops_test,
        https=is_https_enabled(test_flags),
        verify=tls,
    )

    logger.info(
        "Adding a new index with shards allocated to a non-existent node to make cluster health red"
    )
    client_relation = get_relations(ops_test_vm, OPENSEARCH_RELATION_NAME, DB_CLIENT_APP_NAME)[0]

    payload = {
        "settings": {
            "index.routing.allocation.require._name": "non_existent_node",
            "index.number_of_shards": 5,
            "index.number_of_replicas": 0,
        }
    }

    payload = json.dumps(payload)

    unit_name = ops_test_vm.model.applications[DB_CLIENT_APP_NAME].units[0].name
    await client_run_db_request(
        ops_test_vm,
        unit_name,
        client_relation,
        "PUT",
        "/bad_index",
        re.escape(payload),
    )
    logger.info("Waiting up to 600s for OpenSearch service health to become red...")
    async with ops_test.fast_forward("30s"):
        timeout = 600
        start_time = time.time()
        status_matched = False

        while time.time() - start_time < timeout:
            status_matched = await check_full_status(
                ops_test,
                app_name=APP_NAME,
                status="blocked",
                status_msg="The OpenSearch service health is red",
            )
            if status_matched:
                break

            await asyncio.sleep(10)

        assert status_matched


async def test_restore_opensearch_restores_osd(
    ops_test_vm: OpsTest,
    ops_test: OpsTest,
    substrate: str,
    test_flags: Flags,
):
    """This test shouldn't be separate but a native continuation of the previous one."""
    APP_NAME = METADATA_VM["name"] if substrate == "vm" else METADATA_K8s["name"]
    tls = test_flags.test_tls
    traefik = test_flags.traefik
    logger.info("Destroying and restoring the Opensearch cluster")
    await destroy_cluster(
        ops_test_vm,
        app=OPENSEARCH_APP_NAME,
        consumer_ops_test=ops_test if substrate == "k8s" else None,
    )

    await ops_test_vm.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/stable",
        num_units=NUM_UNITS_DB,
        config=CONFIG_OPTS,
    )

    await ops_test_vm.model.integrate(OPENSEARCH_APP_NAME, TLS_CERTIFICATES_APP_NAME)

    async with ops_test_vm.fast_forward("30s"):
        await ops_test_vm.model.wait_for_idle(apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000)

        if substrate == "k8s":
            await ops_test_vm.model.create_offer(
                "opensearch-client", OPENSEARCH_APP_NAME, "opensearch"
            )
            await ops_test.model.consume(f"admin/{ops_test_vm.model.name}.{OPENSEARCH_APP_NAME}")
        await ops_test.model.integrate(APP_NAME, OPENSEARCH_APP_NAME)

        await ops_test_vm.model.wait_for_idle(
            apps=[OPENSEARCH_APP_NAME], status="active", timeout=1000
        )

    if substrate == "k8s" and not traefik:
        await wait_for_ingress_blocked(ops_test, APP_NAME, timeout=1000)
    else:
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    logger.info("Checking if Dashboards is available again")
    assert await access_all_dashboards(
        ops_test_vm, ops_test, https=is_https_enabled(test_flags), verify=tls
    )
