import logging
import os
import subprocess

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="module")
def opensearch_sysctl_settings():
    """Necessary settings for Opensearch

    This should probably rather go to ci.yaml"""
    subprocess.run(["sudo", "sysctl", "-w", "vm.swappiness=0"])
    subprocess.run(["sudo", "sysctl", "-w", "vm.max_map_count=262144"])
    subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.tcp_retries2=5"])


@pytest.fixture
def ubuntu_base():
    """charm base version to use for testing."""
    return os.environ["CHARM_UBUNTU_BASE"]


@pytest.fixture
def series(ubuntu_base):
    """Workaround: python-libjuju does not support deploy base="ubuntu@22.04"; use series"""
    if ubuntu_base == "22.04":
        return "jammy"
    elif ubuntu_base == "24.04":
        return "noble"
    else:
        raise NotImplementedError


@pytest.fixture
def charm(ubuntu_base):
    """Path to the charm file to use for testing."""
    # Return str instead of pathlib.Path since python-libjuju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./opensearch-dashboards_ubuntu@{ubuntu_base}-amd64.charm"


@pytest.fixture
def application_charm() -> str:
    """Path to the application charm to use for testing."""
    return "./tests/integration/application-charm/application_ubuntu@22.04-amd64.charm"
