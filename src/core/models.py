#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of state objects for relations, apps and units."""
import logging
import socket
from typing import Literal, MutableMapping

import requests
from charms.data_platform_libs.v0.data_interfaces import Data, DataDict
from ops import Secret
from ops.model import Application, Relation, Unit
from typing_extensions import override

logger = logging.getLogger(__name__)

SUBSTRATES = Literal["vm", "k8s"]


class StateBase:
    """Base state object."""

    def __init__(
        self,
        relation: Relation | None,
        data_interface: Data,
        component: Unit | Application,
        substrate: SUBSTRATES,
    ):
        self.relation = relation
        self.data_interface = data_interface
        self.component = component
        self.substrate = substrate
        self._relation_data = (
            self.data_interface.as_dict(self.relation.id) if self.relation else {}
        )

    @property
    def relation_data(self) -> MutableMapping[str, str]:
        """The raw relation data."""
        return self._relation_data.data if isinstance(self._relation_data, DataDict) else {}

    def update(self, items: dict[str, str]) -> None:
        """Writes to relation_data."""
        if not self.relation or not self.data_interface:
            return

        delete_fields = [key for key in items if not items[key]]
        update_fields = {k: items[k] for k in items if k not in delete_fields}

        if update_fields:
            self._relation_data.update(update_fields)
        for field in delete_fields:
            del self._relation_data[field]


class OpensearchServer(StateBase):
    """State collection metadata for a single related client application."""

    def __init__(
        self,
        relation: Relation | None,
        data_interface: Data,
        component: Application,
        substrate: SUBSTRATES,
        local_app: Application | None = None,
        password: str = "",
        endpoints: str = "",
    ):
        super().__init__(relation, data_interface, component, substrate)
        self.app = component
        self._password = password
        self._endpoints = endpoints
        self._local_app = local_app

    @override
    def update(self, items: dict[str, str]) -> None:
        """Overridden update to allow for same interface, but writing to local app bag."""
        if not self.relation or not self._local_app:
            return

        self.data_interface.update_relation_data(self.relation.id, items)

    @property
    def username(self) -> str | None:
        """The generated username for the client application."""
        return "kibanaserver"

    @property
    def password(self) -> str | None:
        """The generated password for the client application."""
        return self.relation_data.get("password")

    @property
    def endpoints(self) -> list[str]:
        """Connection endpoints for the client application to connect with."""
        endpoints_str = self.relation_data.get("endpoints")
        return sorted(endpoints_str.split(",")) if endpoints_str else []

    @property
    def tls_ca(self) -> str | None:
        """The CA cert in case TLS is enabled.

        Returns:
            String of either 'enabled' or 'disabled'
        """
        return self.relation_data.get("tls-ca")

    @property
    def version(self) -> str | None:
        """Opensearch version."""
        return self.relation_data.get("version")


class ODCluster(StateBase):
    """State collection metadata for the charm application."""

    def __init__(
        self,
        relation: Relation | None,
        data_interface: Data,
        component: Application,
        substrate: SUBSTRATES,
        tls: bool | None = False,
    ):
        super().__init__(relation, data_interface, component, substrate)
        self._tls = tls
        self.app = component

    # -- TLS --

    @property
    def tls(self) -> bool:
        """Flag to check if TLS is enabled for the cluster."""
        return bool(self._tls)

    @property
    def oauth_client_secret(self) -> str:
        """Client secret of the Oauth relation."""
        return self.relation_data.get("oauth-client-secret", "")


