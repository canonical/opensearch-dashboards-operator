#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import pathlib
import subprocess
from asyncio import gather, sleep
from typing import Any, AsyncGenerator

# import oauth_tools
import pytest
import yaml
from integration.helpers import CONFIG_OPTS, SERIES, get_leader_id
from juju.model import Model
from oauth_tools import ExternalIdpService, deploy_identity_bundle
from playwright.async_api._generated import Page
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_delay, wait_fixed

pytest_plugins = ["oauth_tools.fixtures"]

logger = logging.getLogger(__name__)

MICROK8S_CLOUD_NAME = "uk8s"
METADATA = yaml.safe_load(pathlib.Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
OPENSEARCH_RELATION_NAME = "opensearch-client"
OPENSEARCH_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    "cloudinit-userdata": """postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    """,
}
DATA_INTEGRATOR_NAME = "data-integrator"
DATA_INTEGRATOR_CONFIG = {
    "index-name": "admin-index",
    "extra-user-roles": "admin",
}


@pytest.fixture(scope="module")
async def microk8s_cloud(ops_test: OpsTest) -> AsyncGenerator[None, Any]:
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


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy(ops_test: OpsTest, ops_test_microk8s: OpsTest):
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/edge",
        num_units=2,
        series=SERIES,
        config=CONFIG_OPTS,
    )

    charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(
        charm,
        application_name=APP_NAME,
    )


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_identity_bundle(
    ops_test: OpsTest, ops_test_microk8s: OpsTest, ext_idp_service: ExternalIdpService
):
    await deploy_identity_bundle(
        ops_test=ops_test_microk8s, bundle_channel="latest/edge", ext_idp_service=ext_idp_service
    )
    await gather(
        ops_test.model.wait_for_idle(),
        ops_test_microk8s.model.wait_for_idle(raise_on_error=False),
    )


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_setup_relations(ops_test: OpsTest, ops_test_microk8s: OpsTest):
    await ops_test_microk8s.model.create_offer(
        "certificates", "certificates", "self-signed-certificates"
    )
    await ops_test.model.consume(f"admin/{ops_test_microk8s.model_name}.certificates")
    await ops_test.model.integrate(f"{OPENSEARCH_APP_NAME}:certificates", "certificates")
    await ops_test.model.integrate(f"{APP_NAME}:certificates", "certificates")

    await ops_test.model.integrate(
        f"{OPENSEARCH_APP_NAME}:opensearch-client", f"{APP_NAME}:opensearch-client"
    )

    await ops_test_microk8s.model.create_offer("oauth", "oauth", "hydra")
    await ops_test.model.consume(f"admin/{ops_test_microk8s.model_name}.oauth")
    await ops_test.model.integrate(f"{OPENSEARCH_APP_NAME}:oauth", "oauth")
    await ops_test.model.integrate(f"{APP_NAME}:oauth", "oauth")

    await ops_test.model.integrate(
        f"{OPENSEARCH_APP_NAME}:opensearch-client", f"{DATA_INTEGRATOR_NAME}:opensearch"
    )

    await gather(
        ops_test.model.wait_for_idle(status="active"),
        ops_test_microk8s.model.wait_for_idle(),
    )


@pytest.mark.runner(["self-hosted", "linux", "X64", "jammy", "large"])
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_oauth(
    ops_test: OpsTest, ops_test_microk8s: OpsTest, page: Page, ext_idp_service: ExternalIdpService
):
    opensearch_dashboards_ip = get_leader_id(ops_test, APP_NAME)
