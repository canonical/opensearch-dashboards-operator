#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of global literals for the charm."""

OPENSEARCH_DASHBOARDS_SNAP_REVISION = "41"

SUBSTRATE = "vm"
CHARM_KEY = "opensearch-dashboards"

PEER = "dashboard_peers"
OPENSEARCH_REL_NAME = "opensearch-client"
CERTS_REL_NAME = "certificates"
OAUTH_REL_NAME = "oauth"
DASHBOARD_INDEX = ".opensearch-dashboards"
DASHBOARD_USER = "kibanaserver"
DASHBOARD_ROLE = "kibana_server"
CONTAINER = "opensearch-dashboards"
SERVER_PORT = 5601

DEPENDENCIES = {
    "osd_upstream": {
        "dependencies": {"opensearch": "2.19.2"},
        "name": "opensearch-dashboards",
        "upgrade_supported": ">=2",
        "version": "2.19.2",
    },
}

PATHS = {
    "CONF": "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards",
    "DATA": "/var/snap/opensearch-dashboards/common/var/lib/opensearch-dashboards",
    "LOGS": "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards",
    "BIN": "/snap/opensearch-dashboards/current/opt/opensearch-dashboards",
}

PEER_APP_SECRETS = ["monitor-username", "monitor-password", "oauth-client-secret"]
PEER_UNIT_SECRETS = ["ca-cert", "csr", "certificate", "private-key"]

RESTART_TIMEOUT = 30
SERVICE_AVAILABLE_TIMEOUT = 90
REQUEST_TIMEOUT = 30


# Status messages

MSG_INSTALLING = "installing Opensearch Dashboards..."
MSG_STARTING = "starting..."
MSG_STARTING_SERVER = "starting Opensearch Dashboards server..."
MSG_WAITING_FOR_PEER = "waiting for peer relation"
MSG_STATUS_DB_MISSING = "Opensearch connection is missing"
MSG_STATUS_DB_DOWN = "Opensearch service is (partially or fully) down"
MSG_TLS_CONFIG = "Waiting for TLS to be fully configured..."
MSG_INCOMPATIBLE_UPGRADE = "Incompatible Opensearch and Dashboards versions"

MSG_STATUS_UNAVAIL = "Service unavailable"
MSG_STATUS_UNHEALTHY = "Service is not in a green health state"
MSG_STATUS_ERROR = "Service is an error state"
MSG_STATUS_WORKLOAD_DOWN = "Workload is not alive"
MSG_STATUS_UNKNOWN = "Workload status is not known"
MSG_STATUS_APP_REMOVED = "remove-application was requested: leaving..."
MSG_STATUS_HANGING = "Application does not respond, request hanging"

MSG_APP_STATUS = [
    MSG_STATUS_DB_DOWN,
]

MSG_UNIT_STATUS = [
    MSG_STATUS_HANGING,
    MSG_STATUS_UNAVAIL,
    MSG_STATUS_UNHEALTHY,
    MSG_STATUS_WORKLOAD_DOWN,
    MSG_STATUS_UNKNOWN,
]

# COSG

COS_RELATION_NAME = "cos-agent"
COS_PORT = 9684

HEALTH_OPENSEARCH_STATUS_URL = "_cluster/health"
