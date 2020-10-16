"""This module handles all functionalities for the service.

The functionalities are separated in two major groups.
The first one is to transport the service between several devices,
the second one can start, stop the service and notifies all clients,
when the service status has been changed.
"""

__all__ = ["ServiceHandler",
           "ServiceTransporter",
           "ServiceStatusCodes",
           "TransportStatusCodes"]

__version__ = '1.0'
__author__ = 'Simon Lansing'

from service.service_handler import ServiceHandler
from service.service_handler import ServiceStatusCodes
from service.service_transporter import ServiceTransporter
from service.service_transporter import TransportStatusCodes
