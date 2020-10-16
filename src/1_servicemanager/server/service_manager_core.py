"""This module contains the core class for the full service manager.

This core class initializes all necessary functions and builds a frame for all
components, so that they do not have to interact with each other. All
informations in the complete service manager platform go through the service
manager core.
"""

import logging
import os.path
import time
from threading import Event
from migration import NetworkUtilizationInspector
from migration import NetworkRouter
from migration import NetworkSniffer
from service import ServiceTransporter
from service import ServiceHandler
from service import ServiceStatusCodes
from utils import Networking

LOGGER = logging.getLogger(__name__)

class ServiceManagerCore(object):
    """The core class for the full service manager.

    The service manager is build after the behavioral design patterns
    mediator. All functionalities from other classes are working together through the service manager core. The other classes can use the predefined
    callback functions to set events, and set/get system wide informations.

    Attributes:
        configuration (:obj:`optparse.Option`): Contains all command line
            parameters.

        start_service_event (Event): Event to start the service.
        stop_service_event (Event): Event to stop the service.
        no_recent_connections_event (Event): Event for the migration
            checker, if no recent connections has been detected.
        migrate_service_event (Event): Event to migrated the service
            to another host and stop this service instance.
        duplicate_service_event (Event): Event to duplicate the service to
            another host and keep this service instance running.

        network_router (NetworkRouter): Class to calculate the next
            best service position
        network_sniffer (NetworkSniffer): Class to sniff the 
            incoming and outgoing traffic for the service
        network_utilization_inspector (NetworkUtilizationInspector): 
            Class to take repeatedly decisions for the next migration or duplication, based on the migration time
        service_handler (ServiceHandler): Class to start and stop the service,
            and to inform clients via broadcast for a new or closing service
            instance
        service_transporter (ServiceTransporter): Class to transport the
            service between several service manager instances on different hosts
    """

    def __init__(self, options):
        """The initialization function of the class ServiceManagerCore.

        The function initializes the service manager with all events and
        subclasses.

        Args:
            options (:obj:`optparse.Option`): Contains all command line parameters. 
        """

        LOGGER.debug("starting service_manager_core")
        self.configuration = options
        self.start_service_event = Event()
        self.stop_service_event = Event()

        if options.run_service is True:
            self.start_service_event.set()

        self.no_recent_connections_event = Event()
        self.migrate_service_event = Event()
        self.duplicate_service_event = Event()
        #self.unreachable_hosts = options.unreachable_hosts

        #self.server_hosts = options.server_hosts

        self.network_router = NetworkRouter(self, self.configuration)

        self.network_sniffer = NetworkSniffer(self, self.configuration)

        self.network_utilization_inspector = NetworkUtilizationInspector(
            self, self.configuration)

        self.service_handler = ServiceHandler(self, self.configuration)

        self.service_transporter = ServiceTransporter(self, self.configuration)

    def __enter__(self):
        LOGGER.debug("service_manager_core enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.network_utilization_inspector.cancel_migration_check()
        LOGGER.debug("service_manager_core exit")
        return self

    def service_received_callback(self):
        """Event to inform, that all service files have been received.
        
        Starts the service after the transporter received the service file.
        Through the start_service event, the main loop of the service manager
        core starts the service. The service transporter thread waits inside
        of this method for 10 seconds and checks every second, if the service
        has been started. On a positive start, the service transporter reports
        the new service status to the other (old) server.
        On timeout, the "error starting service" code will be sent back.
        """

        service_status, service_error = ServiceStatusCodes.ERROR_STARTING_SERVICE, "callback error"
        try:
            self.start_service_event.set()

            wait_timeout = 10
            service_status, service_error = self.service_handler.get_service_status()
            while service_status in [ServiceStatusCodes.NOT_STARTED_YET, ServiceStatusCodes.IN_TRANSMISSION]:
                LOGGER.debug("waiting for starting service. service status={}, error={}".format(
                    service_status, service_error))
                
                wait_timeout -= 1
                if wait_timeout == 0:
                    service_status, service_error = ServiceStatusCodes.ERROR_STARTING_SERVICE, "starting service timeout"
                time.sleep(1)
                
                service_status, service_error = self.service_handler.get_service_status()
        except Exception as exc:
            LOGGER.error("FAILED: %s", exc)

        return service_status, service_error

    def do_service_reset_callback(self):
        """Event to reset the complete service.
        
        This method stops the running service, deletes all service files
        and resets its status back to the beginning.
        """

        self.service_handler.delete_service_and_reset_status()

    def do_service_stop_callback(self):
        """Event to stop the complete service.
        
        This method stops the running service and resets its status back
        to the beginning. The service files will not be deleted.
        """
        
        LOGGER.info("stopping false running service")
        self.stop_service_event.set()

    def get_own_hostname_callback(self):
        """Event to get the own host name of the machine.
        
        This method returns the name of the host. E.g. it can be used by
        several classes to compare traffic data or the best host with the own
        to run the service before a migration.

        Returns:
            The name of this host itself.
        """

        return self.network_router.get_own_hostname()

    def get_service_config_callback(self):
        """Event to get the service configuration.

        This method returns the configuration of the active service instance,
        containing the unique service instance ID and the open ports of the
        service.

        Returns:
            The active service configuration.
        """

        return self.service_handler.get_service_configuration()

    def set_service_config_callback(self, service_id, service_ports):
        """Event to set the service configuration.

        This method sets the new configuration of the new service instance,
        containing the unique service instance ID and the open ports of the
        service.

        Args:
            service_id (:obj:`int`): unique service instance ID, increased by
                the transporter after every migration.
            service_ports (:obj:`list` of :obj:`int`): list of all open ports
                of the service to sniff on them for traffic analyzing.
        """

        self.service_handler.set_service_configuration(service_id, service_ports)

    def get_service_status_callback(self):
        """Event to get the service status.

        This method returns the status of the service instance, containing an
        object of the class ServiceStatusCodes and an error code, if an error
        happened while starting the service.

        Returns:
            The status of the service.
        """

        return self.service_handler.get_service_status()

    def set_service_status_callback(self, new_service_status, error):
        """Event to set the service status.

        This method set the status of the service instance, containing an
        predefined enum equal string of the class ServiceStatusCodes and an
        error code, if an error happened in any occasion.

        Args:
            new_service_status (:obj:`str`): status code of the class
                ServiceStatusCodes
            error (:obj:`str`, optional): error code of the given status
        """

        self.service_handler.set_service_status(new_service_status, error)

    def found_service_ports_callback(self, service_pid, ports):
        """Event to set service ports to sniff on after starting the service.

        After starting the service the ports will be set to start a sniffing
        process. This process will start the complete migration iteration
        functionality, which will not be stopped until the next migration.


        Args:
            service_pid (:obj:`int`): the PID of the running service
            port (:obj:`list` of :obj:`int`): list of all open ports of the
                service to sniff on them for traffic analyzing.
        """

        self.network_sniffer.set_sniffing_ports(ports)
        #self.network_utilization_inspector.
        #    start_recent_cpu_and_ram_usage_timer(
        #        service_pid
        #    )

    def new_packet_callback(self, packet_size):
        """Event for every new packet on all ports of the host.

        Any packet incoming and outgoing on any port on the host will be
        recognized by the service manager. The size of the packet will be
        forwarded as an event to the core.

        Args:
            packet_size (:obj:`int`): The size of the incoming packet.
        """

        pass

    def new_service_packet_callback(self, network_packet, is_incoming_packet):
        """Event for every new packet on the ports of the service.

        Any packet incoming and outgoing on the ports of the service will be recognized by the service manager.

        Args:
            network_packet (:obj:`NetworkPacket`): The full network packet
                with all layer informations of the incoming and outgoing
                packet.

            is_incoming_packet(bool): Flag with determines the direction of
                the package. 
        """

        other_ip_addr = network_packet.source_ip_address if is_incoming_packet else network_packet.dest_ip_address
        node_id = Networking.translate_ip_addr_to_node_id(other_ip_addr)

        self.network_utilization_inspector.add_new_connection(node_id, network_packet.total_size, is_incoming_packet)

    def do_service_send_callback(self, duplicate_service, reason=None):
        """Event to send the service to the next service manager instance.

        The service manager core gets the instruction to send the service to
        the next best host. The sending process is handled through the
        service manager core main loop.

        Args:
            duplicate_service (bool): Flag to indicate if the old service
                should be stopped after a completed sending of the service.

            reason(:obj:`str`, optional): reason of the sending process.
        """

        if duplicate_service is True:
            pass
            #self.duplicate_service_event.set()
        else:
            self.migrate_service_event.set()

    def no_recent_connections_callback(self):
        """Event to inform if no recent connections where made to the service.

        The service manager core gets informed if no recent connections where created in the last migration cycle. The event will start an broadcast information routine to all clients in the network.
        """

        LOGGER.info("no recent connections found!")
        self.no_recent_connections_event.set()

    def calculate_central_node_callback(self, recent_in_out_packets, recent_in_out_packets_total):
        """Event to start the calculation of the next best service host.

        On every migration cycle end, this method will be called to start a
        calculation of the next best host to run the service.

        Args:
            recent_in_out_packets (:obj:`dict` of :obj:`dict` of :obj:`int`):
                A dictionary, containing all recently with the service
                connected client hosts and the amount of the incoming and
                outgoing traffic in this time slot.
            recent_in_out_packets_total(:obj:`int`): The total number of
                recent incoming and outgoing data traffic, measured in bytes.

        Returns:
            A list of the the next best host to run the service, calculated on
            the basis of recent connections as well as incoming and outgoing packets of the recent connections.
        """

        return self.network_router.calculcate_central_node_from_recent_connections(
            recent_in_out_packets,
            recent_in_out_packets_total)

    def run(self):
        """The main running loop of the service manager core.

        The service manager core handles all main events in this loop, which
        influences the main functionalities about the service, e.g. starting,
        stopping, and migrating the service, in an ordinary order to minimize
        side effects.
        """

        if self.configuration.testing is False:
            self.network_router.add_all_network_routes()

        while True:
            try:
                if self.start_service_event.is_set() is True and \
                   os.path.exists(self.configuration.service_file) is True:
                    LOGGER.info("main loop start service")
                    self.start_service_event.clear()
                    try:
                        service_status, service_error = self.service_handler.start_service()
                        if service_status == ServiceStatusCodes.STARTED_NORMALLY:
                            migration_check_status = self.network_utilization_inspector.start_forever()
                            LOGGER.info("Migration check status="+str(migration_check_status))
                        else:
                            LOGGER.error("Service could not be started: " + str(service_error))
                    except Exception as exc:
                        LOGGER.error('Error while starting service, Error='+str(exc))

                if self.stop_service_event.is_set() is True:
                    self.stop_service_event.clear()
                    LOGGER.info("main loop stop service")

                    self.network_utilization_inspector.cancel_migration_check()

                    if self.service_handler.stop_service() is True:
                        self.service_handler.delete_service_and_reset_status()

                if self.no_recent_connections_event.is_set() is True:
                    self.no_recent_connections_event.clear()
                    self.service_handler.send_broadcast_event("service", "started")

                if self.migrate_service_event.is_set() is True or \
                   self.duplicate_service_event.is_set() is True:
                    LOGGER.debug("main loop send service")
                    self.migrate_service_event.clear()

                    new_nodes = self.network_utilization_inspector.get_best_new_choosen_nodes()

                    self.network_utilization_inspector.cancel_migration_check()
                    service_sent_successful, service_sent_error_code = \
                        self.service_transporter.send_service(new_nodes,
                                                              self.configuration.service_file)

                    LOGGER.debug("main loop migrate: service_sent_successful=%s, service_sent_error_code=%s",
                                 service_sent_successful,
                                 service_sent_error_code)
                    if service_sent_successful is True:
                        if self.duplicate_service_event.is_set() is False:
                            self.service_handler.stop_service()

                        self.duplicate_service_event.clear()
                    else:
                        migration_check_status = self.network_utilization_inspector.start_forever()
                        LOGGER.info("Migration check has been started again, migration_check_status=%s",
                                    migration_check_status)
                        LOGGER.error("Service could not be migrated: " +
                                     str(service_sent_error_code))
            except Exception as exc:
                LOGGER.error('Error while migration, Error=%s', exc)

            time.sleep(0.001)
                