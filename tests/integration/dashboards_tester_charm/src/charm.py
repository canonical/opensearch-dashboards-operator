#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

import requests
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class DashboardTesterCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.request_action, self._on_request)

    def _on_request(self, event):
        url = event.params["url"]
        method = event.params["method"]
        username = event.params.get("username")
        password = event.params.get("password")
        ca_cert = event.params.get("ca_cert")
        payload = event.params.get("payload")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "osd-xsrf": "true",
        }

        verify_arg = False
        if ca_cert:
            cert_path = "/tmp/ca.pem"
            with open(cert_path, "w") as f:
                f.write(ca_cert)
            verify_arg = cert_path

        try:
            auth = (username, password) if username and password else None

            if method.upper() == "POST" and url.endswith("/auth/login") and not payload:
                data = {"username": username, "password": password}
                resp = requests.post(
                    url, json=data, headers=headers, verify=verify_arg, timeout=10
                )
            else:
                kwargs = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "verify": verify_arg,
                    "timeout": 10,
                }
                if auth:
                    kwargs["auth"] = auth
                if payload:
                    kwargs["data"] = payload

                resp = requests.request(**kwargs)

            event.set_results({"status": resp.status_code, "text": resp.text})
        except Exception as e:
            event.fail(f"Request failed: {str(e)}")


if __name__ == "__main__":
    main(DashboardTesterCharm)
