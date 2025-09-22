#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from charms.data_platform_libs.v0.upgrade import ClusterNotReadyError, DependencyModel
from ops.model import BlockedStatus
from ops.testing import Harness

from charm import OpensearchDashboardsCharm
from events.upgrade import ODUpgradeEvents, OpensearchDashboardsDependencyModel
from exceptions import OSDInstallError
from literals import CHARM_KEY, DEPENDENCIES
from src.literals import MSG_INCOMPATIBLE_UPGRADE
from tests.unit.test_charm import OPENSEARCH_REL_NAME
from workload import ODWorkload

logger = logging.getLogger(__name__)


CONFIG = str(yaml.safe_load(Path("./config.yaml").read_text()))
ACTIONS = str(yaml.safe_load(Path("./actions.yaml").read_text()))
METADATA = str(yaml.safe_load(Path("./metadata.yaml").read_text()))

OPENSEARCH_APP_NAME = "opensearch"


@pytest.fixture
def harness():
    harness = Harness(OpensearchDashboardsCharm, meta=METADATA, config=CONFIG, actions=ACTIONS)
    harness.add_relation("dashboard_peers", CHARM_KEY)
    harness.add_relation("restart", CHARM_KEY)
    harness.add_relation("upgrade", CHARM_KEY)

    harness.begin()
    with harness.hooks_disabled():
        harness.update_relation_data(
            harness.charm.state.peer_relation.id, f"{CHARM_KEY}/0", {"hostname": "000.000.000"}
        )

    harness.charm.upgrade_manager.dependency_model = OpensearchDashboardsDependencyModel(
        **{
            "osd_upstream": {
                "dependencies": {"opensearch": "2.12"},
                "name": "opensearch-dashboards",
                "upgrade_supported": ">=2",
                "version": "2.12",
            },
        }
    )

    return harness


def test_pre_upgrade_check_succeeds(harness, mocker):
    """pre_upgrade_check successful on a healthy system."""
    with patch("workload.ODWorkload.alive", return_value=True):
        assert harness.charm.upgrade_events.pre_upgrade_check() is None


def test_pre_upgrade_check_fails_if_workload_down(harness, mocker):
    """Simulate a workflow failure to veriy pre_upgrade_check fails then."""
    with patch("workload.ODWorkload.alive", return_value=False):
        with pytest.raises(ClusterNotReadyError):
            assert harness.charm.upgrade_events.pre_upgrade_check() is None
            harness.charm.unit.status = BlockedStatus(MSG_INCOMPATIBLE_UPGRADE)


