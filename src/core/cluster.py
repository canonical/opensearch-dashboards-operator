#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of global cluster state for the ZooKeeper quorum."""
import logging
from typing import Dict, Optional, Set

from charms.data_platform_libs.v0.data_interfaces import DataPeerOtherUnit
from ops.framework import Framework, Object
from ops.model import Relation, Unit

from core.models import (
    SUBSTRATES,
    CharmWithRelationData,
    ODCluster,
    ODServer,
    OpensearchServer,
)
from literals import OPENSEARCH_REL_NAME, PEER

logger = logging.getLogger(__name__)


class ClusterStateBase(Object):
    """Collection of global cluster state for Framework/Object."""

    def __init__(self, charm: Framework | Object, substrate: SUBSTRATES):
        super().__init__(parent=charm, key="charm_state")
        self.substrate: SUBSTRATES = substrate

    # --- RAW RELATION ---

    @property
    def peer_relation(self) -> Relation | None:
        """The cluster peer relation."""
        return self.model.get_relation(PEER)

    @property
    def opensearch_relation(self) -> Optional[Relation]:
        """The Opensearch Server relation."""
        if self.model.relations.get(OPENSEARCH_REL_NAME):
            return self.model.relations[OPENSEARCH_REL_NAME][0]


class ClusterState(ClusterStateBase):
    """Collection of global cluster state for the charm."""

    def __init__(self, charm: CharmWithRelationData, substrate: SUBSTRATES):
        super().__init__(charm, substrate)
        self.charm = charm
        self._servers_data = {}

    # --- CORE COMPONENTS---

    @property
    def unit_server(self) -> ODServer:
        """The server state of the current running Unit."""
        return ODServer(
            relation=self.peer_relation,
            data_interface=self.charm.peer_unit_interface,
            component=self.model.unit,
            substrate=self.substrate,
        )

    @property
    def peer_units_data_interfaces(self) -> Dict[Unit, DataPeerOtherUnit]:
        """The cluster peer relation."""
        if not self.peer_relation or not self.peer_relation.units:
            return {}

        for unit in self.peer_relation.units:
            if unit not in self._servers_data:
                self._servers_data[unit] = DataPeerOtherUnit(
                    charm=self.charm, unit=unit, relation_name=PEER
                )
        return self._servers_data

    @property
    def cluster(self) -> ODCluster:
        """The cluster state of the current running App."""
        return ODCluster(
            relation=self.peer_relation,
            data_interface=self.charm.peer_app_interface,
            component=self.model.app,
            substrate=self.substrate,
        )

    @property
    def servers(self) -> Set[ODServer]:
        """Grabs all servers in the current peer relation, including the running unit server.

        Returns:
            Set of ODServers in the current peer relation, including the running unit server.
        """
        if not self.peer_relation:
            return set()

        servers = set()
        for unit, data_interface in self.peer_units_data_interfaces.items():
            servers.add(
                ODServer(
                    relation=self.peer_relation,
                    data_interface=data_interface,
                    component=unit,
                    substrate=self.substrate,
                )
            )
        servers.add(self.unit_server)

        return servers

    @property
    def opensearch_server(self) -> Optional[OpensearchServer]:
        """The state for all related client Applications."""
        if not self.opensearch_relation or not self.opensearch_relation.app:
            return None

        # We assume no more than 1 server relation
        return OpensearchServer(
            relation=self.opensearch_relation,
            data_interface=self.charm.client_requires_interface,
            component=self.opensearch_relation.app,
            substrate=self.substrate,
            local_app=self.cluster.app,
            tls="enabled" if self.cluster.tls else "disabled",
        )

    # --- CLUSTER INIT ---

    @property
    def endpoints(self) -> list[str]:
        """The connection uris for all started ZooKeeper units.

        Returns:
            List of unit addresses
        """
        return sorted(
            [
                server.host if self.substrate == "k8s" else server.private_ip
                for server in self.servers
            ]
        )

    @property
    def started_servers(self) -> Set[ODServer]:
        """The server states of all started peer-related Units."""
        return {server for server in self.servers if server.started}

    @property
    def all_units_related(self) -> bool:
        """Checks if currently related units make up all planned units.

        Returns:
            True if all units are related. Otherwise False
        """
        return len(self.servers) == self.model.app.planned_units()

    # --- HEALTH ---

    @property
    def healthy(self) -> bool:
        """Flag to check if the cluster is safe to update members."""
        # TBD
        return True

    @property
    def stable(self) -> bool:
        """Flag to check if the quorum is in a stable state, with all members up-to-date."""
        if not self.all_units_related:
            logger.debug("cluster not stable - not all units related")
            return False

        return True

    @property
    def ready(self) -> bool:
        """Flag to check if the charm is ready to handle related applications."""
        if not self.stable:
            logger.debug("provider not ready - cluster not stable")
            return False

        return True
