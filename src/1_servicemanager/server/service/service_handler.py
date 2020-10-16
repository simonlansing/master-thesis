"""This module contains all classes to handle the service.

The starting and stopping of a service is done by open the service in a
external subprocess inside the same process group. This will stop the service,
if the service manager will be closed. Another functionality of this class is
the informing of other hosts about the starting and stopping process of the
service with a broadcast message.
"""

import inspect
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from utils import RepeatedTimer
from utils import Networking

LOGGER = logging.getLogger(__name__)

class ServiceStatusCodes(object):
    """This class contains the possible status codes for the service.

    The codes are used to determine the current status of the service itself.
    If the service is started, stopped or in transmission, this codes will be
    used. And if there occurs any error in the starting process, this codes
    will be used to express it.
    """

    NOT_STARTED_YET = 'NOT_STARTED_YET'
    STARTED_NORMALLY = 'STARTED_NORMALLY'
    ERROR_STARTING_SERVICE = 'ERROR_STARTING_SERVICE'
    IN_TRANSMISSION = 'IN_TRANSMISSION'

class ServiceHandler(object):
    """This class handles the service itself.

    This ServiceHandler class starts and stops the service in a separate
    process and informs all hosts using this service by sending a broadcast
    message through the network.

    Attributes:
        BROADCAST_PORT (:obj:`int`): The port to broadcast changes to the
            service status.
        service (:obj:`subprocess`): The process of the service.
        service_ports (:obj:`list` of :obj:`int`): The opend and used ports of
            the service.
        service_status (:obj:`(ServiceStatusCodes,str)`): The current status
            of the service.
        service_id (:obj:`int`): The unique ID of the service instance.
        open_ports_check (:obj:`RepeatedTimer`): A timer to check the ports of
            the service.
        server_broadcast_socket (:obj:`socket`): Socket to broadcast changes
            to the service status.
    """

    BROADCAST_PORT = 6500

    def __init__(self, service_manager, configuration):
        """The initialization function of the class ServiceHandler.

        The function initializes the ServiceHandler instance and extracts all needed information to run and stop the service.

        Args:
            service_manager (:obj:`ServiceManager`): The instance of the
                service manager core to extract the informations.
            configuration (:obj:`optparse.Option`): The configuration of the
                command line interface, e.g. to extract the service file path.
        """

        self.configuration = configuration
        self.testing_flag = configuration.testing
        self.service_file_name_path = configuration.service_file
        self.own_node_id = service_manager.get_own_hostname_callback()
        self.cb_new_service_ports_found = service_manager.found_service_ports_callback

        self.service = None
        self.service_ports = []
        self.service_status = (ServiceStatusCodes.NOT_STARTED_YET, None)
        self.service_status_lock = threading.RLock()

        self.service_id = 1 # the id of the current service instance in the network
                            # (will be updated after receiving a service)

        self.open_ports_check = RepeatedTimer(5, self.get_open_ports_of_service)

        self.server_broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.server_broadcast_socket.bind(('', self.BROADCAST_PORT))
        self.server_broadcast_event = threading.Event()
        self.server_broadcast_thread = threading.Thread(target = self.listen_for_whois_requests, args=())
        self.server_broadcast_thread.daemon = True
        self.server_broadcast_thread.start()

        LOGGER.debug("service handler init")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("service handler exit")
        self.open_ports_check.cancel()
        self.server_broadcast_event.set()
        self.stop_service()
        return self

    def listen_for_whois_requests(self):
        """Listens for requests from hosts who don't know the current server.

        The function listens for hosts and answers them directly, if they don't know the current host, who runs the service.
        """

        while self.server_broadcast_event.is_set() is False:
            try:
                new_message, address = self.server_broadcast_socket.recvfrom(16384)
                new_message = json.loads(new_message)

                if new_message['event'] == "who_is":
                    status, _ = self.get_service_status()
                    if status == ServiceStatusCodes.STARTED_NORMALLY:
                        own_server_ip = Networking.translate_node_id_to_ip_addr(self.own_node_id)

                        LOGGER.info("who_is message from %s = %s", address, new_message)
                        publish_options = {}
                        publish_options['service_name'] = "service"
                        publish_options['event'] = "who_is_answer"
                        publish_options['server_ip'] = own_server_ip
                        publish_options['counter'] = self.service_id
                        
                        try:
                            who_is_answer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            who_is_answer_socket.sendto(json.dumps(publish_options), (address[0], self.BROADCAST_PORT))
                            who_is_answer_socket.close()
                        except socket.error as exc:
                            LOGGER.error('Failed to answer who_is (socket.error): ' + str(exc), exc_info=True)

            except Exception as exc:
                LOGGER.error("Error while receiving broadcast message,\naddress=%s,\nmessage=%s\nError=%s", address, new_message, exc, exc_info=True)
                #except Exception as exc:
                #    LOGGER.error("Error while releasing the current lock, Error={}".format(exc))

        self.server_broadcast_socket.close()

    @staticmethod
    def __get_class_from_frame(depth):
        frame = inspect.stack()[depth][0]
        args, _, _, value_dict = inspect.getargvalues(frame)
        # we check the first parameter for the frame function is
        # named 'self'
        if len(args) and args[0] == 'self':
            # in that case, 'self' will be referenced in value_dict
            instance = value_dict.get('self', None)
            if instance:
                # return its class
                return getattr(instance, '__class__', None)
        # return None otherwise
        return None

    @staticmethod
    def __get_calling_class():
        return ServiceHandler.__get_class_from_frame(4)

    @staticmethod
    def __get_full_calling_class_name():
        calling_class = ServiceHandler.__get_class_from_frame(4)
        return calling_class.__module__ + "." + calling_class.__name__

    def get_service_configuration(self):
        """Gets the current service configuration as a tuple.

        If the service is running, the service ID and the open ports are the informations of the service needed in other classes.

        Returns:
            the service ID and the opened ports of the service.
        """

        return self.service_id, self.service_ports

    def set_service_configuration(self, service_id, service_ports):
        """Sets the current service configuration.

        If the service is freshly received on the service manager, this
        function will be called for the first configuration. Since the
        previous service manager already collected ports, they will be used
        and set here for sniffing purposes.

        Args:
            service_id (:obj:`int`): The new ID of the service.
            service_ports (:obj:`list` of :obj:`int`): The current ports of
                the service.
        """

        self.service_id = service_id

        if self.BROADCAST_PORT in service_ports:
            service_ports.remove(self.BROADCAST_PORT)
        if self.configuration.service_transporter_port in service_ports:
            service_ports.remove(self.configuration.service_transporter_port)

        self.service_ports = service_ports

    def set_service_status(self, status, error=None):
        """Sets the current service status.

        If the service is in transportation, an error occurred or started successfully, the service status is used to inform this.

        Args:
            status (:obj:`str`): status of the service from ServiceStatusCodes.
            error (:obj:`str`, optional): The occurred error of the status, if
                available.
        """

        try:
            self.service_status_lock.acquire()
            self.service_status = status, error
        finally:
            self.service_status_lock.release()

    def get_service_status(self):
        """Gets the current service status.

        If the service is in transportation, an error occurred or started successfully, the service status is used to inform this.

        Returns:
            the current status of the service.
        """

        try:
            calling_class = self.__get_full_calling_class_name()
            LOGGER.info("Returning service status %s to %s", self.service_status, calling_class)
            #self.service_status_lock.acquire()
            return self.service_status
        finally:
            pass
            #self.service_status_lock.release()

    def delete_service_and_reset_status(self):
        """Deletes all files of the service and resets the status.

        In any error case the service can be reset back with this method.

        Returns:
            True if reset was successful, False in any other case.
        """

        try:
            LOGGER.info("Resetting service now.")
            if os.path.exists(self.service_file_name_path):
                os.remove(self.service_file_name_path)
            self.open_ports_check.cancel()
            self.service_ports = []
            self.set_service_status(ServiceStatusCodes.NOT_STARTED_YET, None)
            return True
        except Exception as exc:
            LOGGER.error("Error while resetting service: %s", exc)
            return False

        return False

    def seperate_ipv4_and_port(self, combined_ip_port):
        """Helper function to seperate the IPv4 address and the port.

        Returns:
            A tuple of the IP address and the port number.
        """

        ip_and_port = combined_ip_port.split(':')
        port = ip_and_port.pop()
        #support for IPv6 addresses
        ip_address = ':'.join(ip_and_port)
        return ip_address, port

    def get_open_ports_of_service(self):
        """Callback method of the repeated timer to find open ports.

        This method is called after several seconds to check if there are any open ports of the service in the system.
        """

        try:
            pid = self.service.pid
            command = "netstat -tlnup | awk 'NR>2 { print $4, $7; }'"
            command = "netstat -tlnup | awk 'NR>2 { print $1, $4, $6, $7;}'"
            netstat_output = subprocess.check_output(command, shell=True)

        except subprocess.CalledProcessError as e:
            LOGGER.error("Error while getting open ports of service, Error="+ str(e))
        else:
            found_ports = []
            for line in netstat_output.split('\n'):
                values = line.split(' ')
                if len(values) > 1:
                    if values[0] == "tcp" and values[3] == (str(pid) + "/python") or \
                       values[0] == "udp" and values[2] == (str(pid) + "/python"):
                        ip_address, port = self.seperate_ipv4_and_port(values[1])
                        if port not in found_ports:
                            found_ports.append(int(port))

            if found_ports:
                self.open_ports_check.cancel()

            for port in found_ports:
                if port not in self.service_ports:
                    if port != self.BROADCAST_PORT and \
                       port != self.configuration.service_transporter_port:
                        self.service_ports.append(port)

            self.cb_new_service_ports_found(self.service.pid, self.service_ports)

    def send_broadcast_event(self, service_name, event):
        """Method to send an event to all hosts in the network.

        This method sends a broadcast message with the current service status
        to all hosts in the network.
        """

        broadcast_addresses = ["10.0.0.255"]
        if self.testing_flag is False:
            broadcast_addresses.append("10.0.1.255")
            broadcast_addresses.append("10.0.2.255")

        Networking.broadcast_service_status(
            broadcast_addresses,
            self.own_node_id,
            service_name, event,
            self.service_id)

    def start_service(self):
        """Method to start the service in an own subprocess.

        This method starts the service in an own subprocess, informs all hosts
        in the network via broadcast and returns the new service status to the
        calling functions.

        Returns:
            The new service status.
        """

        try:
            # The os.setsid() is passed in the argument preexec_fn so
            # it's run after the fork() and before exec() to run the shell.
            self.service = subprocess.Popen([sys.executable, self.service_file_name_path])
                                            #close_fds=True,# shell=True,
                                            #preexec_fn=os.setsid)
            LOGGER.info("Started service with pid="+str(self.service.pid))
            
            self.open_ports_check.start()
            # if there are already service ports inside the list (from the last migration process)
            # inform the service manager core about these
            if self.service_ports:
                self.cb_new_service_ports_found(self.service.pid, self.service_ports)

            self.set_service_status(ServiceStatusCodes.STARTED_NORMALLY, None)

            self.send_broadcast_event("service", "started")
        except OSError as exc:
            LOGGER.error("Failed to start service (OSError): %s", exc, exc_info=True)
            self.set_service_status(ServiceStatusCodes.ERROR_STARTING_SERVICE, exc)
        except Exception as exc:
            LOGGER.error("Failed to start service: %s", exc, exc_info=True)
            self.set_service_status(ServiceStatusCodes.ERROR_STARTING_SERVICE, exc)

        return self.get_service_status()

    def stop_service(self):
        """Method to stop the service.

        This method stops the service and informs all hosts in the network via broadcast, that the service has been stopped.

        Returns:
            True if the service has been stopped, False in any occurred error.
        """
        try:
            LOGGER.info("trying to stop service")
            self.send_broadcast_event("service", "stopped")

            if self.service:
                #os.killpg(os.getpgid(self.service.pid), signal.SIGTERM)
                os.kill(self.service.pid, signal.SIGINT)
                # self.service.send_signal(signal.SIGINT)

                # if self.service.wait() == 0:
                #     logger.info("Successful terminated the running service")
                # else:
                #     logger.info("Error while terminating running service. Kill it instead")
                #     os.kill(self.service.pid, signal.SIGINT)

                self.service = None
                self.set_service_status(ServiceStatusCodes.NOT_STARTED_YET, None)

        except Exception as exc:
            LOGGER.error("Could not kill process group: %s", exc, exc_info=True)
            return False

        return True

    """Old functions from the previous middleware concept.

    def stop_service_v1(self):
        logger.debug("stop_service enter")
        self.broadcast_service_status_to_clients(self.own_node_id, None, "stopped")
        for i, config in enumerate(self.service_ports_settings):
            self.service_ports_settings[i]['socket'].close()

    def start_service_v1(self):
        logger.debug("service handler start_service")

        try:
            #self.service_status_lock.acquire()
            self.service = imp.load_source('service', self.service_file_name_path)
            self.service_ports_settings = [{} for x in range(len(self.service.SERVICE_CONFIG))]

            for i, config in enumerate(self.service.SERVICE_CONFIG):
                new_port_setting = {
                    'client_count' : 0,
                    'socket' : socket.socket(socket.AF_INET, config[1]),
                    'thread' : threading.Thread(target=self.run_service_port, args=(i,))
                }
                new_port_setting['socket'].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                new_port_setting['thread'].daemon = True
                self.service_ports_settings[i] = new_port_setting
                self.service_ports_settings[i]['thread'].start()

            self.set_service_status(ServiceHandler.service_status_codes.STARTED_NORMALLY, None)
            return self.get_service_status()
        except SyntaxError as e:
            logger.error("Failed to start service (SyntaxError): " + str(e), exc_info=True)
            self.set_service_status(ServiceHandler.service_status_codes.ERROR_STARTING_SERVICE, e)
            #raise SystemError("Failed to start service (SyntaxError): " + str(e))
            return self.get_service_status()
        except Exception as e:
            logger.error("Failed to start service: " + str(e), exc_info=True)
            self.set_service_status(ServiceHandler.service_status_codes.ERROR_STARTING_SERVICE, e)
            return self.get_service_status()
        finally:
            self.broadcast_service_status_to_clients(None, "started")
            #self.service_status_lock.release()

    def run_service_port(self, config_id):
        logger.debug("service handler run_service_port: " + str(config_id))

        try:
            self.service_ports_settings[config_id]['socket'].bind(('', self.service.SERVICE_CONFIG[config_id][0]))
        except socket.error as e:
            logger.error("Failed to bind service sockets (socket.error): " + str(e), exc_info=True)
            thread.interrupt_main()
        except Exception as e:
            logger.error("Failed to bind service sockets: " + str(e), exc_info=True)
            thread.interrupt_main()

        #backlog is set to default value. defined in /proc/sys/net/core/somaxconn
        self.service_ports_settings[config_id]['socket'].listen(128)

        while True:
            try:
                conn, addr = self.service_ports_settings[config_id]['socket'].accept()
                self.service_ports_settings[config_id]['client_count'] += 1
                self.cb_connection_counter_changed(addr)
                logger.info("Connected with " + addr[0] + ":" + str(addr[1]))
                self.connected_client_thread = threading.Thread(target=self.service.SERVICE_CONFIG[config_id][2], args=(conn,))
                self.connected_client_thread.start()
            except socket.error as e:
                logger.error("Failed to accept socket (socket.error): " + str(e), exc_info=True)
            except Exception as e:
                logger.error("Failed to accept socket: " + str(e), exc_info=True)

        return
    """
