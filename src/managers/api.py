#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for for handling API access."""
import json
import logging
from typing import TYPE_CHECKING, Any

import requests
from requests.exceptions import RequestException

from exceptions import OSDAPIError

if TYPE_CHECKING:
    pass

from core.cluster import SUBSTRATES, ClusterState
from core.workload import WorkloadBase

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "osd-xsrf": "osd-true",
}


class APIManager:
    """Manager for for handling configuration building + writing."""

    def __init__(
        self,
        state: ClusterState,
        workload: WorkloadBase,
        substrate: SUBSTRATES,
    ):
        self.state = state
        self.workload = workload
        self.substrate = substrate

    # =================================
    #  Opensearch connection functions
    # =================================

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        headers: dict = HEADERS,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP(S) request to the OSD Rest API.

        Args:
            method: matching the known http methods.
            headers: request headers as a dict
            endpoint: relative to the base uri.
            payload: JSON / map body payload.
        """

        if None in [endpoint, method]:
            raise ValueError("endpoint or method missing")

        full_url = f"{self.state.unit_server.url}/api/{endpoint}"

        request_kwargs = {
            "verify": self.workload.paths.ca,
            "method": method.upper(),
            "url": full_url,
            "headers": headers,
        }

        request_kwargs["data"] = json.dumps(payload)
        request_kwargs["headers"] = headers

        if not self.state.opensearch_server:
            raise OSDAPIError("No Opensearch connection, can't query API (missing credentials).")

        try:
            with requests.Session() as s:
                s.auth = (  # type: ignore [reportAttributeAccessIssue]
                    self.state.opensearch_server.username,
                    self.state.opensearch_server.password,
                )
                resp = s.request(**request_kwargs)
                resp.raise_for_status()
        except RequestException as e:
            logger.error(f"Request {method} to {full_url} with payload: {payload} failed. \n{e}")
            raise

        return resp.json()

    def service_status(self) -> dict[str, Any]:
        """Query service status from the OSD API."""
        return self.request(endpoint="status")
