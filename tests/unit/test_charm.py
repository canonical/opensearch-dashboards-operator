#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
import yaml
from ops.framework import EventBase
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import OpensearchDasboardsCharm
from helpers import clear_status
from literals import CHARM_KEY, CONTAINER, OPENSEARCH_REL_NAME, PEER, SUBSTRATE

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
    harness._update_config({"log_level": "debug"})
    harness.begin()
    return harness


def test_clear_status(harness):
    harness.charm.unit.status = MaintenanceStatus("x")
    clear_status(harness.charm.unit, "x")
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    harness.charm.unit.status = WaitingStatus("y")
    clear_status(harness.charm.unit, "y")
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    harness.charm.unit.status = BlockedStatus("z")
    clear_status(harness.charm.unit, "z")
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_install_fails_create_passwords_until_peer_relation(harness):
    with harness.hooks_disabled():
        harness.set_leader(True)

    with patch("workload.ODWorkload.install"):
        harness.charm.on.install.emit()

    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_leader(True)

    assert not harness.charm.state.cluster.internal_user_credentials


def test_install_fails_creates_passwords_succeeds(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_leader(True)

    with patch("workload.ODWorkload.install"):
        harness.charm.on.install.emit()
        assert harness.charm.state.cluster.relation_data

        assert harness.charm.state.cluster.internal_user_credentials


@pytest.mark.skipif(SUBSTRATE == "k8s", reason="Snap not used on K8s charms")
def test_install_blocks_snap_install_failure(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_leader(True)

    with patch("workload.ODWorkload.install", return_value=False):
        harness.charm.on.install.emit()

        assert isinstance(harness.model.unit.status, BlockedStatus)


def test_install_sets_ip_hostname_fqdn(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_leader(True)

    with patch("workload.ODWorkload.install", return_value=False):
        harness.charm.on.install.emit()

        assert harness.charm.state.unit_server.private_ip


def test_relation_changed_emitted_for_leader_elected(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charm.OpensearchDasboardsCharm.reconcile") as patched:
        harness.set_leader(True)
        patched.assert_called_once()


def test_relation_changed_emitted_for_config_changed(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charm.OpensearchDasboardsCharm.reconcile") as patched:
        harness.charm.on.config_changed.emit()
        patched.assert_called_once()


def test_relation_changed_emitted_for_relation_changed(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charm.OpensearchDasboardsCharm.reconcile") as patched:
        harness.charm.on.dashboard_peers_relation_changed.emit(harness.charm.state.peer_relation)
        patched.assert_called_once()


def test_relation_changed_emitted_for_relation_joined(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charm.OpensearchDasboardsCharm.reconcile") as patched:
        harness.charm.on.dashboard_peers_relation_joined.emit(harness.charm.state.peer_relation)
        patched.assert_called_once()


def test_relation_changed_emitted_for_relation_departed(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charm.OpensearchDasboardsCharm.reconcile") as patched:
        harness.charm.on.dashboard_peers_relation_departed.emit(harness.charm.state.peer_relation)
        patched.assert_called_once()


def test_relation_changed_starts_units(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_planned_units(1)

    with (
        patch("charm.OpensearchDasboardsCharm.init_server") as patched,
        patch("managers.config.ConfigManager.config_changed"),
        patch("core.cluster.ClusterState.all_units_related", return_value=True),
    ):
        harness.charm.on.config_changed.emit()
        patched.assert_called_once()


def test_relation_changed_emitted_for_opensearch_relation_changed(harness):
    with harness.hooks_disabled():
        opensearch_rel_id = harness.add_relation(OPENSEARCH_REL_NAME, "opensearch")
        harness.add_relation_unit(opensearch_rel_id, "opensearch/0")

    with patch("events.requirer.RequirerEvents._on_client_relation_changed") as patched:
        harness.charm.on.opensearch_client_relation_changed.emit(
            harness.charm.state.opensearch_relation
        )
        patched.assert_called_once()


def test_relation_changed_does_not_start_units_again(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}/0", {"state": "started"})

    with (
        patch("charm.OpensearchDasboardsCharm.init_server") as patched,
        patch("managers.config.ConfigManager.config_changed"),
    ):
        harness.charm.on.config_changed.emit()
        patched.assert_not_called()


def test_relation_changed_does_not_restart_on_departing(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")

    with patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_acquire_lock") as patched:
        harness.remove_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        patched.assert_not_called()


def test_relation_changed_restarts(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}/0", {"state": "started"})

    with (
        patch(
            "charms.rolling_ops.v0.rollingops.RollingOpsManager._on_acquire_lock"
        ) as patched_restart,
        patch("managers.config.ConfigManager.config_changed", return_value=True),
        patch("core.cluster.ClusterState.all_units_related", return_value=True),
    ):
        harness.charm.on.config_changed.emit()
        patched_restart.assert_called_once()


def test_restart_fails_not_started(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_planned_units(1)

    with (
        patch("workload.ODWorkload.restart") as patched_restart,
        patch("workload.ODWorkload.start") as patched_start,
        patch(
            "core.models.ODCluster.internal_user_credentials",
            new_callable=PropertyMock,
            return_value={"user": "password"},
        ),
        patch("managers.config.ConfigManager.set_dashboard_properties"),
    ):
        harness.charm._restart(EventBase)
        patched_restart.assert_not_called()
        patched_start.assert_called_once()


def test_restart_restarts_with_sleep(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.set_planned_units(1)
        harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}/0", {"state": "started"})
        harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}", {"0": "added"})

    with (
        patch("workload.ODWorkload.restart") as patched_restart,
        patch("time.sleep") as patched_sleep,
    ):
        harness.charm._restart(EventBase(harness.charm))
        patched_restart.assert_called_once()
        assert patched_sleep.call_count >= 1


def test_init_server_calls_necessary_methods_non_leader(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}", {"monitor-password": "bla"})

    with (
        patch("managers.config.ConfigManager.set_dashboard_properties") as dashboard_properties,
        patch("workload.ODWorkload.start") as start,
    ):
        harness.charm.init_server()

        dashboard_properties.assert_called_once()
        start.assert_called_once()

        assert harness.charm.state.unit_server.started
        assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_init_server_calls_necessary_methods_leader(harness):
    with harness.hooks_disabled():
        peer_rel_id = harness.add_relation(PEER, CHARM_KEY)
        harness.set_leader(True)
        harness.add_relation_unit(peer_rel_id, f"{CHARM_KEY}/0")
        harness.update_relation_data(peer_rel_id, f"{CHARM_KEY}", {"monitor-password": "bla"})

    with (
        patch("managers.config.ConfigManager.set_dashboard_properties") as dashboard_properties,
        patch("workload.ODWorkload.start") as start,
    ):
        harness.charm.init_server()

        dashboard_properties.assert_called_once()
        start.assert_called_once()

        assert harness.charm.state.unit_server.started
        assert isinstance(harness.charm.app.status, BlockedStatus)
        assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_config_changed_applies_relation_data(harness):
    with harness.hooks_disabled():
        _ = harness.add_relation(PEER, CHARM_KEY)
        harness.set_leader(True)

    with (
        patch("core.cluster.ClusterState.stable", return_value=True),
        patch("managers.config.ConfigManager.config_changed") as patched,
        patch("core.cluster.ClusterState.all_units_related", return_value=True),
    ):
        harness.charm.on.config_changed.emit()

        patched.assert_called_once()


# def test_port_updates_if_tls(harness):
#     with harness.hooks_disabled():
#         harness.add_relation(PEER, CHARM_KEY)
#         app_id = harness.add_relation(REL_NAME, "application")
#         harness.set_leader(True)
#         harness.update_relation_data(app_id, "application", {"chroot": "app"})
#
#         # checking if ssl port and ssl flag are passed
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             f"{CHARM_KEY}/0",
#             {"private-address": "treebeard", "state": "started"},
#         )
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             CHARM_KEY,
#             {"quorum": "ssl", "relation-0": "mellon", "tls": "enabled"},
#         )
#         harness.charm.update_client_data()
#
#     uris = ""
#
#     for client in harness.charm.state.clients:
#         assert client.tls
#         uris = client.uris
#
#     with harness.hooks_disabled():
#         # checking if normal port and non-ssl flag are passed
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             f"{CHARM_KEY}/0",
#             {"private-address": "treebeard", "state": "started", "quorum": "non-ssl"},
#         )
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             CHARM_KEY,
#             {"quorum": "non-ssl", "relation-0": "mellon", "tls": ""},
#         )
#         harness.charm.update_client_data()
#
#     for client in harness.charm.state.clients:
#         assert not client.tls
#         assert client.uris != uris
#
#
# def test_update_relation_data(harness):
#     with harness.hooks_disabled():
#         harness.add_relation(PEER, CHARM_KEY)
#         harness.set_leader(True)
#         app_1_id = harness.add_relation(REL_NAME, "application")
#         app_2_id = harness.add_relation(REL_NAME, "new_application")
#         harness.update_relation_data(
#             app_1_id,
#             "application",
#             {"chroot": "app", "requested-secrets": json.dumps(["username", "password"])},
#         )
#         harness.update_relation_data(
#             app_2_id,
#             "new_application",
#             {
#                 "chroot": "new_app",
#                 "chroot-acl": "rw",
#                 "requested-secrets": json.dumps(["username", "password"]),
#             },
#         )
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             f"{CHARM_KEY}/0",
#             {
#                 "ip": "treebeard",
#                 "state": "started",
#                 "private-address": "glamdring",
#                 "hostname": "frodo",
#             },
#         )
#         harness.add_relation_unit(harness.charm.state.peer_relation.id, f"{CHARM_KEY}/1")
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             f"{CHARM_KEY}/1",
#             {"ip": "shelob", "state": "ready", "private-address": "narsil", "hostname": "sam"},
#         )
#         harness.add_relation_unit(harness.charm.state.peer_relation.id, f"{CHARM_KEY}/2")
#         harness.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             f"{CHARM_KEY}/2",
#             {
#                 "ip": "balrog",
#                 "state": "started",
#                 "private-address": "anduril",
#                 "hostname": "merry",
#             },
#         )
#         harness.charm.peer_app_interface.update_relation_data(
#             harness.charm.state.peer_relation.id,
#             {f"relation-{app_1_id}": "mellon", f"relation-{app_2_id}": "friend"},
#         )
#
#     with (
#         patch("core.cluster.ClusterState.ready", new_callable=PropertyMock, return_value=True),
#     ):
#         harness.charm.update_client_data()
#
#     # building bare clients for validation
#     usernames = []
#     passwords = []
#
#     for relation in harness.charm.state.client_relations:
#         myclient = None
#         for client in harness.charm.state.clients:
#             if client.relation == relation:
#                 myclient = client
#         client = ODClient(
#             relation=relation,
#             data_interface=harness.charm.client_provider_interface,
#             substrate=SUBSTRATE,
#             component=relation.app,
#             local_app=harness.charm.app,
#             password=myclient.relation_data.get("password", ""),
#             endpoints=myclient.relation_data.get("endpoints", ""),
#             uris=myclient.relation_data.get("uris", ""),
#             tls=myclient.relation_data.get("tls", ""),
#         )
#
#         assert client.username, (
#             client.password in harness.charm.state.cluster.client_passwords.items()
#         )
#         assert client.username not in usernames
#         assert client.password not in passwords
#
#         logger.info(client.endpoints)
#
#         assert len(client.endpoints.split(",")) == 3
#         assert len(client.uris.split(",")) == 3, client.uris
#
#         if SUBSTRATE == "vm":
#             # checking ips are used
#             for ip in ["treebeard", "shelob", "balrog"]:
#                 assert ip in client.endpoints
#                 assert ip in client.uris
#
#             # checking private-address or hostnames are NOT used
#             for hostname_address in ["glamdring", "narsil", "anduril", "sam", "frodo", "merry"]:
#                 assert hostname_address not in client.endpoints
#                 assert hostname_address not in client.uris
#
#         if SUBSTRATE == "k8s":
#             assert "endpoints" in client.endpoints
#             assert "endpoints" in client.uris
#
#         for uri in client.uris.split(","):
#             # checking client_port in uri
#             assert re.search(r":[\d]+", uri)
#
#         assert client.uris.endswith(client.chroot)
#
#         usernames.append(client.username)
#         passwords.append(client.password)
