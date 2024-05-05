#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for building necessary files for Java TLS auth."""
import logging
import subprocess
from subprocess import STDOUT, CalledProcessError

import ops.pebble

from core.cluster import SUBSTRATES, ClusterState
from core.workload import WorkloadBase

logger = logging.getLogger(__name__)


class TLSManager:
    """Manager for building necessary files for Java TLS auth."""

    def __init__(self, state: ClusterState, workload: WorkloadBase, substrate: SUBSTRATES):
        self.state = state
        self.workload = workload
        self.substrate = substrate

    def set_private_key(self) -> None:
        """Sets the unit private-key."""
        if not self.state.unit_server.private_key:
            logger.error("Can't set private-key to unit, missing private-key in relation data")
            return

        self.workload.write(
            content=self.state.unit_server.private_key, path=self.workload.paths.server_key
        )

    def set_ca(self) -> None:
        """Sets the unit CA."""
        if not self.state.unit_server.ca:
            logger.error("Can't set CA to unit, missing CA in relation data")
            return

        self.workload.write(content=self.state.unit_server.ca, path=self.workload.paths.ca)

    def set_certificate(self) -> None:
        """Sets the unit certificate."""
        if not self.state.unit_server.certificate:
            logger.error("Can't set certificate to unit, missing certificate in relation data")
            return

        self.workload.write(
            content=self.state.unit_server.certificate, path=self.workload.paths.certificate
        )

    def remove_cert_files(self) -> None:
        """Removes all certs, keys, stores from the unit."""
        try:
            self.workload.exec(
                command=[
                    "rm",
                    "-rf",
                    f"{self.workload.paths.conf_path}/*.pem",
                    f"*{self.workload.paths.conf_path}/*.key",
                    f"*{self.workload.paths.conf_path}/*.p12",
                    f"*{self.workload.paths.conf_path}/*.jks",
                ],
                working_dir=self.workload.paths.conf_path,
            )
        except (subprocess.CalledProcessError, ops.pebble.ExecError) as e:
            logger.error(str(e.stdout))
            raise e

    def certificate_valid(self) -> bool:
        """Check if server certificate is valid"""
        cmd = f"openssl x509 -in {self.workload.paths.certificate} -subject -noout"
        try:
            response = subprocess.check_output(
                cmd, stderr=STDOUT, shell=True, universal_newlines=True
            )
        except CalledProcessError as error:
            logging.error(f"Checking certificate failed: {error.output}")
            return False
        return self.state.unit_server.private_ip in response
