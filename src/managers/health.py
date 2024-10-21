#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling service health."""

import logging
import os

import requests
from requests.exceptions import ConnectionError, HTTPError

from core.cluster import SUBSTRATES, ClusterState
from core.workload import WorkloadBase
from exceptions import OSDAPIError
from literals import (
    HEALTH_OPENSEARCH_STATUS_URL,
    MSG_STATUS_APP_REMOVED,
    MSG_STATUS_DB_DOWN,
    MSG_STATUS_DB_MISSING,
    MSG_STATUS_ERROR,
    MSG_STATUS_HANGING,
    MSG_STATUS_UNAVAIL,
    MSG_STATUS_UNHEALTHY,
    MSG_STATUS_UNKNOWN,
    MSG_STATUS_WORKLOAD_DOWN,
    REQUEST_TIMEOUT,
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
            return False, MSG_STATUS_UNKNOWN
        except (ConnectionError, OSDAPIError):
            return False, MSG_STATUS_UNAVAIL
        except requests.ReadTimeout:
            return False, MSG_STATUS_HANGING

        if status_data["status"]["overall"]["state"] == "green":
            return True, ""
        elif status_data["status"]["overall"]["state"] == "yellow":
            return True, MSG_STATUS_UNHEALTHY
        elif status_data["status"]["overall"]["state"] != "green":
            return False, MSG_STATUS_ERROR
        return True, MSG_STATUS_UNKNOWN

    def opensearch_ok(self) -> tuple[bool, str]:
        """Verify if associated Opensearch service is up and running."""

        if not self.state.url:
            return False, MSG_STATUS_APP_REMOVED

        if not self.state.opensearch_server or not (
            os.path.exists(self.workload.paths.opensearch_ca)
            and os.path.getsize(self.workload.paths.opensearch_ca) > 0
        ):
            return False, MSG_STATUS_DB_MISSING

        for endpoint in self.state.opensearch_server.endpoints:
            full_url = f"https://{endpoint}/{HEALTH_OPENSEARCH_STATUS_URL}"

            request_kwargs = {
                "url": full_url,
                "method": "GET",
                "verify": self.workload.paths.opensearch_ca,
                "headers": None,
                "timeout": REQUEST_TIMEOUT,
            }

            try:
                with requests.Session() as s:
                    s.auth = (  # type: ignore [reportAttributeAccessIssue]
                        self.state.opensearch_server.username,
                        self.state.opensearch_server.password,
                    )
                    resp = s.request(**request_kwargs)
                    resp.raise_for_status()
            except requests.exceptions.RequestException:
                continue

            if resp.status_code == 200:
                try:
                    status = resp.json()
                except requests.exceptions.JSONDecodeError:
                    continue
                if status.get("status") == "green":
                    return True, ""

        return False, MSG_STATUS_DB_DOWN

    def app_healthy(self) -> tuple[bool, str]:
        """Unit-level global healthcheck."""
        return self.opensearch_ok()

    def unit_healthy(self) -> tuple[bool, str]:
        """Unit-level global healthcheck."""
        if not self.workload.alive:
            return False, MSG_STATUS_WORKLOAD_DOWN

        return self.status_ok()
