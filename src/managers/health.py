#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling Kafka machine health."""

import logging

from requests.exceptions import ConnectionError, HTTPError

from core.cluster import SUBSTRATES, ClusterState
from core.workload import WorkloadBase
from exceptions import OSDAPIError
from literals import (
    MSG_STATUS_ERROR,
    MSG_STATUS_UNAVAIL,
    MSG_STATUS_UNHEALTHY,
    MSG_STATUS_UNKNOWN,
    MSG_STATUS_WORKLOAD_DOWN,
)
from managers.api import APIManager

logger = logging.getLogger(__name__)


class HealthManager:
    """Manager for handling Kafka machine health."""

    def __init__(
        self,
        state: ClusterState,
        workload: WorkloadBase,
        substrate: SUBSTRATES,
    ):
        self.state = state
        self.workload = workload
        self.substrate = substrate
        self.api_manager = APIManager(state, workload, substrate)

    def status_ok(self) -> tuple[bool, str]:
        """Health status"""
        try:
            status_data = self.api_manager.service_status()
        except HTTPError as err:
            if err.response.status_code == 503:
                return False, MSG_STATUS_UNAVAIL
        except (ConnectionError, OSDAPIError):
            return False, MSG_STATUS_UNAVAIL

        if status_data["status"]["overall"]["state"] == "green":
            return True, ""
        elif status_data["status"]["overall"]["state"] == "yellow":
            return True, MSG_STATUS_UNHEALTHY
        elif status_data["status"]["overall"]["state"] != "green":
            return False, MSG_STATUS_ERROR
        return True, MSG_STATUS_UNKNOWN

    def healthy(self) -> tuple[bool, str]:
        """Unit-level global healthcheck."""
        if not self.workload.alive:
            return False, MSG_STATUS_WORKLOAD_DOWN

        return self.status_ok()
