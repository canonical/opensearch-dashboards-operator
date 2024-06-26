#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of global literals for the charm."""

OPENSEARCH_DASHBOARDS_SNAP_REVISION = "9"

SUBSTRATE = "vm"
CHARM_KEY = "opensearch-dashboards"

PEER = "dashboard_peers"
OPENSEARCH_REL_NAME = "opensearch_client"
CERTS_REL_NAME = "certificates"
DASHBOARD_INDEX = ".opensearch-dashboards"
DASHBOARD_USER = "kibanaserver"
DASHBOARD_ROLE = "kibana_server"
CONTAINER = "opensearch-dashboards"
CHARM_USERS = ["monitor"]
SERVER_PORT = 5601

DEPENDENCIES = {
    "osd_upstream": {
        "dependencies": {"opensearch": "2.13"},
        "name": "opensearch-dashboards",
        "upgrade_supported": ">=2",
        "version": "2.13",
    },
}

PATHS = {
    "CONF": "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards",
    "DATA": "/var/snap/opensearch-dashboards/common/var/lib/opensearch-dashboards",
    "LOGS": "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards",
    "BIN": "/snap/opensearch-dashboards/current/opt/opensearch-dashboards",
}

PEER_APP_SECRETS = [
    "monitor-username",
    "monitor-password",
]
PEER_UNIT_SECRETS = ["ca-cert", "csr", "certificate", "private-key"]

RESTART_TIMEOUT = 30


# Status messages

MSG_INSTALLING = "installing Opensearch Dashboards..."
MSG_STARTING = "starting..."
MSG_STARTING_SERVER = "starting Opensearch Dashboards server..."
MSG_WAITING_FOR_USER_CREDENTIALS = "waiting for passwords to be created"
MSG_WAITING_FOR_PEER = "waiting for peer relation"
MSG_DB_MISSING = "Opensearch connection is missing"
MSG_TLS_CONFIG = "Waiting for TLS to be fully configured..."
MSG_INCOMPATIBLE_UPGRADE = "Incompatible upgrade, rollback required"
