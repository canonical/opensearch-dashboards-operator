#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import os
import subprocess
from asyncio import sleep
from typing import Any, AsyncGenerator, Literal

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


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
def charmvm(charm_base):
    """Path to the charm file to use for testing."""
    # Return str instead of pathlib.Path since python-lib juju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./machine/opensearch-dashboards_{charm_base}-amd64.charm"


@pytest.fixture
def charmk8s(charm_base):
    """Path to the charm file to use for testing."""
    # Return str instead of pathlib.Path since python-lib juju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./kubernetes/opensearch-dashboards-k8s_{charm_base}-amd64.charm"


@pytest.fixture
def application_charm() -> str:
    """Path to the application charm to use for testing."""
    return "./tests/integration/dashboards_application_charm/application_ubuntu@24.04-amd64.charm"


@pytest.fixture
def dashboard_tester_charm() -> str:
    """Path to the application charm to use for testing k8s."""
    return "./tests/integration/dashboards_tester_charm/dashboard-tester_ubuntu@24.04-amd64.charm"


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


@pytest.fixture(scope="module")
async def ops_test_vm(
    request, tmp_path_factory, ops_test: OpsTest
) -> AsyncGenerator[OpsTest, Any]:
    """Returns a VM OpsTest.

    When the primary substrate is k8s (ops_test points to k8s), this fixture creates and
    manages a secondary VM model for OpenSearch. When the primary substrate is vm, this
    fixture simply yields the same ops_test.
    """
    if os.environ.get("SUBSTRATE", "vm").lower() != "k8s":
        yield ops_test
        return

    model_name = f"{ops_test.model_name}-vm"

    orig_cloud = getattr(request.config.option, "cloud", None)
    orig_model = getattr(request.config.option, "model", None)
    orig_alias = getattr(request.config.option, "model_alias", None)

    request.config.option.controller = ops_test.controller_name
    request.config.option.cloud = "localhost"
    request.config.option.model = model_name
    request.config.option.model_alias = model_name

    ops_res = OpsTest(request, tmp_path_factory)
    await ops_res._setup_model()

    request.config.option.cloud = orig_cloud
    request.config.option.model = orig_model
    request.config.option.model_alias = orig_alias

    yield ops_res

    if not ops_test.keep_model:
        await ops_res.forget_model(alias=model_name)
        await ops_res._controller.destroy_model(model_name, destroy_storage=True, force=True)
        while model_name in await ops_res._controller.list_models():
            await sleep(5)
    await ops_res._cleanup_models()
