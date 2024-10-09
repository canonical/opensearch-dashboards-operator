#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import socket
import subprocess
from pathlib import Path
from subprocess import PIPE, CalledProcessError, check_output
from typing import Dict, List, Optional

import requests
import yaml
from juju.relation import Relation
from juju.unit import Unit
from pytest_operator.plugin import OpsTest
from requests.exceptions import ConnectionError, SSLError
from tenacity import (
    Retrying,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_fixed,
)

from core.workload import ODPaths

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OPENSEARCH_APP_NAME = "opensearch"
SERIES = "jammy"

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

TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"
COS_AGENT_APP_NAME = "grafana-agent"
COS_AGENT_RELATION_NAME = "cos-agent"
DB_CLIENT_APP_NAME = "application"


logger = logging.getLogger(__name__)

DASHBOARD_QUERY_PARAMS = {
    "params": {
        "index": "albums*",
        "body": {
            "sort": [{"_score": {"order": "desc"}}],
            "size": 500,
            "version": True,
            "stored_fields": ["*"],
            "script_fields": {},
            "docvalue_fields": [],
            "_source": {"excludes": []},
            "query": {
                "bool": {
                    "must": [],
                    "filter": [{"match_all": {}}],
                    "should": [],
                    "must_not": [],
                }
            },
        },
        "preference": 1717603297253,
    }
}


def get_relations(ops_test: OpsTest, name: str, app_name: str = APP_NAME) -> list[Relation]:
    """Get relations of a given name"""
    results = []
    for relation in ops_test.model.relations:
        if any(
            [
                relation.endpoints[i].name == name and relation.applications[i].name == app_name
                for i in range(len(relation.endpoints))
            ]
        ):
            results.append(relation)
    return results


def get_relation(ops_test: OpsTest, relation: str = "opensearch-client"):
    return get_relations(ops_test, relation)[0]


async def get_password(ops_test) -> str:
    secret_data = await get_secret_by_label(ops_test, f"{APP_NAME}.app")
    return secret_data.get("super-password")


async def get_secret_by_label(ops_test, label: str) -> Dict[str, str]:
    secrets_meta_raw = await ops_test.juju("list-secrets", "--format", "json")
    secrets_meta = json.loads(secrets_meta_raw[1])

    for secret_id in secrets_meta:
        if secrets_meta[secret_id]["label"] == label:
            break

    secret_data_raw = await ops_test.juju("show-secret", "--format", "json", "--reveal", secret_id)
    secret_data = json.loads(secret_data_raw[1])
    return secret_data[secret_id]["content"]["Data"]


async def get_user_password(ops_test: OpsTest, user: str, num_unit=0) -> str:
    """Use the charm action to retrieve the password for user.

    Return:
        String with the password stored on the peer relation databag.
    """
    params = {"username": user}
    action = await ops_test.model.units.get(f"{APP_NAME}/{num_unit}").run_action(
        "get-password", **params
    )
    password = await action.wait()
    return password.results[f"{user}-password"]


async def set_password(
    ops_test: OpsTest, username="kibanaserver", password=None, num_unit=0
) -> str:
    """Use the charm action to start a password rotation."""
    params = {"username": username}
    if password:
        params["password"] = password

    action = await ops_test.model.units.get(f"{APP_NAME}/{num_unit}").run_action(
        "set-password", **params
    )
    password = await action.wait()
    return password.results


