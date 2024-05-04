#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for Apache Opensearch Dashboards."""

import logging
import time

from charms.rolling_ops.v0.rollingops import RollingOpsManager
from ops.charm import CharmBase, InstallEvent, SecretChangedEvent
from ops.framework import EventBase
from ops.main import main
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus

from core.cluster import ClusterState
from events.password_actions import PasswordActionEvents
from events.requirer import RequirerEvents

# from events.provider import ProviderEvents
from events.tls import TLSEvents
from helpers import clear_status
from literals import (
    CHARM_KEY,
    CHARM_USERS,
    MSG_DB_MISSING,
    MSG_INSTALLING,
    MSG_RECONFIG,
    MSG_STARTING,
    MSG_STARTING_SERVER,
    MSG_TLS_CONFIG,
    MSG_WAITING_FOR_PEER,
    MSG_WAITING_FOR_USER_CREDENTIALS,
    PEER,
    RESTART_TIMEOUT,
    SUBSTRATE,
)
from managers.config import ConfigManager
from managers.tls import TLSManager
from workload import ODWorkload

# from events.upgrade import ODUpgradeEvents, OpensearchDasboardsDependencyModel


logger = logging.getLogger(__name__)


class OpensearchDasboardsCharm(CharmBase):
    """Charmed Operator for Opensearch Dashboards."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = CHARM_KEY
        self.state = ClusterState(self, substrate=SUBSTRATE)
        self.workload = ODWorkload()

        # --- CHARM EVENT HANDLERS ---

        self.password_action_events = PasswordActionEvents(self)
        self.tls_events = TLSEvents(self)
        self.requirer_events = RequirerEvents(self)
        # self.upgrade_events = ODUpgradeEvents(
        #     self,
        #     dependency_model=OpensearchDasboardsDependencyModel(
        #         **DEPENDENCIES  # pyright: ignore[reportGeneralTypeIssues]
        #     ),
        # )

        # --- MANAGERS ---

        self.tls_manager = TLSManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE
        )
        self.config_manager = ConfigManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE, config=self.config
        )

        # --- LIB EVENT HANDLERS ---

        self.restart = RollingOpsManager(self, relation="restart", callback=self._restart)

        # --- CORE EVENTS ---

        self.framework.observe(getattr(self.on, "install"), self._on_install)

        self.framework.observe(getattr(self.on, "start"), self._start)

        self.framework.observe(getattr(self.on, "update_status"), self.reconcile)
        self.framework.observe(getattr(self.on, "leader_elected"), self.reconcile)
        self.framework.observe(getattr(self.on, "config_changed"), self.reconcile)

        self.framework.observe(getattr(self.on, f"{PEER}_relation_changed"), self.reconcile)
        self.framework.observe(getattr(self.on, f"{PEER}_relation_joined"), self.reconcile)
        self.framework.observe(getattr(self.on, f"{PEER}_relation_departed"), self.reconcile)

        self.framework.observe(getattr(self.on, "secret_changed"), self._on_secret_changed)

    # --- CORE EVENT HANDLERS ---

    def _on_install(self, event: InstallEvent) -> None:
        """Handler for the `on_install` event."""
        self.unit.status = MaintenanceStatus(MSG_INSTALLING)

        install = self.workload.install()
        if not install:
            self.unit.status = BlockedStatus("unable to install Opensearch Dashboards")

        # don't complete install until passwords set
        if not self.state.peer_relation:
            self.unit.status = WaitingStatus(MSG_WAITING_FOR_PEER)
            event.defer()
            return
        clear_status(self.unit, MSG_WAITING_FOR_PEER)

        if self.unit.is_leader() and not self.state.cluster.internal_user_credentials:
            for user in CHARM_USERS:
                self.state.cluster.update({f"{user}-password": self.workload.generate_password()})
        clear_status(self.unit, [MSG_INSTALLING, MSG_WAITING_FOR_USER_CREDENTIALS])

    def reconcile(self, event: EventBase) -> None:
        """Generic handler for all 'something changed, update' events across all relations."""

        # not all methods called
        if not self.state.peer_relation:
            return

        # attempt startup of server
        if not self.state.unit_server.started:
            self.init_server()

        # don't delay scale-down leader ops by restarting dying unit
        if getattr(event, "departing_unit", None) == self.unit:
            return

        outdated_status = []
        # Maintain the correct app status
        if self.unit.is_leader():
            if self.state.opensearch_server:
                outdated_status.append(MSG_DB_MISSING)

        # Maintain the correct unit status

        # Request new certificates if IP changed
        if self.state.cluster.tls:
            if self.state.unit_server.tls and self.tls_manager.certificate_valid():
                outdated_status.append(MSG_TLS_CONFIG)
            else:
                self.unit.status = MaintenanceStatus(MSG_TLS_CONFIG)

        # Restart on config change
        if (
            self.config_manager.config_changed()
            and self.state.unit_server.started
            # and self.upgrade_events.idle
        ):
            # NOTE: We never clean up MSG_RECONFIG, as it MUST be replaced by rolling_ops statuses
            # (Otherwise the server is out-of-date)
            # It is to ensure continuality of non-active status as needed
            self.unit.status = MaintenanceStatus(MSG_RECONFIG)
            self.on[f"{self.restart.name}"].acquire_lock.emit()

        # Clear all possible irrelevant statuses
        for status in outdated_status:
            clear_status(self.unit, status)

    def _on_secret_changed(self, event: SecretChangedEvent):
        """Reconfigure services on a secret changed event."""
        if not event.secret.label:
            return

        if not self.state.peer_relation:
            return

        cluster_secret_label = self.state.cluster.data_interface._generate_secret_label(
            PEER,
            self.state.peer_relation.id,
            "extra",  # type:ignore noqa
        )  # Changes with the soon upcoming new version of DP-libs STILL within this POC

        server_secret_label = self.state.unit_server.data_interface._generate_secret_label(
            PEER,
            self.state.peer_relation.id,
            "extra",  # type:ignore noqa
        )  # Changes with the soon upcoming new version of DP-libs STILL within this POC

        if event.secret.label in [cluster_secret_label, server_secret_label]:
            logger.info(f"Secret {event.secret.label} changed.")
            self.reconcile(event)

    def _start(self, event: EventBase) -> None:
        """Forces a rolling-restart event.

        Necessary for ensuring that `on_start` restarts roll.
        """
        # if not self.state.peer_relation or not self.state.stable or not self.upgrade_events.idle:
        self.unit.status = MaintenanceStatus(MSG_STARTING)
        if not self.state.peer_relation or not self.state.stable:
            event.defer()
            return

        self.reconcile(event)
        clear_status(self.unit, MSG_STARTING)

    def _restart(self, event: EventBase) -> None:
        """Handler for emitted restart events."""
        # if not self.state.stable or not self.upgrade_events.idle:
        #     event.defer()
        #     return
        if not self.state.unit_server.started:
            self.reconcile(event)
            return

        logger.info(f"{self.unit.name} restarting...")
        self.workload.restart()

        start_time = time.time()
        while not self.workload.alive() and time.time() - start_time < RESTART_TIMEOUT:
            time.sleep(5)

        clear_status(self.unit, [MSG_STARTING, MSG_STARTING_SERVER])

    # --- CONVENIENCE METHODS ---

    def init_server(self):
        """Calls startup functions for server start."""
        # don't run if leader has not yet created passwords
        if not self.state.cluster.internal_user_credentials:
            self.unit.status = MaintenanceStatus(MSG_WAITING_FOR_USER_CREDENTIALS)
            return

        self.unit.status = MaintenanceStatus(MSG_STARTING_SERVER)
        logger.info(f"{self.unit.name} initializing...")

        logger.debug("setting properties")
        self.config_manager.set_dashboard_properties()

        logger.debug("starting Opensearch Dashboards service")
        self.workload.start()

        # unit flags itself as 'started' so it can be retrieved by the leader
        logger.info(f"{self.unit.name} started")

        # added here in case a `restart` was missed
        self.state.unit_server.update({"state": "started"})
        clear_status(self.unit, MSG_STARTING_SERVER)

        if self.unit.is_leader() and not self.state.opensearch_server:
            self.app.status = BlockedStatus(MSG_DB_MISSING)


if __name__ == "__main__":
    main(OpensearchDasboardsCharm)
