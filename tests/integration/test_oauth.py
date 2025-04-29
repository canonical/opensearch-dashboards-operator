#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import pathlib
from asyncio import gather

# import oauth_tools
import pytest
import yaml
from integration.helpers import CONFIG_OPTS, get_address
from oauth_tools import (
    ExternalIdpService,
    access_application_login_page,
    click_on_sign_in_button_by_text,
    complete_auth_code_login,
    deploy_identity_bundle,
)
from playwright.async_api._generated import Page
from pytest_operator.plugin import OpsTest

pytest_plugins = ["oauth_tools.fixtures"]

logger = logging.getLogger(__name__)

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


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy(ops_test: OpsTest, ops_test_microk8s: OpsTest, charm: str, series: str):
    """Deploy OpenSearch and OpenSearch Dashboards but don't wait for completion."""
    await ops_test.model.set_config(OPENSEARCH_CONFIG)

    await ops_test.model.deploy(
        OPENSEARCH_APP_NAME,
        channel="2/edge",
        num_units=2,
        series=series,
        config=CONFIG_OPTS,
    )

    await ops_test.model.deploy(
        charm,
        application_name=APP_NAME,
        series=series,
    )


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_identity_bundle(
    ops_test: OpsTest, ops_test_microk8s: OpsTest, ext_idp_service: ExternalIdpService
):
    """Deploy identity platform on K8s and wait for both models to complete deployments."""
    await deploy_identity_bundle(
        ops_test=ops_test_microk8s,
        bundle_channel="latest/edge",
        ext_idp_service=ext_idp_service,
    )
    await gather(
        ops_test.model.wait_for_idle(),
        ops_test_microk8s.model.wait_for_idle(raise_on_error=False),
    )


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_setup_relations(ops_test: OpsTest, ops_test_microk8s: OpsTest):
    """Establish all the required relations.

    Connects OpenSearch, OpenSearch Dashboards and identity platform (cross-model).
    """
    await ops_test_microk8s.model.create_offer(
        "certificates", "certificates", "self-signed-certificates"
    )
    await ops_test.model.consume(f"admin/{ops_test_microk8s.model_name}.certificates")
    await ops_test.model.integrate(f"{OPENSEARCH_APP_NAME}:certificates", "certificates")
    await ops_test.model.integrate(f"{APP_NAME}:certificates", "certificates")

    await ops_test.model.integrate(
        f"{OPENSEARCH_APP_NAME}:opensearch-client", f"{APP_NAME}:opensearch-client"
    )

    await gather(
        ops_test.model.wait_for_idle(status="active"),
        ops_test_microk8s.model.wait_for_idle(raise_on_error=False),
    )

    await ops_test_microk8s.model.create_offer("oauth", "oauth", "hydra")
    await ops_test.model.consume(f"admin/{ops_test_microk8s.model_name}.oauth")
    await ops_test.model.integrate(f"{OPENSEARCH_APP_NAME}:oauth", "oauth")
    await ops_test.model.integrate(f"{APP_NAME}:oauth", "oauth")

    await gather(
        ops_test.model.wait_for_idle(status="active"),
        ops_test_microk8s.model.wait_for_idle(raise_on_error=False),
    )


@pytest.mark.abort_on_fail
async def test_oauth(
    ops_test: OpsTest,
    ops_test_microk8s: OpsTest,
    page: Page,
    ext_idp_service: ExternalIdpService,
):
    """Ensure that SSO works for OpenSearch Dashboards login."""
    opensearch_dashboards_ip = await get_address(
        ops_test, ops_test.model.applications[APP_NAME].units[0].name
    )

    await access_application_login_page(
        page=page,
        url=f"https://{opensearch_dashboards_ip}:5601",
        redirect_login_url=f"https://{opensearch_dashboards_ip}:5601/app/login",
    )
    await click_on_sign_in_button_by_text(page=page, text="Log in with single sign-on")
    await complete_auth_code_login(
        page=page, ops_test=ops_test_microk8s, ext_idp_service=ext_idp_service
    )
