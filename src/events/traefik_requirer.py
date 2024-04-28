#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Event handler for related applications on the `zookeeper` relation interface."""
import logging
from typing import TYPE_CHECKING

from charms.traefik_k8s.v2.ingress import (
    IngressPerAppRequirer,
    IngressPerAppReadyEvent,
    IngressPerAppRevokedEvent,
)
from ops.framework import Object

if TYPE_CHECKING:
    from charm import OpensearchDasboardsCharm

logger = logging.getLogger(__name__)


class TraefikRequirerEvents(Object):
    """Event handlers for related applications on the `traefik` relation interface."""

    def __init__(self, charm):
        super().__init__(charm, "provider")
        self.charm: "OpensearchDasboardsCharm" = charm

        self.ingress = IngressPerAppRequirer(self.charm, port=5601)

        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        logger.info("This app's ingress URL: %s", event.url)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        logger.info("This app no longer has ingress")
