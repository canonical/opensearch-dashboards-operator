#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for Apache Opensearch Dashboards."""

import logging
import time

from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.rolling_ops.v0.rollingops import RollingOpsManager
from ops.charm import CharmBase, InstallEvent, SecretChangedEvent
from ops.framework import EventBase
from ops.main import main
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus

from core.cluster import ClusterState
from events.oauth import OAuthHandler
from events.requirer import RequirerEvents
from events.tls import TLSEvents
from events.upgrade import ODUpgradeEvents, OpensearchDashboardsDependencyModel
from helpers import (
    clear_global_status,
    clear_status,
    set_global_status,
    update_grafana_dashboards_title,
)
from literals import (
    CHARM_KEY,
    COS_PORT,
    COS_RELATION_NAME,
    DEPENDENCIES,
    MSG_APP_STATUS,
    MSG_INCOMPATIBLE_UPGRADE,
    MSG_INSTALLING,
    MSG_STARTING,
    MSG_STARTING_SERVER,
    MSG_STATUS_DB_MISSING,
    MSG_STATUS_HANGING,
    MSG_TLS_CONFIG,
    MSG_UNIT_STATUS,
    MSG_WAITING_FOR_PEER,
    PEER,
    RESTART_TIMEOUT,
    SERVER_PORT,
    SERVICE_AVAILABLE_TIMEOUT,
    SUBSTRATE,
)
from managers.api import APIManager
from managers.config import ConfigManager
from managers.health import HealthManager
from managers.tls import TLSManager
from managers.upgrade import UpgradeManager
from workload import ODWorkload

logger = logging.getLogger(__name__)