class ODServer(StateBase):
    """State collection metadata for a charm unit."""

    def __init__(
        self,
        relation: Relation | None,
        data_interface: Data,
        component: Unit,
        substrate: SUBSTRATES,
    ):
        super().__init__(relation, data_interface, component, substrate)
        self.unit = component

    @property
    def unit_id(self) -> int:
        """The id of the unit from the unit name.

        e.g opensearch-dashboards/2 --> 2
        """
        return int(self.component.name.split("/")[1])

    # -- Cluster Init --

    @property
    def started(self) -> bool:
        """Flag to check if the unit has started the service."""
        return self.relation_data.get("state", None) == "started"

    @property
    def password_rotated(self) -> bool:
        """Flag to check if the unit has rotated their internal passwords."""
        return bool(self.relation_data.get("password-rotated", None))

    @property
    def hostname(self) -> str:
        """The hostname for the unit."""
        return socket.gethostname()

    @property
    def fqdn(self) -> str:
        """The Fully Qualified Domain Name for the unit."""
        # return socket.getfqdn(self.private_ip)
        return socket.getfqdn(self.private_ip)

    @property
    def private_ip(self) -> str:
        """The IP for the unit recovered using socket."""
        return socket.gethostbyname(self.hostname)

    @property
    def public_ip(self) -> str:
        """The public IP for the unit."""
        return socket.gethostbyname(self.hostname)

    @property
    def host(self) -> str:
        """The hostname for the unit."""
        host = ""
        if self.substrate == "vm":
            for key in ["hostname", "ip", "private-address"]:
                if host := self.relation_data.get(key, ""):
                    break

        if self.substrate == "k8s":
            host = f"{self.component.name.split('/')[0]}-{self.unit_id}.{self.component.name.split('/')[0]}-endpoints"

        return host

    # -- TLS --

    @property
    def private_key(self) -> str:
        """The private-key contents for the unit to use for TLS."""
        return self.relation_data.get("private-key", "")

    @property
    def csr(self) -> str:
        """The current certificate signing request contents for the unit."""
        return self.relation_data.get("csr", "")

    @property
    def certificate(self) -> str:
        """The certificate contents for the unit to use for TLS."""
        return self.relation_data.get("certificate", "")

    @property
    def ca(self) -> str:
        """The root CA contents for the unit to use for TLS."""
        return self.relation_data.get("ca-cert", "")

    @property
    def tls(self) -> bool:
        """Flag to check if TLS is enabled for the cluster."""
        return bool(self.ca) and bool(self.certificate) and bool(self.private_key)

    @property
    def sans(self) -> dict[str, list[str]]:
        """The Subject Alternative Name for the unit's TLS certificates."""
        if not all([self.private_ip, self.hostname, self.fqdn]):
            return {}

        return {
            "sans_ip": [self.private_ip, self.public_ip],
            "sans_dns": [dns for dns in {self.hostname, self.fqdn} if dns],
        }


class OAuth:
    """State collection metadata for the oauth relation."""

    def __init__(self, relation: Relation | None, client_secret: str):
        self.relation = relation
        self._client_secret = client_secret

    @property
    def relation_data(self) -> MutableMapping[str, str]:
        """Oauth relation data object."""
        if not self.relation or not self.relation.app:
            return {}

        return self.relation.data[self.relation.app]

    @property
    def issuer_url(self) -> str:
        """The issuer URL to identify the IDP."""
        return self.relation_data.get("issuer_url", "")

    @property
    def client_id(self) -> str:
        """Client ID created by Hydra."""
        return self.relation_data.get("client_id", "")

    @property
    def client_secret(self) -> str:
        """Client secret created by Hydra."""
        return self._client_secret

    @property
    def jwks_endpoint(self) -> str:
        """The JWKS endpoint needed to validate JWT tokens."""
        return self.relation_data.get("jwks_endpoint", "")

    @property
    def introspection_endpoint(self) -> str:
        """The introspection endpoint needed to validate non-JWT tokens."""
        return self.relation_data.get("introspection_endpoint", "")

    @property
    def jwt_access_token(self) -> bool:
        """A flag indicating if the access token is JWT or not."""
        return self.relation_data.get("jwt_access_token", "false").lower() == "true"

    @property
    def uses_trusted_ca(self) -> bool:
        """A flag indicating if the IDP uses certificates signed by a trusted CA."""
        try:
            requests.get(self.issuer_url, timeout=10)
            return True
        except requests.exceptions.SSLError:
            return False
        except requests.exceptions.RequestException:
            return True
