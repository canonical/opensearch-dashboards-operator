#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import re
import socket
import subprocess
from pathlib import Path
from subprocess import PIPE, check_output
from typing import Dict, List, Optional

import requests
import yaml
from pytest_operator.plugin import OpsTest

from core.workload import ODPaths

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


def application_active(ops_test: OpsTest, expected_units: int) -> bool:
    units = ops_test.model.applications[APP_NAME].units

    if len(units) != expected_units:
        return False

    for unit in units:
        if unit.workload_status != "active":
            return False

    return True


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


def access_dashboard_https(host: str, password: str):
    """This function should be rather replaced by a 'requests' call, if we can figure out the source of discrepancy."""
    curl_cmd = check_output(
        [
            "bash",
            "-c",
            'curl  -XPOST -H "Content-Type: application/json" -H "osd-xsrf: true" -H "Accept: application/json" '
            + f"https://{host}:5601/auth/login -d "
            + "'"
            + '{"username":"kibanaserver","password": "'
            + f"{password}"
            + '"'
            + "}' --cacert ca.pem",
        ],
        text=True,
    )
    return "roles" in curl_cmd


def srvr(host: str) -> Dict:
    """Retrieves attributes returned from the 'srvr' 4lw command.

    Specifically for this test, we are interested in the "Mode" of the OD server,
    which allows checking quorum leadership and follower active status.
    """
    response = check_output(
        f"echo srvr | nc {host} 2181", stderr=PIPE, shell=True, universal_newlines=True
    )

    assert response, "Opensearch Dashboards not running"

    result = {}
    for item in response.splitlines():
        k = re.split(": ", item)[0]
        v = re.split(": ", item)[1]
        result[k] = v

    return result


async def ping_servers(ops_test: OpsTest) -> bool:
    for unit in ops_test.model.applications[APP_NAME].units:
        host = unit.public_address
        mode = srvr(host)["Mode"]
        if mode not in ["leader", "follower"]:
            return False

    return True


async def correct_version_running(ops_test: OpsTest, expected_version: str) -> bool:
    for unit in ops_test.model.applications[APP_NAME].units:
        host = unit.public_address
        if expected_version not in srvr(host)["Opensearch Dashboards version"]:
            return False

    return True


def get_dashboard_ca_cert(model_full_name: str, unit: str):
    output = subprocess.run(
        [
            "bash",
            "-c",
            f"JUJU_MODEL={model_full_name} juju scp "
            f"ubuntu@{unit}:/var/snap/opensearch-dashboards/current/etc/opensearch-dashboards/certificates/ca.pem ./",
        ],
    )
    if not output.returncode:
        return True
    return False


def check_jaas_config(model_full_name: str, unit: str):
    config = check_output(
        f"JUJU_MODEL={model_full_name} juju ssh {unit} sudo -i 'cat {ODPaths().jaas}'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    user_lines = {}
    for line in config.splitlines():
        matched = re.search(pattern=r"user_([a-zA-Z\-\d]+)=\"([a-zA-Z0-9]+)\"", string=line)
        if matched:
            user_lines[matched[1]] = matched[2]

    return user_lines


async def get_address(ops_test: OpsTest, app_name=APP_NAME, unit_num=0) -> str:
    """Get the address for a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["public-address"]
    return address


def get_private_address(model_full_name: str, unit: str):
    private_ip = check_output(
        [
            "bash",
            "-c",
            f"JUJU_MODEL={model_full_name} juju ssh {unit} ip a | "
            "grep global | grep 'inet 10.*/24' | cut -d' ' -f6 | cut -d'/' -f1",
        ],
        text=True,
    )
    return private_ip.rstrip()


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


def get_relation_data(model_full_name: str, unit: str, endpoint: str):
    show_unit = _get_show_unit_json(model_full_name=model_full_name, unit=unit)
    d_relations = show_unit[unit]["relation-info"]
    for relation in d_relations:
        if relation["endpoint"] == endpoint:
            return relation["application-data"]
    raise Exception("No relation found!")


async def get_application_hosts(ops_test: OpsTest, app_name: str, units: List[str]) -> List[str]:
    """Retrieves the ip addresses of the containers."""
    hosts = []
    status = await ops_test.model.get_status()  # noqa: F821
    for unit in units:
        hosts.append(status["applications"][app_name]["units"][f"{unit}"]["public-address"])
    return hosts


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


def set_opensearch_user_password(
    opensearch_endpoint: str,
    opensearch_admin_password: str,
    dashboard_password: str,
    user: str = "kibanaserver",
) -> bool:
    """Setting the password for a user in opensearch."""
    session = requests.Session()
    session.auth = ("admin", opensearch_admin_password)

    url = f"https://{opensearch_endpoint}/_plugins/_security/api/internalusers/{user}"
    payload = {"password": dashboard_password}
    headers = {"Content-Type": "application/json"}
    response = session.put(url, json=payload, headers=headers, verify=False)
    return response.status_code == 200
