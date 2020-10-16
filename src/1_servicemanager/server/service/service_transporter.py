"""This module contains all classes to transport the service.
    
The transportation of a service is done by sending all service files from one
service manager to another. After a successful transportation this module will
inform the upper class via callback functions to proceed with the next steps.
"""

import json
import logging
import socket
import sys
import threading
from service import ServiceStatusCodes
from utils import Networking

LOGGER = logging.getLogger(__name__)

class TransportStatusCodes(object):
    """This class contains the possible status codes while the transportation.
    
    The codes are used to determine the current positive and negative status
    of the service transportation. If there occurs any error in the
    transportation algorithm, this codes will be used to express them.
    """

    OKAY = 'OKAY'
    ACCEPTED = 'ACCEPTED'
    NOT_FOUND = 'NOT_FOUND'
    CONFLICT = 'CONFLICT'
    LOCKED = 'LOCKED'
    INTERNAL_SERVER_ERROR = 'INTERNAL_SERVER_ERROR'
    TRANSPORT_ERROR = 'TRANSPORT_ERROR'
    SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE'
    GATEWAY_TIMED_OUT = 'GATEWAY_TIMED_OUT'

class ServiceTransporter(object):
    """This class transports the service between several service managers.

    This ServiceTransporter class sends all files of the service with an own
    application protocol on a TCP connection. Any error or the complete
    transportation process will be informed to the higher class through
    callback functions.

    Attributes:
        GLOBAL_TIMEOUT (:obj:`float`): The time when a timeout will be raised
            in the process of service transportation.
        service_file_name_path (:obj:`str`): The path to the service file.
        server_port (:obj:`int`): The configured port for transportation.
        server_socket (:obj:`socket`): The socket to transport the service.
        receive_service_lock (:obj:`threading.Lock`): A lock, in order to
            block receiving more than one service at the same time.
        send_service_lock (:obj:`threading.Lock`): A lock, in order to
            block sending more than one service at the same time.
        server_thread (:obj:`threading.Thread`): The thread to receive the
            service files, if no service is active on this host.
    """

    GLOBAL_TIMEOUT = 180.0

    def __init__(self, service_manager, configuration):
        """The initialization function of the class ServiceTransporter.

        The function initializes the ServiceTransporter instance and registers
        all callback functions of the service manager core for its own
        functions.

        Args:
            service_manager (:obj:`ServiceManager`): The instance of the
                service manager core to extract the callback functions.
            configuration (:obj:`optparse.Option`): The configuration of the
                command line interface to extract the transportation port.
        """

        self.cb_get_service_status = service_manager.get_service_status_callback
        self.cb_set_service_status = service_manager.set_service_status_callback
        self.cb_get_service_configuration = service_manager.get_service_config_callback
        self.cb_set_service_configuration = service_manager.set_service_config_callback
        self.cb_reset_service = service_manager.do_service_reset_callback
        self.cb_service_received = service_manager.service_received_callback
        self.cb_handshake_error = service_manager.do_service_stop_callback

        self.service_file_name_path = configuration.service_file
        self.server_port = configuration.service_transporter_port

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.receive_service_lock = threading.Lock()
        self.send_service_lock = threading.Lock()

        self.server_thread = threading.Thread(target=self.run, args=())
        self.server_thread.daemon = True
        self.server_thread.start()

        #LOGGER.debug("service transporter init")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("service transporter exit")
        self.server_socket.close()
        return self

    def run(self):
        """The run function of the transportation thread.

        The function listens to the external transportation port and waits for
        an incoming service file.
        """

        try:
            self.server_socket.bind(('0.0.0.0', self.server_port))
        except socket.error as e:
            LOGGER.error("Failed to bind transporter socket: " + str(e), exc_info=True)
            sys.exit(1)

        #https://stackoverflow.com/questions/12340047/uwsgi-your-server-socket-listen-backlog-is-limited-to-100-connections
        #set the backlog to zero (backlog is the number of pending, but not yet accepted client connections.)
        self.server_socket.listen(0)

        while True:
            conn, addr = self.server_socket.accept()
            LOGGER.info("Connected with " + addr[0] + ":" + str(addr[1]))
            connected_client_thread = threading.Thread(target=self.receive_service, args=(conn,))
            connected_client_thread.start()

    def receive_service(self, conn):
        """The function to receive a service.

        The function is called after an external connection is incoming. If
        there is no own service running on the service manager, the functions
        begins to receive the service. After the completion, the service will
        be started.

        Args:
            conn (:obj:`socket`): The socket of the other service manager to
                receive the service.
        """

        service_status, _ = self.cb_get_service_status()

        try:
            if service_status != ServiceStatusCodes.NOT_STARTED_YET:
                LOGGER.info("rejected connection due to conflicting service_status")
                Networking.send_packed(conn, TransportStatusCodes.CONFLICT, self.GLOBAL_TIMEOUT)
            #elif not self.receive_service_lock.acquire(False):
            #    LOGGER.debug("Could not acquire lock")
            #    networking.send_packed(conn, TransportStatusCodes.SERVICE_UNAVAILABLE, self.GLOBAL_TIMEOUT)
            else:
                try:
                    self.cb_set_service_status(ServiceStatusCodes.IN_TRANSMISSION, None)
                    #self.receive_service_lock.acquire()

                    Networking.send_packed(conn, TransportStatusCodes.ACCEPTED, self.GLOBAL_TIMEOUT)
                    LOGGER.info("accepted connection to receive service")

                    raw_service_data = Networking.recv_packed(conn, self.GLOBAL_TIMEOUT)

                    if isinstance(raw_service_data, str) and len(raw_service_data) > 0:
                        new_service_configuration = json.loads(raw_service_data)

                        service = new_service_configuration['service']
                        self.cb_set_service_configuration(new_service_configuration['counter'],
                                                          new_service_configuration['ports'])
                        LOGGER.info("New service uses the following ports={}".format(new_service_configuration['ports']))
                        if service is not None and len(service) > 0:
                            with open(self.service_file_name_path, 'wb') as service_file:
                                service_file.write(service)
                        else:
                            Networking.send_packed(conn, TransportStatusCodes.TRANSPORT_ERROR, self.GLOBAL_TIMEOUT)
                            raise IOError('timed out while receiving or writing file')
                    else:
                        Networking.send_packed(conn, TransportStatusCodes.TRANSPORT_ERROR, self.GLOBAL_TIMEOUT)
                        raise IOError("Raw Service Data is corrupt!")
                except (socket.error, socket.timeout, OSError, IOError) as exc:
                    LOGGER.error("Failed while receiving file: " + str(exc), exc_info=True)
                    self.cb_reset_service()
                    #self.service_handler.set_service_status(ServiceStatusCodes.NOT_STARTED_YET, None)
                    #if os.path.exists(self.service_file_name_path):
                    #    os.remove(self.service_file_name_path)
                except Exception as exc:
                    LOGGER.error("FAILED: " + str(exc), exc_info=True)
                    self.cb_reset_service()
                else:
                    try:
                        LOGGER.info("Successful received service, starting now.")
                        service_status, _ = self.cb_service_received()
                        if service_status == ServiceStatusCodes.STARTED_NORMALLY:
                            Networking.send_packed(conn, TransportStatusCodes.OKAY, self.GLOBAL_TIMEOUT)
                        elif service_status == ServiceStatusCodes.ERROR_STARTING_SERVICE:
                            Networking.send_packed(conn, TransportStatusCodes.INTERNAL_SERVER_ERROR, self.GLOBAL_TIMEOUT)
                            self.cb_reset_service()
                        LOGGER.info("service_status=%s", service_status)
                    except (socket.error, socket.timeout) as exc:
                        LOGGER.error("Failed while sending final handshake: %s", exc, exc_info=True)
                        self.cb_handshake_error()
                    except Exception as exc:
                        LOGGER.error("FAILED: %s", exc, exc_info=True)
                        self.cb_handshake_error()
                #finally:
                #    self.receive_service_lock.release()
        except (socket.error, socket.timeout) as exc:
            LOGGER.error("Failed while returning status: %s", exc, exc_info=True)
            self.cb_handshake_error()
        except Exception as exc:
            LOGGER.error("FAILED: %s", exc, exc_info=True)
            self.cb_handshake_error()
        finally:
            LOGGER.info("Closing connection after receiving or error.")
            conn.close()

    def send_service(self, best_hosts, file_path):
        """The function to send a service.

        The function is called from the service manager core to send the
        service to another host. If the best host is not reachable after
        several retries, the next best one from the list will be used as new
        server. After the service has been send successfully, this event will
        be informed to the service manager core.

        Args:
            best_hosts (:obj:`list` of :obj:`int`): The list of the best hosts
                in descending order.
            file_path (:obj:`str`): The path to the service file.
        """

        LOGGER.debug("send_service enter")

        if not self.send_service_lock.acquire(False):
            return False, TransportStatusCodes.LOCKED

        try:
            send_socket = None
            connected = False  # Flag that indicates, if the server connection is up and running
            connection_attempts = 0
            connection_attempts_max = 10

            with open(file_path, 'rb') as service_file:
                for new_host in best_hosts:
                    while connection_attempts < connection_attempts_max:
                        try:
                            send_socket = socket.socket()
                            node_ip_address = Networking.translate_node_id_to_ip_addr(new_host[0])
                            #LOGGER.info("Try to connect to host {} with IP {}".format(new_host, node_ip_address))
                            send_socket.settimeout(self.GLOBAL_TIMEOUT)
                            send_socket.connect((node_ip_address, self.server_port))
                            send_socket.settimeout(None)
                            connected = True
                            LOGGER.info("Connection to IP {} established".format(node_ip_address))
                            break
                        except (socket.timeout, socket.error) as exc:
                            LOGGER.error("Error while connecting to IP {}, (socket.timeout, socket.error)={}".format(
                                node_ip_address, exc))
                            if send_socket is not None:
                                send_socket.close()
                            connection_attempts += 1
                            connected = False
                        except Exception as exc:
                            LOGGER.error("Error while connecting to IP {}, Exception={}".format(node_ip_address, exc))
                            if send_socket is not None:
                                send_socket.close()
                            connection_attempts += 1
                            connected = False
                    if connected is True:
                        break

                if connected is True:
                    migration_status = Networking.recv_packed(send_socket, self.GLOBAL_TIMEOUT)
                    #LOGGER.info("migration status code by other server: " + str(migration_status))

                    #the service migration has been accepted and can be started
                    if migration_status == TransportStatusCodes.ACCEPTED:

                        new_service_id, open_service_ports = self.cb_get_service_configuration()
                        new_service_id += 1
                        new_service_configuration = {'counter': new_service_id,
                                                     'ports': open_service_ports,
                                                     'service':service_file.read()}

                        if Networking.send_packed(
                                send_socket,
                                json.dumps(new_service_configuration),
                                self.GLOBAL_TIMEOUT) is None:
                            new_service_status = Networking.recv_packed(send_socket, self.GLOBAL_TIMEOUT)
                            LOGGER.info("service status code by other server: %s", new_service_status)
                            if new_service_status == TransportStatusCodes.OKAY:
                                return True, None
                            elif new_service_status == TransportStatusCodes.INTERNAL_SERVER_ERROR:
                                return False, TransportStatusCodes.INTERNAL_SERVER_ERROR
                            elif new_service_status == TransportStatusCodes.TRANSPORT_ERROR:
                                return False, TransportStatusCodes.TRANSPORT_ERROR

                    #the service is already running on the other server, the migration has to be stopped
                    elif migration_status == TransportStatusCodes.CONFLICT:
                        LOGGER.info("service status code from other server before transmission: %s", migration_status)
                        return False, TransportStatusCodes.CONFLICT
                    #the migration is already running from another server,
                    #so this migration is unavailable and should be stopped
                    #elif migration_status == TransportStatusCodes.SERVICE_UNAVAILABLE:
                    #    return False, TransportStatusCodes.SERVICE_UNAVAILABLE

                return False, TransportStatusCodes.NOT_FOUND
        except (OSError, IOError) as exc:
            LOGGER.error("Failed while sending file: " + str(exc))
            return False, str(exc)
        except (socket.error, socket.timeout) as exc:
            LOGGER.error("Failed while sending file (socket.error/timeout): " + str(exc))
            return False, str(exc)
        except Exception as exc:
            LOGGER.error("FAILED: " + str(exc), exc_info=True)
            return False, TransportStatusCodes.INTERNAL_SERVER_ERROR
        finally:
            send_socket.close()
            self.send_service_lock.release()
            #connected = False