def restart_unit(model_full_name: str, unit: str) -> None:
    # getting juju id
    machine_id = check_output(
        f"JUJU_MODEL={model_full_name} juju status | grep {unit} | awk '{{ print $4 }}'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    # getting lxc machine name
    machine_name = check_output(
        f"JUJU_MODEL={model_full_name} juju machines | grep awk '{{print $4}}' | grep -e '-{machine_id}'| head -1",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )
    _ = check_output(
        f"lxc restart {machine_name}",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )


def access_prometheus_exporter(host: str) -> bool:
    """Check if a given unit has 'kibana-exporter' service available and publishing."""
    try:
        # Normal IP address
        socket.inet_aton(host)
    except OSError:
        socket.inet_pton(socket.AF_INET6, host)
        host = f"[{host}]"

    url = f"http://{host}:9684/metrics"
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException:
        return False
    return response.status_code == 200 and "kibana_status" in response.text


async def access_all_prometheus_exporters(ops_test: OpsTest) -> bool:
    """Check if a given unit has 'kibana-exporter' service available and publishing."""
    result = True
    for unit in ops_test.model.applications[APP_NAME].units:
        unit_ip = await get_address(ops_test, unit.name)
        result = result and access_prometheus_exporter(unit_ip)
    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(5),
    retry_error_callback=lambda _: False,
    retry=lambda x: x is False,
)
def dashboard_unavailable(host: str, https: bool = False) -> bool:
    """A single OSD instance is impossible to contact."""
    protocol = "http" if not https else "https"
    url = f"{protocol}://{host}:5601/auth/login"
    arguments = {"url": url}
    if https:
        arguments["verify"] = "./ca.pem"

    try:
        response = requests.get(**arguments)
    except ConnectionError:
        return True
    return response.status_code == 503


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(15),
    retry_error_callback=lambda _: False,
    retry=retry_if_result(lambda x: x is False),
)
def all_dashboards_unavailable(ops_test: OpsTest, https: bool = False) -> bool:
    """None of the OSD units are possible to contact."""

    unavail = True
    for unit in ops_test.model.applications[APP_NAME].units:

        if https:
            if not get_dashboard_ca_cert(ops_test.model.name, unit):
                logger.info(f"Couldn't retrieve host certificate for unit {unit}")
                continue

        host = get_bind_address(ops_test.model.name, unit.name)

        # We should retry until a host could be retrieved
        if not host:
            continue

        unavail = unavail and dashboard_unavailable(host, https)
        if not unavail:
            logger.error("Host {host} still available")
    return unavail


def access_dashboard(
    host: str, password: str, username: str = "kibanaserver", ssl: bool = False
) -> bool:
    #
    # NOTE: This one currently is failing for SSL, with:
    # *** requests.exceptions.SSLError: HTTPSConnectionPool(host='10.67.147.132', port=5601):
    # Max retries exceeded with url: /auth/login (Caused by
    # SSLError(SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
    # IP address mismatch, certificate is not valid for '10.67.147.132'. (_ssl.c:1007)")))
    #
    # ...while CURL is passing happily with the same cert...
    # Thus, temporarily the least the function below this one is used for HTTPS
    #

    try:
        # Normal IP address
        socket.inet_aton(host)
    except OSError:
        socket.inet_pton(socket.AF_INET6, host)
        host = f"[{host}]"

    protocol = "http" if not ssl else "https"
    url = f"{protocol}://{host}:5601/auth/login"
    data = {"username": username, "password": password}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "osd-xsrf": "true",
    }

    arguments = {"url": url, "headers": headers, "json": data}
    if ssl:
        arguments["verify"] = "./ca.pem"
    response = requests.post(**arguments)
    return response.status_code == 200


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(15),
    retry_error_callback=lambda _: False,
    retry=retry_if_result(lambda x: x is False),
)
async def access_all_dashboards(
    ops_test: OpsTest, relation_id: int | None = None, https: bool = False, skip: list[str] = []
):
    """Check if all dashboard instances are accessible."""

    if not ops_test.model.applications[APP_NAME].units:
        logger.error(f"No units for application {APP_NAME}")
        return False

    if not relation_id:
        relation_id = get_relation(ops_test, "opensearch-client").id

    dashboard_credentials = await get_secret_by_label(
        ops_test, f"opensearch-client.{relation_id}.user.secret"
    )
    dashboard_password = dashboard_credentials["password"]

    # Copying the Dashboard's CA cert locally to use it for SSL verification
    # We only get it once for pipeline efficiency, as it's the same on all units
    if https:
        unit = ops_test.model.applications[APP_NAME].units[0].name
        if unit not in skip and not get_dashboard_ca_cert(ops_test.model.name, unit):
            logger.error(f"Couldn't retrieve host certificate for unit {unit}")
            return False

    result = True
    for unit in ops_test.model.applications[APP_NAME].units:
        if unit.name in skip:
            continue
        host = get_bind_address(ops_test.model.name, unit.name)
        if not host:
            logger.error(f"No hostname found for {unit.name}, can't check connection.")
            return False

        result &= access_dashboard(host=host, password=dashboard_password, ssl=https)
        if result:
            logger.info(f"Host {unit.name}, {host} passed access check")
        else:
            dump_all(ops_test, unit)
    return result


@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(30),
    retry_error_callback=lambda _: False,
    retry=(retry_if_result(lambda x: x is False) | retry_if_exception_type(SSLError)),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
)
def get_dashboard_ca_cert(model_full_name: str, unit: str):
    try:
        output = subprocess.run(
            [
                "bash",
                "-c",
                f"JUJU_MODEL={model_full_name} juju scp "
                f"ubuntu@{unit}:"
                "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/certificates/ca.pem ./",
            ],
            timeout=30,
        )
    except subprocess.CalledProcessError as err:
        logger.error(f"{err}")
        return False
    if not output.returncode:
        return True
    return False


