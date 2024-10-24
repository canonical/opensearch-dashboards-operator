#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses
import yaml
from ops.testing import Harness
from requests import ReadTimeout

from charm import OpensearchDasboardsCharm
from literals import CHARM_KEY, CONTAINER, OPENSEARCH_REL_NAME, SUBSTRATE

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
    harness._update_config({"log_level": "debug"})
    harness.begin()
    harness.charm.model.get_binding = MagicMock()
    harness.charm.model.get_binding.network.bind_address = MagicMock(return_value="10.10.10.10")

    return harness


@responses.activate
def test_api_request(harness):

    harness.set_leader(True)
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
    harness.charm.state.unit_server.relation = MagicMock(name="test")

    responses.add(
        method="GET",
        url=f"{harness.charm.state.url}/api/status",
        json=expected_response,
    )
    response = harness.charm.api_manager.request("status")
    assert all(field in response for field in ["status", "name", "version"])
    assert all(field in response["status"] for field in ["statuses", "overall"])


@responses.activate
def test_status(harness):

    harness.set_leader(True)
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

    response = harness.charm.api_manager.service_status()
    assert all(field in response for field in ["status", "name", "version"])
    assert all(field in response["status"] for field in ["statuses", "overall"])


@responses.activate
def test_request_timeout(harness):
    """ReadTimeout is "bubbled up" to caller."""
    responses.add(method="GET", url=f"{harness.charm.state.url}/api/status", body=ReadTimeout())
    with pytest.raises(ReadTimeout):
        harness.charm.api_manager.service_status()
