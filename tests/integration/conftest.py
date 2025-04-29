import logging
import os
import pathlib
import subprocess
from asyncio import sleep
from typing import Any, AsyncGenerator

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)

MICROK8S_CLOUD_NAME = "uk8s"


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


@pytest.fixture(scope="module")
async def microk8s_cloud(ops_test: OpsTest) -> AsyncGenerator[None, Any]:
    """Install and configure MicroK8s as second cloud on the same juju controller.

    Skips if it configured already. Automatically removes connection to the created
    cloud and removes MicroK8s from system unless keep models parameter is used.
    """
    controller_name = next(
        iter(yaml.safe_load(subprocess.check_output(["juju", "show-controller"])))
    )

    clouds = await ops_test._controller.clouds()
    if f"cloud-{MICROK8S_CLOUD_NAME}" in clouds.clouds:
        yield None
        return

    try:
        subprocess.run(["sudo", "snap", "install", "--classic", "microk8s"], check=True)
        subprocess.run(["sudo", "snap", "install", "--classic", "kubectl"], check=True)
        subprocess.run(["sudo", "microk8s", "enable", "dns"], check=True)
        subprocess.run(["sudo", "microk8s", "enable", "hostpath-storage"], check=True)
        subprocess.run(
            ["sudo", "microk8s", "enable", "metallb:10.64.140.43-10.64.140.49"],
            check=True,
        )

        # Configure kubectl now
        subprocess.run(["mkdir", "-p", str(pathlib.Path.home() / ".kube")], check=True)
        kubeconfig = subprocess.check_output(["sudo", "microk8s", "config"])
        with open(str(pathlib.Path.home() / ".kube" / "config"), "w") as f:
            f.write(kubeconfig.decode())
        for attempt in Retrying(stop=stop_after_delay(150), wait=wait_fixed(15)):
            with attempt:
                if (
                    len(
                        subprocess.check_output(
                            "kubectl get po -A  --field-selector=status.phase!=Running",
                            shell=True,
                            stderr=subprocess.DEVNULL,
                        ).decode()
                    )
                    != 0
                ):  # We got sth different from "No resources found." in stderr
                    raise Exception()

        # Add microk8s to the kubeconfig
        subprocess.run(
            [
                "juju",
                "add-k8s",
                MICROK8S_CLOUD_NAME,
                "--client",
                "--controller",
                controller_name,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        pytest.exit(str(e))

    yield None

    if not ops_test.keep_model:
        subprocess.run(
            [
                "juju",
                "remove-cloud",
                "--client",
                "--controller",
                controller_name,
                MICROK8S_CLOUD_NAME,
            ],
            check=True,
        )
        subprocess.run(["sudo", "snap", "remove", "--purge", "microk8s"], check=True)
        subprocess.run(["sudo", "snap", "remove", "--purge", "kubectl"], check=True)


@pytest.fixture(scope="module")
async def ops_test_microk8s(
    request, tmp_path_factory, ops_test: OpsTest, microk8s_cloud: None
) -> AsyncGenerator[OpsTest, Any]:
    """Create second OpsTest object, that is connected to the MicroK8s cloud.

    Automatically creates and destroys (unless keep models parameter is used) corresponding Juju model.

    Returns:
        OpsTest object with MicroK8s connection and Juju model.
    """
    model_name = f"{ops_test.model_name}-uk8s"
    request.config.option.controller = ops_test.controller_name
    request.config.option.cloud = "uk8s"
    request.config.option.model = model_name
    request.config.option.model_alias = model_name
    ops_res = OpsTest(request, tmp_path_factory)
    await ops_res._setup_model()
    yield ops_res
    if not ops_test.keep_model:
        await ops_res.forget_model(alias=model_name)
        await ops_res._controller.destroy_model(model_name, destroy_storage=True, force=True)
        while model_name in await ops_res._controller.list_models():
            await sleep(5)
    await ops_res._cleanup_models()
