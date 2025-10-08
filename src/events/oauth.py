#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling OpenSearch Dashboards OAuth configuration."""

import logging
from typing import TYPE_CHECKING

from charms.hydra.v0.oauth import ClientConfig, OAuthRequirer
from ops import BlockedStatus, EventBase, ModelError, Object

from helpers import set_global_status
from literals import MSG_STATUS_OAUTH_INFO_FAILED, OAUTH_REL_NAME

if TYPE_CHECKING:
    from charm import OpensearchDashboardsCharm

logger = logging.getLogger(__name__)


class OAuthHandler(Object):
    """Handler for managing oauth relations."""

    def __init__(self, charm) -> None:
        super().__init__(charm, "oauth")
        self.charm: "OpensearchDashboardsCharm" = charm

        self.oauth = OAuthRequirer(self.charm, self._client_config(), relation_name=OAUTH_REL_NAME)
        self.framework.observe(
            self.charm.on[OAUTH_REL_NAME].relation_changed, self._on_oauth_relation_changed
        )
        self.framework.observe(
            self.charm.on[OAUTH_REL_NAME].relation_broken, self._on_oauth_relation_changed
        )

    def _on_oauth_relation_changed(self, event: EventBase) -> None:
        """Handler for `_on_oauth_relation_changed` event."""
        if not self.charm.state.servers:
            event.defer()
            return
        try:
            provider_info = self.oauth.get_provider_info()
        except ModelError as e:
            logger.error("OAuth provider info not available: %s", e)
            set_global_status(self.charm, BlockedStatus(MSG_STATUS_OAUTH_INFO_FAILED))
            event.defer()
            return
        self.charm.state.cluster.update(
            {
                "oauth-client-secret": (
                    provider_info.client_secret
                    if provider_info and provider_info.client_secret
                    else ""
                ),
            }
        )

        self.charm.reconcile(event)

    def _client_config(self) -> ClientConfig:
        """Generates actual client config for the OAuth."""
        return ClientConfig(
            audience=["opensearch"],
            redirect_uri=f"{self.charm.state.url}/auth/openid/login",
            scope="openid profile email phone offline address",
            grant_types=["authorization_code"],
            token_endpoint_auth_method="client_secret_post",
        )

    def update_client_config(self):
        """Updates redirect_uri of the OAuth client config if needed."""
        self.oauth.update_client_config(self._client_config())
