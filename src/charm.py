#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Operator for Apache Opensearch Dashboards."""

import logging
import os

from ops.log import JujuLogHandler
from ops.main import main
from single_kernel_opensearch_dashboards.charms.k8s import OpenSearchDashboardsK8sCharm
from single_kernel_opensearch_dashboards.charms.vm import OpenSearchDashboardsVMCharm

# Show logger name (module name) in logs
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if isinstance(handler, JujuLogHandler):
        handler.setFormatter(logging.Formatter("{name}:{message}", style="{"))
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def is_k8s():
    return "KUBERNETES_SERVICE_HOST" in os.environ


if __name__ == "__main__":
    if is_k8s():
        main(OpenSearchDashboardsK8sCharm)
    else:
        main(OpenSearchDashboardsVMCharm)
