#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from unittest.mock import DEFAULT, PropertyMock, patch

import pytest
import yaml
from ops.testing import Harness

from charm import OpensearchDasboardsCharm
from literals import CERTS_REL_NAME, CHARM_KEY, PEER
from src.events.tls import TLSEvents

CONFIG = str(yaml.safe_load(Path("./config.yaml").read_text()))
ACTIONS = str(yaml.safe_load(Path("./actions.yaml").read_text()))
METADATA = str(yaml.safe_load(Path("./metadata.yaml").read_text()))


@pytest.fixture
def harness():
    harness = Harness(OpensearchDasboardsCharm, meta=METADATA, config=CONFIG, actions=ACTIONS)
    harness.add_relation(PEER, CHARM_KEY)
    harness.begin()
    return harness


def test_certificates_created_sets_tls_enabled(harness):
    with harness.hooks_disabled():
        harness.set_leader(True)

    with (
        patch("ops.framework.EventBase.defer"),
        patch("core.cluster.ClusterState.stable", new_callable=PropertyMock, return_value=True),
    ):
        harness.add_relation(CERTS_REL_NAME, "tls-certificates-operator")

        assert harness.charm.state.cluster.tls


def test_certificates_joined_creates_private_key(harness):
    with (
        patch("core.cluster.ClusterState.stable", new_callable=PropertyMock, return_value=True),
        patch("core.models.ODCluster.tls", new_callable=PropertyMock, return_value=True),
        patch("workload.ODWorkload.configure") as workload_config,
    ):
        cert_rel_id = harness.add_relation(CERTS_REL_NAME, "tls-certificates-operator")
        harness.add_relation_unit(cert_rel_id, "tls-certificates-operator/1")

    assert harness.charm.state.unit_server.private_key
    assert "BEGIN RSA PRIVATE KEY" in harness.charm.state.unit_server.private_key.splitlines()[0]
    assert workload_config.assert_called_once


def test_certificates_available_fails_wrong_csr(harness):
    cert_rel_id = harness.add_relation(CERTS_REL_NAME, "tls-certificates-operator")
    harness.update_relation_data(cert_rel_id, f"{CHARM_KEY}/0", {"csr": "not-missing"})

    harness.charm.tls_events.certificates.on.certificate_available.emit(
        certificate_signing_request="missing",
        certificate="cert",
        ca="ca",
        chain=["ca", "cert"],
    )

    assert not harness.charm.state.unit_server.certificate
    assert not harness.charm.state.unit_server.ca


def test_certificates_available_succeeds(harness):
    with harness.hooks_disabled():
        harness.add_relation(CERTS_REL_NAME, "tls-certificates-operator")

    # implicitly tests restart call
    harness.add_relation(harness.charm.restart.name, "{CHARM_KEY}/0")

    harness.charm.unit.add_secret(
        {"csr": "not-missing"},
        label=f"{PEER}.opensearch-dashboards.unit",
    )

    # implicitly tests these method calls
    with patch.multiple(
        "managers.tls.TLSManager",
        set_private_key=DEFAULT,
        set_ca=DEFAULT,
        set_certificate=DEFAULT,
        # set_truststore=DEFAULT,
        # set_p12_keystore=DEFAULT,
    ):
        harness.charm.tls_events.certificates.on.certificate_available.emit(
            certificate_signing_request="not-missing",
            certificate="cert",
            ca="ca",
            chain=["ca", "cert"],
        )

        assert harness.charm.state.unit_server.certificate
        assert harness.charm.state.unit_server.ca


def test_certificates_broken(harness):
    with harness.hooks_disabled():
        certs_rel_id = harness.add_relation(CERTS_REL_NAME, "tls-certificates-operator")

        harness.charm.unit.add_secret(
            {
                "csr": "not-missing",
                "certificate": "cert",
                "ca-cert": "exists",
                "private-key": "key",
            },
            label=f"{PEER}.opensearch-dashboards.unit",
        )
        harness.set_leader(True)

    assert harness.charm.state.unit_server.certificate
    assert harness.charm.state.unit_server.ca
    assert harness.charm.state.unit_server.csr

    # implicitly tests these method calls
    with (
        patch.multiple(
            "managers.tls.TLSManager", remove_cert_files=DEFAULT, certificate_valid=lambda _: True
        ),
        patch("workload.ODWorkload.configure") as workload_config,
        patch("events.tls.TLSCertificatesRequiresV3.request_certificate_revocation"),
    ):

        harness.remove_relation(certs_rel_id)

        # While the TLS relation is gone
        assert not harness.charm.state.cluster.tls
        # ...we've still preserved certs locally
        assert harness.charm.state.unit_server.certificate
        assert harness.charm.state.unit_server.ca
        assert harness.charm.state.unit_server.csr
        assert harness.charm.state.unit_server.tls

        assert workload_config.assert_called_once


def test_certificates_expiring(harness):
    key = open("tests/keys/0.key").read()
    harness.update_relation_data(
        harness.charm.state.peer_relation.id,
        f"{CHARM_KEY}/0",
        {
            "csr": "csr",
            "private-key": key,
            "certificate": "cert",
            "hostname": "treebeard",
            "ip": "1.1.1.1",
            "fqdn": "fangorn",
        },
    )

    with (
        patch(
            "charms.tls_certificates_interface.v3.tls_certificates.TLSCertificatesRequiresV3.request_certificate_renewal",
            return_value=None,
        ),
    ):
        harness.charm.tls_events.certificates.on.certificate_expiring.emit(
            certificate="cert", expiry=None
        )

        assert harness.charm.state.unit_server.csr != "csr"


def test_set_tls_private_key(harness):
    harness.update_relation_data(
        harness.charm.state.peer_relation.id,
        f"{CHARM_KEY}/0",
        {
            "csr": "csr",
            "private-key": "mellon",
            "certificate": "cert",
            "hostname": "treebeard",
            "ip": "1.1.1.1",
            "fqdn": "fangorn",
        },
    )
    key = open("tests/keys/0.key").read()

    with (
        patch(
            "charms.tls_certificates_interface.v3.tls_certificates.TLSCertificatesRequiresV3.request_certificate_renewal",
            return_value=None,
        ),
    ):
        harness.run_action("set-tls-private-key", {"internal-key": key})

        assert harness.charm.state.unit_server.csr != "csr"