def get_file_contents(ops_test: OpsTest, unit: Unit, filename: str) -> str:
    try:
        output = subprocess.check_output(
            [
                "bash",
                "-c",
                f"JUJU_MODEL={ops_test.model.name} juju ssh {unit.name} sudo cat {filename}",
            ]
        )
    except subprocess.CalledProcessError as err:
        logger.error(f"{err}")
        output = ""
    return output


def dump_all(ops_test: OpsTest, unit: Unit):
    for file in [
        "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/certificates/ca.pem",
        "/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/opensearch_dashboards.yml",
        "/var/snap/opensearch-dashboards/common/var/log/opensearch-dashboards/opensearch_dashboards.log",
    ]:
        output = get_file_contents(ops_test, unit, file)
        if output:
            print(output)


async def get_address(ops_test: OpsTest, unit_name: str) -> str:
    """Get the address for a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][APP_NAME]["units"][f"{unit_name}"]["public-address"]
    return address


def get_bind_address(model_full_name: str, unit: str):
    try:
        private_ip = check_output(
            [
                "juju",
                "exec",
                f"--model={model_full_name}",
                "--unit",
                unit,
                "--",
                "network-get",
                OPENSEARCH_RELATION_NAME,
                "--bind-address",
            ],
            text=True,
        )
    except CalledProcessError as err:
        logger.info(f"Couldn't retrieve IP address: {str(err)}")
        return ""

    if private_ip.rstrip():
        return private_ip.rstrip()

    try:
        info = check_output(
            ["bash", "-c", f"JUJU_MODEL={model_full_name} juju ssh {unit} ip a "],
            text=True,
        )
        logger.info(f"Couldn't retrieve IP, info is: {info}")
    except CalledProcessError as err:
        logger.info(f"Couldn't retrieve IP address: {str(err)}")
        return ""


def _get_show_unit_json(model_full_name: str, unit: str) -> Dict:
    """Retrieve the show-unit result in json format."""
    show_unit_res = check_output(
        f"JUJU_MODEL={model_full_name} juju show-unit {unit} --format json",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    try:
        show_unit_res_dict = json.loads(show_unit_res)
        return show_unit_res_dict
    except json.JSONDecodeError:
        raise ValueError


def check_properties(model_full_name: str, unit: str):
    properties = check_output(
        f"JUJU_MODEL={model_full_name} juju ssh {unit} sudo -i 'cat {ODPaths().properties}'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )
    return properties.splitlines()


def get_relation_id(model_full_name: str, unit: str, app_name: str):
    show_unit = _get_show_unit_json(model_full_name=model_full_name, unit=unit)
    d_relations = show_unit[unit]["relation-info"]
    for relation in d_relations:
        if relation["endpoint"] == app_name:
            relation_id = relation["relation-id"]
            return relation_id
    raise Exception("No relation found!")


def get_app_relation_data(model_full_name: str, unit: str, endpoint: str):
    show_unit = _get_show_unit_json(model_full_name=model_full_name, unit=unit)
    d_relations = show_unit[unit]["relation-info"]
    for relation in d_relations:
        if relation["endpoint"] == endpoint:
            return relation["application-data"]
    raise Exception("No relation found!")


def get_unit_relation_data(model_full_name: str, unit: str, endpoint: str):
    show_unit = _get_show_unit_json(model_full_name=model_full_name, unit=unit)
    d_relations = show_unit[unit]["relation-info"]
    for relation in d_relations:
        if relation["endpoint"] == endpoint:
            return relation["related-units"]
    raise Exception("No relation found!")


async def get_application_hosts(ops_test: OpsTest, app_name: str, units: List[str]) -> List[str]:
    """Retrieves the ip addresses of the containers."""
    hosts = []
    status = await ops_test.model.get_status()  # noqa: F821
    for unit in units:
        hosts.append(status["applications"][app_name]["units"][f"{unit}"]["public-address"])
    return hosts


async def check_full_status(
    ops_test: OpsTest, app: str = APP_NAME, status: str = "active", status_msg: str | None = None
) -> bool:
    """Compare app and unit status against those requested in the parameters."""
    status_data = await ops_test.model.get_status()  # noqa: F821

    if not status_data.applications[app].status.status == status:
        return False

    if not all(
        unit.workload_status.status == status
        for unit in status_data.applications[app].units.values()
    ):
        return False

    if status_msg:
        if not status_data.applications[app].status.info == status_msg:
            return False
        if not all(
            unit.workload_status.info == status_msg
            for unit in status_data.applications[app].units.values()
        ):
            return False
    return True


def count_lines_with(model_full_name: str, unit: str, file: str, pattern: str) -> int:
    result = check_output(
        f"JUJU_MODEL={model_full_name} juju ssh {unit} sudo -i 'grep \"{pattern}\" {file} | wc -l'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    return int(result)


async def get_alias_from_relation_data(
    ops_test: OpsTest, unit_name: str, related_unit_name: str
) -> Optional[str]:
    """Get the alias that the unit assigned to the related unit application/cluster.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit
        related_unit_name: name of the related unit

    Returns:
        the alias for the application/cluster of
            the related unit

    Raises:
        ValueError if it's not possible to get unit data
            or if there is no alias on that.
    """
    raw_data = (await ops_test.juju("show-unit", related_unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {related_unit_name}")
    data = yaml.safe_load(raw_data)

    # Retrieve the relation data from the unit.
    relation_data = {}
    for relation in data[related_unit_name]["relation-info"]:
        # Peer relation typically
        if "related-units" not in relation:
            continue
        for name, unit in relation["related-units"].items():
            if name == unit_name:
                relation_data = unit["data"]
                break

    # Check whether the unit has set an alias for the related unit application/cluster.
    if "alias" not in relation_data:
        raise ValueError(f"no alias could be grabbed for {related_unit_name} application/cluster")

    return relation_data["alias"]


async def get_application_relation_data(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
    key: str,
    relation_id: str = None,
    relation_alias: str = None,
    related_endpoint: str = None,
    app_or_unit: str = "app",
) -> Optional[str]:
    """Get relation data for an application.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: name of the relation to get connection data from
        key: key of data to be retrieved
        relation_id: id of the relation to get connection data from
        relation_alias: alias of the relation (like a connection name)
            to get connection data from
        related_endpoint: the related endpoint, i.e. the "other side" of the relation
        app_or_unit: whether it's the app or the unit databag to be searched

    Returns:
        the data that was requested or None
            if no data in the relation

    Raises:
        ValueError if it's not possible to get application data
            or if there is no data for the particular relation endpoint
            and/or alias.
    """
    unit_name = f"{application_name}/0"
    raw_data = (await ops_test.juju("show-unit", unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {unit_name}")
    data = yaml.safe_load(raw_data)
    # Filter the data based on the relation name.
    relation_data = [v for v in data[unit_name]["relation-info"] if v["endpoint"] == relation_name]

    if relation_id:
        # Filter the data based on the relation id.
        relation_data = [v for v in relation_data if v["relation-id"] == relation_id]
    if relation_alias:
        # Filter the data based on the cluster/relation alias.
        relation_data = [
            v
            for v in relation_data
            if await get_alias_from_relation_data(
                ops_test, unit_name, next(iter(v["related-units"]))
            )
            == relation_alias
        ]
    if related_endpoint:
        relation_data = [
            v
            for v in data[unit_name]["relation-info"]
            if v["related-endpoint"] == related_endpoint
        ]
    if len(relation_data) == 0:
        raise ValueError(
            f"no relation data could be grabbed on relation with endpoint {relation_name} and alias {relation_alias}"
        )
    if app_or_unit == "app":
        return relation_data[0]["application-data"].get(key)
    else:
        return relation_data[0]["local-unit"].get("data", {}).get(key)


async def get_leader_name(ops_test: OpsTest, app_name: str = APP_NAME):
    """Get the leader unit name."""
    for unit in ops_test.model.applications[app_name].units:
        if await unit.is_leader_from_status():
            return unit.name


async def get_leader_id(ops_test: OpsTest, app_name: str = APP_NAME) -> str:
    """Get the leader unit id."""
    leader_name = await get_leader_name(ops_test, app_name)
    return leader_name.split("/")[-1]


def get_unit(ops_test: OpsTest, unit_name: str) -> str:
    """Get unit by name."""
    for unit in ops_test.model.units:
        if unit.name == unit_name:
            return unit


def get_hostname(ops_test: OpsTest, unit_name: str) -> str:
    """Get hostname for a unit."""
    unit = get_unit(ops_test, unit_name)
    return unit.machine.hostname


@retry(wait=wait_fixed(wait=15), stop=stop_after_attempt(15))
async def client_run_request(
    ops_test,
    unit_name: str,
    relation: Relation,
    method: str,
    headers: str,
    endpoint: str,
    payload: str = None,
    action: str = "run-db-request",
    server_uri: str = "",
):
    # python can't have variable names with a hyphen, and Juju can't have action variables with an
    # underscore, so this is a compromise.

    app_name = unit_name.split("/")[0]
    relation_name = [
        relation.endpoints[i].name for i in range(2) if relation.applications[i].name == app_name
    ][0]
    params = {
        "relation-id": relation.id,
        "relation-name": relation_name,
        "headers": json.dumps(headers),
        "method": method,
        "endpoint": endpoint,
    }
    if payload:
        params["payload"] = payload
    if server_uri:
        params["server-uri"] = server_uri

    action = await ops_test.model.units.get(unit_name).run_action(action, **(params or {}))
    action = await action.wait()

    if action.status != "completed":
        raise Exception(action.results)

    return action.results


@retry(wait=wait_fixed(wait=15), stop=stop_after_attempt(15))
async def client_run_db_request(
    ops_test,
    unit_name: str,
    relation: Relation,
    method: str,
    endpoint: str,
    payload: str = None,
):
    """Client applicatoin issuing a request to Opensearch."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return await client_run_request(
        ops_test, unit_name, relation, method, headers, endpoint, payload
    )


