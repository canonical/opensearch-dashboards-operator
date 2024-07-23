#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm-specific exceptions."""


class OSDError(Exception):
    """Charm-specific parent exception."""


class OSDAPIError(OSDError):
    """Exception relating to OSD API access."""