class OpensearchDasboardsCharm(CharmBase):
    """Charmed Operator for Opensearch Dashboards."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = CHARM_KEY
        self.state = ClusterState(self, substrate=SUBSTRATE)
        self.workload = ODWorkload()

        # --- CHARM EVENT HANDLERS ---

        self.tls_events = TLSEvents(self)
        self.requirer_events = RequirerEvents(self)
        dependency_model = OpensearchDashboardsDependencyModel(**DEPENDENCIES)
        self.upgrade_events = ODUpgradeEvents(self, dependency_model=dependency_model)
        self.oauth = OAuthHandler(self)

        # --- MANAGERS ---

        self.tls_manager = TLSManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE
        )
        self.config_manager = ConfigManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE, config=self.config
        )
        self.api_manager = APIManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE
        )
        self.health_manager = HealthManager(
            state=self.state, workload=self.workload, substrate=SUBSTRATE
        )
        self.upgrade_manager = UpgradeManager(
            state=self.state,
            workload=self.workload,
            substrate=SUBSTRATE,
            dependency_model=dependency_model,
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

        # --- COS ---
        self.cos_integration = COSAgentProvider(
            self,
            relation_name=COS_RELATION_NAME,
            metrics_endpoints=[],
            scrape_configs=self._scrape_config,
            refresh_events=[self.on.config_changed],
            metrics_rules_dir="./src/alert_rules/prometheus",
            log_slots=["opensearch-dashboards:logs"],
        )

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
        clear_status(self.unit, [MSG_INSTALLING, MSG_WAITING_FOR_PEER])

    def reconcile(self, event: EventBase) -> None:
        """Generic handler for all 'something changed, update' events across all relations."""
        # 1. Block until peer relation is set
        if not self.state.peer_relation:
            self.unit.status = WaitingStatus(MSG_WAITING_FOR_PEER)
            return

        update_grafana_dashboards_title(self)

        outdated_status = [MSG_WAITING_FOR_PEER]

        # attempt startup of server
        if not self.state.unit_server.started:
            self.init_server()

        # don't delay scale-down leader ops by restarting dying unit
        if getattr(event, "departing_unit", None) == self.unit:
            return

        # 2. Restart if the service is down or on config change

        # Evaluate unit health at this point (as it may trigger a restart)
        unit_healthy, unit_msg = self.health_manager.unit_healthy()

        if (
            (not unit_healthy and unit_msg == MSG_STATUS_HANGING)
            or self.config_manager.config_changed()
            and self.state.unit_server.started
            and self.upgrade_events.idle
        ):
            self.on[f"{self.restart.name}"].acquire_lock.emit()
            # No point in setting any status -- would be wiped out by rollingops after the restert
            return

        # 3. Maintain the correct app status
        # No further actions below but only status settings

        # Block until Opensearch is available and it's a compatible version
        if self.state.opensearch_server:
            outdated_status.append(MSG_STATUS_DB_MISSING)
        else:
            set_global_status(self, BlockedStatus(MSG_STATUS_DB_MISSING))
            return

        if self.upgrade_manager.version_compatible():
            outdated_status.append(MSG_INCOMPATIBLE_UPGRADE)
        else:
            set_global_status(self, BlockedStatus(MSG_INCOMPATIBLE_UPGRADE))
            return

        # Maintain the correct unit status

        # Request new certificates if IP changed
        if self.state.cluster.tls:
            if self.state.unit_server.tls and self.tls_manager.certificate_valid():
                outdated_status.append(MSG_TLS_CONFIG)
            else:
                self.unit.status = MaintenanceStatus(MSG_TLS_CONFIG)
                return
        else:
            outdated_status.append(MSG_TLS_CONFIG)

        # Handle possible changes to the TLS
        # TODO: HTTP - HTTPS switching should be fixed to fully utilize this
        self.oauth.update_client_config()

        # Regular health-check
        # Checks that may modify the 'app' state as well
        app_healthy, app_msg = self.health_manager.app_healthy()
        if not app_healthy:
            set_global_status(self, BlockedStatus(app_msg))
            return
        else:
            outdated_status += MSG_APP_STATUS

        # Checks purely on unit level
        if not unit_healthy:
            self.unit.status = BlockedStatus(unit_msg)
            return

        if unit_msg:
            self.unit.status = WaitingStatus(unit_msg)
            return
        else:
            outdated_status += MSG_UNIT_STATUS

        # Clear all possible irrelevant statuses
        for status in outdated_status:
            clear_global_status(self, status)

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
        if not self.state.unit_server.started:
            self.reconcile(event)
            return

        logger.info(f"{self.unit.name} restarting...")
        self.workload.restart()

        # Allow the service to start up safely on the snap level
        start_time = time.time()
        while not self.workload.alive() and time.time() - start_time < RESTART_TIMEOUT:
            time.sleep(5)

        # Allow the service to establish
        # Reason: we are emitting an 'update-status' right after
        # If the service is not yet functional, the status is set as
        # 'Service unavailable' until the next 'update-status' hook execution
        start_time = time.time()
        unit_healthy, _ = self.health_manager.unit_healthy()
        while not unit_healthy and time.time() - start_time < SERVICE_AVAILABLE_TIMEOUT:
            time.sleep(5)
            unit_healthy, _ = self.health_manager.unit_healthy()

        clear_status(self.unit, [MSG_STARTING, MSG_STARTING_SERVER])

    # --- CONVENIENCE METHODS ---

    def init_server(self):
        """Calls startup functions for server start."""
        self.unit.status = MaintenanceStatus(MSG_STARTING_SERVER)
        logger.info(f"{self.unit.name} initializing...")

        logger.debug("setting properties")
        self.config_manager.set_dashboard_properties()

        logger.debug("starting Opensearch Dashboards service")

        self.workload.start()

        # open port
        self.unit.open_port("tcp", port=SERVER_PORT)

        # unit flags itself as 'started' so it can be retrieved by the leader
        logger.info(f"{self.unit.name} started")

        # added here in case a `restart` was missed
        self.state.unit_server.update({"state": "started"})
        clear_status(self.unit, MSG_STARTING_SERVER)

        if self.unit.is_leader() and not self.state.opensearch_server:
            self.app.status = BlockedStatus(MSG_STATUS_DB_MISSING)

    def _scrape_config(self) -> list[dict]:
        """Generates the scrape config as needed."""
        return [
            {
                "metrics_path": "/metrics",
                "static_configs": [
                    {"targets": [f"{self.state.unit_server.private_ip}:{COS_PORT}"]}
                ],
                # "tls_config": {"ca": self.state.unit_server.ca},
                "scheme": "http",
            }
        ]


if __name__ == "__main__":
    main(OpensearchDasboardsCharm)