@retry(wait=wait_fixed(wait=15), stop=stop_after_attempt(15))
async def client_run_dashboards_request(
    ops_test,
    unit_name: str,
    relation: Relation,
    method: str,
    host: str,
    endpoint: str,
    payload: str = None,
    https=False,
):
    """Client applicatoin issuing a request to Opensearch Dashboards."""
    action = "run-dashboards-request"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "osd-xsrf": "osd-fetch",
    }
    proto = "https" if https else "http"
    server_uri = f"{proto}://{host}:5601"
    return await client_run_request(
        ops_test,
        unit_name,
        relation,
        method,
        headers,
        endpoint,
        payload,
        action,
        server_uri,
    )


async def client_run_all_dashboards_request(
    ops_test: OpsTest,
    unit_name: str,
    relation: Relation,
    method: str,
    endpoint: str,
    payload: str = None,
    https: bool = False,
):
    """Check if all dashboard instances are accessible."""

    result = []
    if not ops_test.model.applications[APP_NAME].units:
        logger.debug(f"No units for application {APP_NAME}")
        return False

    for dashboards_unit in ops_test.model.applications[APP_NAME].units:
        host = get_bind_address(ops_test.model.name, dashboards_unit.name)
        if not host:
            logger.debug(f"No hostname found for {dashboards_unit.name}, can't check connection.")
            return False

        response = await client_run_dashboards_request(
            ops_test, unit_name, relation, method, host, endpoint, payload, https
        )
        if "results" in response:
            result.append(json.loads(response["results"])["rawResponse"])
        else:
            result.append(response)
        logger.info(f"Response from {unit_name}, {host}: {response}")

    return result