@pytest.mark.parametrize("version", [("2.1.1"), ("2.12.0"), ("2.12.1"), ("2.12")])
def test_post_upgrade_check_succeeds(version, harness, mocker):
    """Verify success if no version mismatch"""
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    harness.update_relation_data(opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": version})
    assert harness.charm.upgrade_events.post_upgrade_check() is None
    assert harness.charm.upgrade_manager.version_compatible() is True


def test_post_upgrade_check_fails_major(harness, mocker):
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    with pytest.raises(ClusterNotReadyError):
        harness.update_relation_data(
            opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": "3.1"}
        )
        assert harness.charm.upgrade_events.post_upgrade_check() is None
        assert harness.charm.upgrade_manager.version_compatible() is False
        assert isinstance(harness.model.unit.status, BlockedStatus)


def test_post_upgrade_check_fails_minor(harness, mocker):
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    with pytest.raises(ClusterNotReadyError):
        harness.update_relation_data(
            opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": "2.13.1"}
        )
        assert harness.charm.upgrade_events.post_upgrade_check() is None
        assert harness.charm.upgrade_manager.version_compatible() is False
        assert isinstance(harness.model.unit.status, BlockedStatus)


def test_build_upgrade_stack(harness):
    with harness.hooks_disabled():
        harness.add_relation_unit(harness.charm.state.peer_relation.id, f"{CHARM_KEY}/1")
        harness.update_relation_data(
            harness.charm.state.peer_relation.id, f"{CHARM_KEY}/1", {"hostname": "111.111.111"}
        )
        harness.add_relation_unit(harness.charm.state.peer_relation.id, f"{CHARM_KEY}/2")
        harness.update_relation_data(
            harness.charm.state.peer_relation.id, f"{CHARM_KEY}/2", {"hostname": "222.222.222"}
        )
        harness.add_relation_unit(harness.charm.state.peer_relation.id, f"{CHARM_KEY}/3")
        harness.update_relation_data(
            harness.charm.state.peer_relation.id, f"{CHARM_KEY}/3", {"hostname": "333.333.333"}
        )

    stack = harness.charm.upgrade_events.build_upgrade_stack()

    assert stack[0] == 0
    assert len(stack) == 4


def test_dashboards_dependency_model():
    assert sorted(OpensearchDashboardsDependencyModel.__fields__.keys()) == sorted(
        DEPENDENCIES.keys()
    )

    for value in DEPENDENCIES.values():
        assert DependencyModel(**value)


def test_upgrade_granted_sets_failed_if_failed_snap(harness, mocker):
    mocker.patch.object(ODWorkload, "stop")
    mocker.patch.object(ODWorkload, "restart")
    mocker.patch.object(ODWorkload, "install", side_effect=OSDInstallError("install failed"))
    mocker.patch.object(ODUpgradeEvents, "pre_upgrade_check")
    mocker.patch.object(ODUpgradeEvents, "set_unit_completed")
    mocker.patch.object(ODUpgradeEvents, "set_unit_failed")

    mock_event = mocker.MagicMock()

    harness.charm.upgrade_events._on_upgrade_granted(mock_event)

    ODWorkload.stop.assert_called_once()
    ODWorkload.install.assert_called_once()
    ODWorkload.restart.assert_not_called()
    ODUpgradeEvents.set_unit_completed.assert_not_called()
    ODUpgradeEvents.set_unit_failed.assert_called_once()


def test_upgrade_granted_sets_failed_if_failed_upgrade_check(harness, mocker):
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    harness.update_relation_data(
        opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": "5.12.1"}
    )

    mocker.patch.object(ODWorkload, "stop")
    mocker.patch.object(ODWorkload, "restart")
    mocker.patch.object(ODWorkload, "install", return_value=True)
    mocker.patch.object(ODUpgradeEvents, "set_unit_completed")
    mocker.patch.object(ODUpgradeEvents, "set_unit_failed")

    mock_event = mocker.MagicMock()

    harness.charm.upgrade_events._on_upgrade_granted(mock_event)

    ODWorkload.stop.assert_called_once()
    ODWorkload.install.assert_called_once()
    ODUpgradeEvents.set_unit_completed.assert_not_called()
    ODUpgradeEvents.set_unit_failed.assert_called_once()


def test_upgrade_granted_succeeds(harness, mocker):
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    harness.update_relation_data(
        opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": "2.12.1"}
    )

    mocker.patch.object(ODWorkload, "stop")
    mocker.patch.object(ODWorkload, "restart")
    mocker.patch.object(ODWorkload, "install")
    mocker.patch.object(ODUpgradeEvents, "pre_upgrade_check")
    mocker.patch.object(ODUpgradeEvents, "set_unit_completed")
    mocker.patch.object(ODUpgradeEvents, "set_unit_failed")

    mock_event = mocker.MagicMock()

    harness.charm.upgrade_events._on_upgrade_granted(mock_event)

    ODWorkload.stop.assert_called_once()
    ODWorkload.install.assert_called_once()
    ODWorkload.restart.assert_called_once()
    ODUpgradeEvents.set_unit_completed.assert_called_once()
    ODUpgradeEvents.set_unit_failed.assert_not_called()


def test_upgrade_granted_recurses_upgrade_changed_on_leader(harness, mocker):
    opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, OPENSEARCH_APP_NAME)
    harness.update_relation_data(
        opensearch_rel_id, f"{OPENSEARCH_APP_NAME}", {"version": "2.12.1"}
    )

    mocker.patch.object(ODWorkload, "stop")
    mocker.patch.object(ODWorkload, "restart")
    mocker.patch.object(ODWorkload, "install")
    mocker.patch.object(ODUpgradeEvents, "pre_upgrade_check")
    mocker.patch.object(ODUpgradeEvents, "on_upgrade_changed")

    mock_event = mocker.MagicMock()

    harness.charm.upgrade_events._on_upgrade_granted(mock_event)

    ODUpgradeEvents.on_upgrade_changed.assert_not_called()

    with harness.hooks_disabled():
        harness.set_leader(True)

    harness.charm.upgrade_events._on_upgrade_granted(mock_event)

    ODUpgradeEvents.on_upgrade_changed.assert_called_once()
