#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for for handling configuration building + writing."""
import logging
from typing import TYPE_CHECKING, Any

import yaml
from ops.model import ConfigData

if TYPE_CHECKING:
    pass

from core.cluster import SUBSTRATES, ClusterState
from core.workload import WorkloadBase

logger = logging.getLogger(__name__)


DEFAULT_PROPERTIES = {
    "opensearch.requestHeadersWhitelist": ["authorization", "securitytenant"],
    "opensearch_security.multitenancy.enabled": True,
    "opensearch_security.multitenancy.tenants.preferred": ["Private", "Global"],
    "opensearch_security.readonly_mode.roles": ["kibana_read_only"],
    "server.ssl.enabled": False,
    "opensearch_security.cookie.secure": False,
}

# Overrides the DEFAULT_PROPERTIES if we have TLS enabled
TLS_PROPERTIES = {
    "server.ssl.enabled": True,
    "opensearch.ssl.verificationMode": "full",
    "opensearch_security.cookie.secure": True,
}

LOG_PROPERTIES = {
    "logging.verbose": True,
}


class ConfigManager:
    """Manager for for handling configuration building + writing."""

    def __init__(
        self,
        state: ClusterState,
        workload: WorkloadBase,
        substrate: SUBSTRATES,
        config: ConfigData,
    ):
        self.state = state
        self.workload = workload
        self.substrate = substrate
        self.config = config

    @property
    def log_level(self) -> str:
        """Return the Opensearch-compilant logging level set by the user.

        Returns:
            String with these possible values: DEBUG, INFO, WARN, ERROR
        """
        # FIXME: use pydantic config models for this validation instead
        permitted_levels = ["INFO", "WARNING", "ERROR"]
        config_log_level = self.config["log_level"]

        if config_log_level not in permitted_levels:
            logger.error(
                f"Invalid log_level config value of {config_log_level}. "
                f"Must be one of {','.join(permitted_levels)}. Defaulting to 'INFO'"
            )
            config_log_level = "INFO"

        # Remapping to WARN that is generally used in Java applications based on log4j and logback.
        if config_log_level == "WARNING":
            return "logging.quiet"
        elif config_log_level == "INFO":
            return "logging.verbose"
        elif config_log_level == "ERROR":
            return "logging.silent"

        return ""

    @property
    def dashboard_properties(self) -> dict[str, Any]:
        """Build the opensearch_dashboards.yml content.

        As we are building on top of the known templates above, we do not need to care about
        merging lists, for example. We will override the default properties if needed.

        Returns:
            List of properties to be set to opensearch_dashboards.yml config file
        """
        properties = DEFAULT_PROPERTIES.copy()

        opensearch_user = (
            self.state.opensearch_server.username if self.state.opensearch_server else ""
        )
        opensearch_password = (
            self.state.opensearch_server.password if self.state.opensearch_server else ""
        )

        if self.state.opensearch_server and len(self.state.opensearch_server.endpoints) > 0:
            properties["opensearch.hosts"] = [
                f"https://{endpoint}" for endpoint in self.state.opensearch_server.endpoints
            ]

        opensearch_ca = self.workload.paths.opensearch_ca if self.state.opensearch_server else None

        # We are using the address exposed by Juju as service address
        properties["server.host"] = str(self.state.bind_address)
        if opensearch_user and opensearch_password:
            properties |= {
                "opensearch.username": opensearch_user,
                "opensearch.password": opensearch_password,
            }

        if opensearch_ca:
            properties["opensearch.ssl.certificateAuthorities"] = [opensearch_ca]

        if self.state.unit_server.tls:
            properties |= TLS_PROPERTIES
            properties |= {
                "server.ssl.certificate": self.workload.paths.certificate,
                "server.ssl.key": self.workload.paths.server_key,
            }

        if self.state.oauth_relation:
            properties |= {
                "opensearch_security.auth.type": ["basicauth", "openid"],
                "opensearch_security.auth.multiple_auth_enabled": True,
                "opensearch_security.openid.connect_url": f"{self.state.oauth.issuer_url}/.well-known/openid-configuration",
                "opensearch_security.openid.client_id": self.state.oauth.client_id,
                "opensearch_security.openid.client_secret": self.state.oauth.client_secret,
                "opensearch_security.openid.verify_hostnames": False,
                "opensearch_security.openid.root_ca": opensearch_ca,
                "opensearch_security.openid.base_redirect_url": self.state.url,
            }

        # Log-level
        properties[self.log_level] = True

        # Paths
        properties["path.data"] = self.workload.paths.data_path

        return properties

    @property
    def current_properties(self) -> list[str]:
        """The current configuration properties set to zoo.cfg."""
        return self.workload.read(self.workload.paths.properties)

    def set_dashboard_properties(self) -> None:
        """Writes built config file."""
        self.workload.write(
            content=yaml.dump(self.dashboard_properties),
            path=self.workload.paths.properties,
        )

    def load_dashboard_properties(self) -> dict[str, Any]:
        """Reads built config file."""
        return yaml.safe_load(
            "\n".join(
                self.workload.read(
                    path=self.workload.paths.properties,
                )
            )
        )

    def config_changed(self) -> bool:
        """Compares expected vs actual config that would require a restart to apply."""
        if self.load_dashboard_properties() == self.dashboard_properties:
            return False
        self.set_dashboard_properties()
        return True
