# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import PropertyMock

import pytest
from ops import JujuVersion


@pytest.fixture(autouse=True)
def patched_wait(mocker):
    mocker.patch("tenacity.nap.time")


@pytest.fixture(autouse=True)
def patched_pebble_restart(mocker):
    mocker.patch("ops.model.Container.restart")


@pytest.fixture(autouse=True)
def patched_healthy(mocker):
    mocker.patch("workload.ODWorkload.healthy", new_callable=PropertyMock, return_value=True)


@pytest.fixture(autouse=True)
def juju_has_secrets(mocker):
    """Using Juju3 we should always have secrets available."""
    mocker.patch.object(JujuVersion, "has_secrets", new_callable=PropertyMock).return_value = True


# @pytest.fixture(autouse=True)
# def patched_idle(mocker):
#     mocker.patch(
#         "events.upgrade.ODUpgradeEvents.idle", new_callable=PropertyMock, return_value=True
#     )

# @pytest.fixture(autouse=True)
# def patched_set_rolling_update_partition(mocker):
#     mocker.patch("events.upgrade.ODUpgradeEvents._set_rolling_update_partition")
