#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of global literals for the ZooKeeper charm."""

OPENSEARCH_DASHBOARDS_SNAP_REVISION = 8

SUBSTRATE = "vm"
CHARM_KEY = "opensearch-dashboards"

PEER = "dashboard_peers"
OPENSEARCH_REL_NAME = "opensearch_client"
# DASHBOARD_INDEX = ".opensearch-dashboards"
DASHBOARD_INDEX = "admin-index"
CONTAINER = "opensearch-dashboards"
CHARM_USERS = ["admin", "kibanaserver"]
CERTS_REL_NAME = "certificates"
# CLIENT_PORT = 2181
# SECURE_CLIENT_PORT = 2182
SERVER_PORT = 5601
# JMX_PORT = 9998
# METRICS_PROVIDER_PORT = 7000

DEPENDENCIES = {
    "service": {
        "dependencies": {},
        "name": "zookeeper",
        "upgrade_supported": "^3.5",
        "version": "3.8.2",
    },
}

PATHS = {
    "CONF": "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards",
    "DATA": "/var/snap/opensearch-dashboards/common/var/lib/opensearch-dashboards",
    "LOGS": "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards",
    "BIN": "/snap/opensearch-dashboards/current/opt/opensearch-dashboards",
}

PEER_APP_SECRETS = [
    "admin-username",
    "admin-password",
    "kibanaserver-username",
    "kibanaserver-password",
]
PEER_UNIT_SECRETS = ["ca-cert", "csr", "certificate", "private-key"]
