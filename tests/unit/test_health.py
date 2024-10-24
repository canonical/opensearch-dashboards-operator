#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import responses
import yaml
from ops.testing import Harness
from requests import ReadTimeout

from charm import OpensearchDasboardsCharm
from literals import (
    CHARM_KEY,
    CONTAINER,
    MSG_STATUS_UNAVAIL,
    OPENSEARCH_REL_NAME,
    SUBSTRATE,
)
from src.literals import MSG_STATUS_DB_DOWN, MSG_STATUS_HANGING
from tests.unit.test_charm import MSG_STATUS_UNHEALTHY

logger = logging.getLogger(__name__)

CONFIG = str(yaml.safe_load(Path("./config.yaml").read_text()))
ACTIONS = str(yaml.safe_load(Path("./actions.yaml").read_text()))
METADATA = str(yaml.safe_load(Path("./metadata.yaml").read_text()))


@pytest.fixture
def harness():
    harness = Harness(OpensearchDasboardsCharm, meta=METADATA, config=CONFIG, actions=ACTIONS)

    if SUBSTRATE == "k8s":
        harness.set_can_connect(CONTAINER, True)

    harness.add_relation("restart", CHARM_KEY)
    upgrade_rel_id = harness.add_relation("upgrade", CHARM_KEY)
    harness.update_relation_data(upgrade_rel_id, f"{CHARM_KEY}/0", {"state": "idle"})
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, "opensearch")
    harness.add_relation_unit(opensearch_rel_id, "opensearch/0")
    harness.update_relation_data(
        opensearch_rel_id, "opensearch", {"endpoints": "111.222.333.444:9200,555.666.777.888:9200"}
    )
    harness.update_relation_data(opensearch_rel_id, "opensearch", {"tls-ca": "<cert_data_here>"})
    harness._update_config({"log_level": "INFO"})
    harness.begin()
    return harness


@responses.activate
def test_health_status_ok(harness):

    expected_response = {
        "name": "juju-3e401b-2",
        "uuid": "6e2def14-8870-4a70-bc84-82cdc99823e4",
        "version": {
            "number": "2.13.0",
            "build_hash": "2a9d6dd852c2931f94d292c09ed7a7ba82a43c82",
            "build_number": 7550,
            "build_snapshot": False,
        },
        "status": {
            "overall": {
                "since": "2024-07-06T20:18:31.394Z",
                "state": "green",
                "title": "Green",
                "nickname": "Looking good",
                "icon": "success",
                "uiColor": "secondary",
            },
            "statuses": [
                {
                    "id": "core:opensearch@2.13.0",
                    "message": "You're running OpenSearch Dashboards 2.13.0 with some "
                    "different versions of OpenSearch. Update OpenSearch Dashboards or "
                    "OpenSearch to the same version to prevent compatibility issues: "
                    "v2.14.0 @ 10.230.1.205:9200 (10.230.1.205), v2.14.0 @ "
                    "10.230.1.90:9200 (10.230.1.90)",
                    "since": "2024-07-06T20:18:31.394Z",
                    "state": "green",
                    "icon": "success",
                    "uiColor": "secondary",
                },
                {
                    "id": "core:savedObjects@2.13.0",
                    "message": "SavedObjects service has completed migrations and is available",
                    "since": "2024-07-06T20:18:31.394Z",
                    "state": "green",
                    "icon": "success",
                    "uiColor": "secondary",
                },
                {
                    "id": "plugin:ganttChartDashboards@2.13.0",
                    "message": "All dependencies are available",
                    "since": "2024-07-06T20:18:31.394Z",
                    "state": "green",
                    "icon": "success",
                    "uiColor": "secondary",
                },
            ],
        },
    }

    responses.add(
        method="GET",
        url=f"{harness.charm.state.url}/api/status",
        json=expected_response,
    )

    response = harness.charm.health_manager.status_ok()
    assert response[0]
    assert response[1] == ""


@responses.activate
def test_health_status_service_uniavail(harness):

    responses.add(
        method="GET",
        url=f"{harness.charm.state.url}/api/status",
        status=503,
        body="OpenSearch Dashboards server is not ready yet",
    )

    response = harness.charm.health_manager.status_ok()
    assert not response[0]
    assert response[1] == MSG_STATUS_UNAVAIL


@responses.activate
def test_health_status_service_unresponsive(harness):

    responses.add(
        method="GET",
        url=f"{harness.charm.state.url}/api/status",
        status=503,
        body=ReadTimeout(),
    )

    response = harness.charm.health_manager.status_ok()
    assert not response[0]
    assert response[1] == MSG_STATUS_HANGING


@responses.activate
def test_health_opensearch_ok(harness):

    opensearch_status = {
        "cluster_name": "opensearch-cluster",
        "status": "green",
        "timed_out": "false",
        "number_of_nodes": 2,
        "number_of_data_nodes": 2,
        "discovered_master": "true",
        "active_primary_shards": 6,
        "active_shards": 12,
        "relocating_shards": 0,
        "initializing_shards": 0,
        "unassigned_shards": 0,
        "delayed_unassigned_shards": 0,
        "number_of_pending_tasks": 0,
        "number_of_in_flight_fetch": 0,
        "task_max_waiting_in_queue_millis": 0,
        "active_shards_percent_as_number": 100.0,
    }

    responses.add(
        method="GET",
        url="https://111.222.333.444:9200/_cluster/health",
        status=200,
        json=opensearch_status,
    )

    assert harness.charm.health_manager.opensearch_ok()


@responses.activate
@pytest.mark.parametrize("status", [("yellow"), ("red")])
def test_health_opensearch_not_ok(harness, status):

    opensearch_status = {"status": status}

    responses.add(
        method="GET",
        url="https://111.222.333.444:9200/_cluster/health",
        status=200,
        json=opensearch_status,
    )

    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1):
        assert (False, MSG_STATUS_DB_DOWN) == harness.charm.health_manager.opensearch_ok()


@responses.activate
def test_health_opensearch_unavailable(harness):

    responses.add(
        method="GET",
        url="https://111.222.333.444:9200/_cluster/health",
        status=503,
    )

    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1):
        assert (False, MSG_STATUS_DB_DOWN) == harness.charm.health_manager.opensearch_ok()
