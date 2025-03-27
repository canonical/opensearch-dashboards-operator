#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for Apache Opensearch Dashboards."""

import json
import logging

from charms.tls_certificates_interface.v3.tls_certificates import CharmBase
from data_platform_helpers.version_check import get_charm_revision
from ops.model import ActiveStatus, Application, StatusBase, Unit

logger = logging.getLogger(__name__)


def clear_status(scope_obj: Unit | Application, messages: str | list[str]) -> None:
    """Clear status if set."""
    if not isinstance(messages, list):
        messages = [messages]

    if any([scope_obj.status.message == message for message in messages]):
        logger.debug(f"Clearing status {messages} from {scope_obj}.")
        scope_obj.status = ActiveStatus()


def set_global_status(charm: CharmBase, status: StatusBase | None):
    """Set status on all possible levels."""
    if not status:
        return

    charm.unit.status = status
    if charm.unit.is_leader():
        charm.app.status = status


def clear_global_status(charm: CharmBase, status: str | None):
    """Clear status on all levels."""
    if not status:
        return
    clear_status(charm.unit, status)
    if charm.unit.is_leader():
        clear_status(charm.app, status)


def update_grafana_dashboards_title(charm: CharmBase) -> None:
    """Update the title of the Grafana dashboard file to include the charm revision."""
    revision = get_charm_revision(charm.model.unit)
    dashboard_path = charm.charm_dir / "src/grafana_dashboards/dashboard.json"

    with open(dashboard_path, "r") as file:
        dashboard = json.load(file)

    old_title = dashboard.get("title", "Charmed OpenSearch Dashboards")
    title_prefix = old_title.split(" - Rev")[0]
    new_title = f"{old_title} - Rev {revision}"
    dashboard["title"] = f"{title_prefix} - Rev {revision}"

    logger.info(
        "Changing the title of dashboard %s from %s to %s",
        dashboard_path.name,
        old_title,
        new_title,
    )

    with open(dashboard_path, "w") as file:
        json.dump(dashboard, file, indent=4)