async def destroy_cluster(ops_test, app: str = OPENSEARCH_APP_NAME):
    """Destroy cluster in a forceful way."""
    n_apps_before = len(ops_test.model.applications)
    await ops_test.model.applications[app].destroy(destroy_storage=True, force=True, no_wait=False)

    # destroy does not wait for applications to be removed, perform this check manually
    for attempt in Retrying(stop=stop_after_attempt(100), wait=wait_fixed(10), reraise=True):
        with attempt:
            # pytest_operator has a bug where the number of applications does not get correctly
            # updated. Wrapping the call with `fast_forward` resolves this
            async with ops_test.fast_forward():
                n_apps_after = len(ops_test.model.applications)
            # This case we don't raise an error in the context manager which
            # fails to restore the `update-status-hook-interval` value to it's former state.
            assert n_apps_after == n_apps_before - 1, "old cluster not destroyed successfully."


async def for_machines(ops_test, machines, state="started"):
    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(wait=60)):
        with attempt:
            mach_status = json.loads(
                subprocess.check_output(
                    ["juju", "machines", f"--model={ops_test.model.name}", "--format=json"]
                )
            )["machines"]
            for id in machines:
                if (
                    str(id) not in mach_status.keys()
                    or mach_status[str(id)]["juju-status"]["current"] != state
                ):
                    logger.warning(f"machine-{id} either not exist yet or not in {state}")
                    raise Exception()
