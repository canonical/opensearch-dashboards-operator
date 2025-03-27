#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
import yaml
from ops.testing import Harness

from charm import OpensearchDasboardsCharm
from literals import CHARM_KEY, CONTAINER, PEER, SUBSTRATE

logger = logging.getLogger(__name__)

CONFIG = str(yaml.safe_load(Path("./config.yaml").read_text()))
ACTIONS = str(yaml.safe_load(Path("./actions.yaml").read_text()))
METADATA = str(yaml.safe_load(Path("./metadata.yaml").read_text()))

DEFAULT_CONF = """logging.verbose: true
opensearch.requestHeadersWhitelist:
- authorization
- securitytenant
opensearch_security.cookie.secure: false
opensearch_security.multitenancy.enabled: true
opensearch_security.multitenancy.tenants.preferred:
- Private
- Global
opensearch_security.readonly_mode.roles:
- kibana_read_only
path.data: /var/snap/opensearch-dashboards/common/var/lib/opensearch-dashboards
server.host: {ip}
server.ssl.enabled: false
"""


@pytest.fixture
def harness():
    harness = Harness(OpensearchDasboardsCharm, meta=METADATA, config=CONFIG, actions=ACTIONS)

    if SUBSTRATE == "k8s":
        harness.set_can_connect(CONTAINER, True)

    harness.add_relation("restart", CHARM_KEY)
    harness.add_relation(PEER, CHARM_KEY)
    harness._update_config({"log_level": "INFO"})
    harness.begin()
    return harness


def test_log_level_changed(harness):
    with (patch("managers.config.ConfigManager.set_dashboard_properties") as set_props,):
        harness.charm.config_manager.config_changed()
        set_props.assert_called_once()

    with (
        patch("workload.ODWorkload.read", return_value=["log_level: logging.silent"]),
        patch("workload.ODWorkload.write") as write,
    ):
        assert harness.charm.config_manager.config_changed()
        content = DEFAULT_CONF.format(ip=harness.charm.state.bind_address)
        path = "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/opensearch_dashboards.yml"
        write.assert_called_with(content=content, path=path)


def test_tls_disabled(harness):
    assert "server.ssl.enabled: true" not in harness.charm.config_manager.dashboard_properties


def test_tls_enabled(harness):
    with (
        patch("ops.framework.EventBase.defer"),
        patch("core.cluster.ClusterState.stable", new_callable=PropertyMock, return_value=True),
    ):
        harness.charm.unit.add_secret(
            {"private-key": "key", "certificate": "cert", "ca-cert": "exists"},
            label=f"{PEER}.opensearch-dashboards.unit",
        )

    assert harness.charm.config_manager.dashboard_properties.get("server.ssl.enabled") is True
