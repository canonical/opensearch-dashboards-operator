#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Operator for Apache Opensearch Dashboards."""

import logging

from ops.log import JujuLogHandler
from ops.main import main
from single_kernel_opensearch_dashboards.charms.k8s import OpenSearchDashboardsK8sCharm

# Show logger name (module name) in logs
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if isinstance(handler, JujuLogHandler):
        handler.setFormatter(logging.Formatter("{name}:{message}", style="{"))
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

if __name__ == "__main__":
    main(OpenSearchDashboardsK8sCharm)
