# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Event handler for JWT authentication configuration."""

import logging
from typing import TYPE_CHECKING

import ops

from literals import JWT_REL_NAME

if TYPE_CHECKING:
    from charm import OpensearchDashboardsCharm

logger = logging.getLogger(__name__)


class JwtEvents(ops.Object):
    """Handler for managing JWT relations."""

    def __init__(self, charm):
        super().__init__(charm, "provider")
        self.charm: "OpensearchDashboardsCharm" = charm

        self.framework.observe(self.charm.on.secret_changed, self._on_secret_changed)
        self.framework.observe(
            self.charm.on[JWT_REL_NAME].relation_changed, self._on_jwt_relation_changed
        )
        self.framework.observe(
            self.charm.on[JWT_REL_NAME].relation_broken, self._on_jwt_relation_broken
        )

    def _on_jwt_relation_changed(self, event: ops.RelationChangedEvent) -> None:
        """Handle changed relation data."""
        if not self.charm.state.jwt_relation:
            logger.error(f"Cannot access relation data for {JWT_REL_NAME}")
            return

        if self.charm.config_manager.config_changed():
            logger.info("Initiate restart for applying config changes")
            self.charm.on[f"{self.charm.restart.name}"].acquire_lock.emit()

    def _on_jwt_relation_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle the removal of the relation."""
        if self.charm.config_manager.config_changed():
            logger.info("Initiate restart for applying config changes")
            self.charm.on[f"{self.charm.restart.name}"].acquire_lock.emit()

    def _on_secret_changed(self, event: ops.SecretChangedEvent) -> None:
        """Handle updates to the relation secret."""
        # this is only for developer documentation: currently we don't need the secret data
        pass
