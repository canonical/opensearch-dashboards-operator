#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for for handling OSD REST API access."""
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
from literals import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "osd-xsrf": "osd-true",
}


class APIManager:
    """Manager for for handling OSD REST API access."""

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
        """Issue a "raw"" HTTP(S) request to the OSD Rest API.

        Thin wrapper around the Python 'requests' call to access OSD API.
        Catching no errors/exceptions.

        Args:
            method: matching the known http methods.
            headers: request headers as a dict
            endpoint: relative to the base uri.
            payload: JSON / map body payload.

        Raises:
            ReadTimeout: We distinguish if the service was fully unresponsive
            RequestException (including any descendants from requests.exceptions)
        """

        if None in [endpoint, method]:
            raise ValueError("endpoint or method missing")

        full_url = f"{self.state.url}/api/{endpoint}"

        request_kwargs = {
            "verify": self.workload.paths.ca,
            "method": method.upper(),
            "url": full_url,
            "headers": headers,
            "timeout": REQUEST_TIMEOUT,
        }

        request_kwargs["data"] = json.dumps(payload)
        request_kwargs["headers"] = headers

        if not self.state.opensearch_server:
            raise OSDAPIError(
                "Can't query OSD API, no Opensearch connection (i.e. no OSD credentials)."
            )

        try:
            with requests.Session() as s:
                s.auth = (  # type: ignore [reportAttributeAccessIssue]
                    self.state.opensearch_server.username,
                    self.state.opensearch_server.password,
                )
                resp = s.request(**request_kwargs)
                resp.raise_for_status()
        except requests.ReadTimeout as e:
            logger.error(f"Hanging, no response from {full_url}: {e}.")
            raise
        except RequestException as e:
            logger.error(f"Request {method} to {full_url} with payload: {payload} failed. \n{e}")
            raise

        return resp.json()

    def service_status(self) -> dict[str, Any]:
        """Query service status from the OSD API.

        A think wrapper around the Python 'requests' call to OSD API status endpoint.
        No errors/exceptions are handled.

        Raises:
            RequestException (including any descendants from requests.exceptions)
        """
        return self.request(endpoint="status")
