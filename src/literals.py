#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of global literals for the charm."""

OPENSEARCH_DASHBOARDS_SNAP_REVISION = "18"

SUBSTRATE = "vm"
CHARM_KEY = "opensearch-dashboards"

PEER = "dashboard_peers"
OPENSEARCH_REL_NAME = "opensearch-client"
CERTS_REL_NAME = "certificates"
DASHBOARD_INDEX = ".opensearch-dashboards"
DASHBOARD_USER = "kibanaserver"
DASHBOARD_ROLE = "kibana_server"
CONTAINER = "opensearch-dashboards"
SERVER_PORT = 5601

DEPENDENCIES = {
    "osd_upstream": {
        "dependencies": {"opensearch": "2.14"},
        "name": "opensearch-dashboards",
        "upgrade_supported": ">=2",
        "version": "2.14",
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
MSG_WAITING_FOR_PEER = "waiting for peer relation"
MSG_DB_MISSING = "Opensearch connection is missing"
MSG_TLS_CONFIG = "Waiting for TLS to be fully configured..."
MSG_INCOMPATIBLE_UPGRADE = "Incompatible upgrade, rollback required"

MSG_STATUS_UNAVAIL = "Service unavailable"
MSG_STATUS_UNHEALTHY = "Service is not in a green health state"
MSG_STATUS_ERROR = "Service is an error state"
MSG_STATUS_WORKLOAD_DOWN = "Workload is not alive"
MSG_STATUS_UNKNOWN = "Workload status is not known"

MSG_STATUS = [
    MSG_STATUS_UNAVAIL,
    MSG_STATUS_UNHEALTHY,
    MSG_STATUS_WORKLOAD_DOWN,
    MSG_STATUS_UNKNOWN,
]

# COS

COS_RELATION_NAME = "cos-agent"
COS_PORT = 9684
