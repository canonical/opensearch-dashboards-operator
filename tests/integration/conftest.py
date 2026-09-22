#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import os
import subprocess
from typing import Literal

import pytest

logger = logging.getLogger(__name__)

OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_K8S_CHARM = "opensearch-k8s"


@pytest.fixture(autouse=True, scope="module")
def opensearch_sysctl_settings():
    """Necessary settings for Opensearch

    This should probably rather go to ci.yaml"""
    subprocess.run(["sudo", "sysctl", "-w", "vm.swappiness=0"])
    subprocess.run(["sudo", "sysctl", "-w", "vm.max_map_count=262144"])
    subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.tcp_retries2=5"])


@pytest.fixture(scope="session")
def substrate() -> Literal["k8s", "vm"]:
    """Returns the substrate"""
    sub = os.environ.get("SUBSTRATE", "vm").lower()
    if sub not in ("k8s", "vm"):
        raise ValueError(
            f"Substrate has invalid value. Correct values are k8s, vm. Current value {sub}."
        )
    return sub


@pytest.fixture
def charm_base():
    """Returns the base in the modern format, e.g., 'ubuntu@22.04'."""
    base_version = os.environ.get("CHARM_UBUNTU_BASE", "24.04")
    return f"ubuntu@{base_version}"


@pytest.fixture
def charm(charm_base, substrate):
    """Path to the dashboards charm file to use for testing."""
    # Return str instead of pathlib.Path since python-lib juju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    if substrate == "k8s":
        return f"./kubernetes/opensearch-dashboards-k8s_{charm_base}-amd64.charm"
    return f"./machine/opensearch-dashboards_{charm_base}-amd64.charm"


@pytest.fixture
def opensearch_deploy_args(substrate) -> tuple[str, bool]:
    """Returns (charm, trust) for deploying OpenSearch on the current substrate."""
    if substrate == "k8s":
        return OPENSEARCH_K8S_CHARM, True
    return OPENSEARCH_APP_NAME, False


@pytest.fixture
def application_charm() -> str:
    """Path to the application charm to use for testing."""
    return "./tests/integration/dashboards_application_charm/application_ubuntu@24.04-amd64.charm"


def pytest_configure(config):
    if os.environ.get("SUBSTRATE", "vm").lower() == "k8s":
        k8s_cloud = os.environ.get("K8S_CLOUD", "uk8s")
        if not getattr(config.option, "cloud", None):
            config.option.cloud = k8s_cloud


class Flags:
    def __init__(self):
        self.test_tls = os.environ.get("TEST_TLS", "false").lower() == "true"
        self.traefik = os.environ.get("TEST_TRAEFIK", "false").lower() == "true"
        self.transfer_traefik_ca = os.environ.get("TRANSFER_TRAEFIK_CA", "false").lower() == "true"
        if self.transfer_traefik_ca and not self.traefik:
            raise ValueError("TRANSFER_TRAEFIK_CA=true requires TEST_TRAEFIK=true.")


@pytest.fixture(scope="class")
def test_flags() -> Flags:
    """Fixture to provide TLS and Traefik configuration groups from Spread."""
    return Flags()
