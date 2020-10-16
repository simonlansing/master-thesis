"""The module contains the functions to check a migration possibility

The NetworkUtilizationInspector of this module checks after every migration
cycle, if there is a better host to run the service. This information will be
sent to the service manager core.
"""

import logging
import subprocess
import threading
from collections import defaultdict
from utils import RepeatedTimer

LOGGER = logging.getLogger(__name__)

class NetworkUtilizationInspector(object):
    """This class checks a possible migration for the platform.

    This NetworkUtilizationInspector class checks the collected data from the
    NetworkSniffer and calculates with functions from the NetworkRouter the
    next possible service host. If the hosts is on a better position than this
    host, the migration will be informed to the service manager core.

    Attributes:
        check_connections_timer (:obj:`RepeatedTimer`): Timer to repeat the
            process of the migration cycle
        connection_check_lock (:obj:`threading.Lock`): A lock that no two or
            more checks could occur in the same time.
        recent_in_out_packets (:obj:`dict` of :obj:`dict` of :obj:`int`):
            A dictionary, containing all recently with the service
            connected client hosts and the amount of the incoming and
            outgoing traffic in this time slot.
        recent_in_out_packets_total(:obj:`int`): The total number of recent
            incoming and outgoing data traffic, measured in bytes.
        best_new_choosen_nodes (:obj:`list` of :obj:`(int, int)`): A sorted
            list of all possible service hosts.
        check_cpu_ram_timer (:obj:`RepeatedTimer`): Timer to repeatedly check
            the current CPU and RAM status of the service on the host.
        cpu_ram_check_lock (:obj:`threading.Lock`): A lock that no two or
            more checks could occur in the same time.
    """

    def __init__(self, service_manager, configuration):
        """The initialization function of the NetworkUtilizationInspector.

        The function initializes the NetworkUtilizationInspector instance and
        registers all callback functions of the service manager core for its
        own functions.

        Args:
            service_manager (:obj:`ServiceManager`): The instance of the
                service manager core to extract the callback functions.
            configuration (:obj:`optparse.Option`): The configuration of the
                command line interface, e.g. to extract the possible server 
                hosts.
        """

        LOGGER.debug("migration_checker init")

        self.recent_cpu_ram_check_flag = False
        self.migration_flag = configuration.migration
        self.testing_flag = configuration.testing
        self.server_hosts = configuration.server_hosts
        self.own_node_id = service_manager.get_own_hostname_callback()

        self.connection_check_time = configuration.connection_check_time
        self.cpu_ram_check_time = configuration.cpu_ram_check_time
        self.cpu_threshold = configuration.cpu_threshold
        self.ram_threshold = configuration.ram_threshold
        self.migration_threshold = configuration.migration_threshold

        self.cb_send_service = service_manager.do_service_send_callback
        self.cb_no_recent_connections = service_manager.no_recent_connections_callback
        self.cb_calculate_central_node = service_manager.calculate_central_node_callback

        #self.own_pid = os.getpid()
        self.check_connections_timer = None
        self.connection_check_lock = threading.Lock()
        self.recent_in_out_packets = defaultdict(lambda: defaultdict(int))
        self.recent_in_out_packets_total = 0
        self.best_new_choosen_nodes = None

        self.check_cpu_ram_timer = None
        self.service_pid = None
        self.cpu_ram_check_lock = threading.Lock()
        self.recent_cpu_ram_usage = {'cpu': 0.0, 'ram': 0.0, 'counter':0}

    def __enter__(self):
        LOGGER.debug("migration_checker enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("migration_checker exit")
        self.cancel_migration_check()
        return self

    def start_forever(self):
        """The external interface method to start the migration check.

        The method starts the main functionality of the NetworkUtilizationInspector by starting the repeated timers.

        Returns:
            True on successful start of the migration check cycle,
            False on any error.
        """

        if self.migration_flag is True:
            LOGGER.info("starting migration check forever")
            try:
                if self.check_connections_timer and self.check_connections_timer.is_alive():
                    self.check_connections_timer.cancel()
                    self.check_connections_timer.join()

                if self.check_cpu_ram_timer and self.check_cpu_ram_timer.is_alive():
                    self.check_cpu_ram_timer.cancel()
                    self.check_cpu_ram_timer.join()

                self.check_connections_timer = RepeatedTimer(
                    self.connection_check_time,
                    self.check_recent_connections_for_best_server)
                self.check_connections_timer.start()

                # self.check_cpu_ram_timer = RepeatedTimer(
                #     self.cpu_ram_check_time,
                #     self.check_recent_cpu_and_ram_usage,
                #     self.service_pid)
                # self.check_cpu_ram_timer.start()
                return True
            except Exception as exc:
                LOGGER.error("cannot start migration check, Error="+str(exc))
                return False
        else:
            return False

    def cancel_migration_check(self):
        """The external interface method to cancel the migration check.

        The method cancels the main functionality of the
        NetworkUtilizationInspector by canceling the repeated timers.
        """

        if self.check_connections_timer is not None:
            self.check_connections_timer.cancel()
        if self.check_cpu_ram_timer:
            self.check_cpu_ram_timer.cancel()

    def check_recent_cpu_and_ram_usage(self, args=None):
        """The callback method to check the current CPU and RAM of the service.

        The method is called repeatedly and checks the current CPU and RAM
        usage of the service. The values are summed up, so that an average
        value can be created.
        """

        try:
            self.cpu_ram_check_lock.acquire()
            if args is None:
                pid = None
            else:
                pid = args[0]
            #LOGGER.info("check_recent_cpu_and_ram_usage, pid="+str(pid))

            #remove for further investigations in total CPU and RAM usage
            if pid is None:
                return

            command = "/usr/bin/top -b -n 1 -p " + str(pid) + " | awk 'NR>7 { cpu = $9; ram = $10 } END { print cpu, ram; }'"
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
            stdout = proc.stdout.read().replace(',', '.').split()
            #LOGGER.info(stdout)
            self.recent_cpu_ram_usage['cpu'] += float(stdout[0])
            self.recent_cpu_ram_usage['ram'] += float(stdout[1])
            self.recent_cpu_ram_usage['counter'] += 1
            #LOGGER.info(self.recent_cpu_ram_usage)
        except Exception as e:
            LOGGER.error("Failed while searching cpu and ram, pid=" + str(pid) + ", Error=" + str(e), exc_info=True)
        finally:
            self.cpu_ram_check_lock.release()

    def start_recent_cpu_and_ram_usage_timer(self, pid=None):
        """This method starts the check the current CPU and RAM of the service.

        The method is starts the repeated check for the current CPU and RAM
        usage of the service.

        Returns:
            True if successful start of the timer, False if the timer has not
            been started.
        """

        if self.migration_flag is True and self.recent_cpu_ram_check_flag is True:
            self.service_pid = pid
            self.check_cpu_ram_timer = RepeatedTimer(self.cpu_ram_check_time,
                                                     self.check_recent_cpu_and_ram_usage,
                                                     self.service_pid)
            self.check_cpu_ram_timer.start()
            return True
        else:
            return False

    def get_best_new_choosen_nodes(self):
        """This method returns the list of best hosts for running the service.

        Returns:
            A list of all possible hosts to run the service in descending
            order.
        """

        try:
            self.connection_check_lock.acquire()
            return self.best_new_choosen_nodes
        finally:
            self.connection_check_lock.release()

    def add_new_connection(self, node_id, packet_size, is_incoming_packet):
        """Adds a new incoming connection to the service to the list.

        If a new host has send a packet to the service, this will be saved
        into a dictionary. This information can be used to calculate the next
        best host to run the service.

        Args:
            node_id: (:obj:`int`): The ID of the connected host.
            packet_size (:obj:`int`): The size of the sent or received packet.
            is_incoming_packet (bool): Indicator, if the packet was incoming
                from or outgoing to the other host.
        """

        try:
            self.connection_check_lock.acquire()

            #if node_id not in self.recent_in_out_packets:
            #    self.recent_in_out_packets[node_id]['in'] = 0
            #    self.recent_in_out_packets[node_id]['out'] = 0

            if is_incoming_packet:
                self.recent_in_out_packets[node_id]['in'] += packet_size
            else:
                self.recent_in_out_packets[node_id]['out'] += packet_size

            self.recent_in_out_packets_total += packet_size

            #LOGGER.info("Added new connection from node {}".format(node_id))
        except Exception as exc:
            LOGGER.error("Failed while adding new connection: " + str(exc), exc_info=True)
        finally:
            #LOGGER.info("total counter: " + str(self.recent_in_out_packets_total))
            self.connection_check_lock.release()

    def calculate_avg_cpu_and_ram_out_of_recent_usage(self):
        """Checks the average cpu and ram usage of the service.

        This method is called once every migration cycle to check the average
        CPU and RAM usage value of the service. If the values is higher than
        threshold value, a duplication of the service could be made instead of
        a migration.

        Returns:
            the recent average value of the CPU and RAM usage of the service.
        """

        try:
            avg_cpu, avg_ram = 0.0, 0.0
            self.cpu_ram_check_lock.acquire()
            LOGGER.info(self.recent_cpu_ram_usage)
            if self.recent_cpu_ram_usage['counter'] > 0:
                avg_cpu = self.recent_cpu_ram_usage['cpu'] / self.recent_cpu_ram_usage['counter']
                avg_ram = self.recent_cpu_ram_usage['ram'] / self.recent_cpu_ram_usage['counter']

            self.recent_cpu_ram_usage = {'cpu': 0.0, 'ram': 0.0, 'counter':0}
            return avg_cpu, avg_ram

        except Exception as exc:
            LOGGER.error("Failed while checking recent connections: " + str(exc), exc_info=True)
        finally:
            self.cpu_ram_check_lock.release()

    def check_recent_connections_for_best_server(self):
        """Checks the recent connections to calculate the best host.

        This method is called once every migration cycle to check, which host
        is the best to run the service instance. It uses all gathered
        information from packets and hosts to allocate the best service. The
        results will be informed to the service manager core.
        """

        LOGGER.debug("enter")
        try:
            self.connection_check_lock.acquire()

            if self.recent_in_out_packets_total == 0:
                self.cb_no_recent_connections()
                return

            #LOGGER.debug("start calculating central node from recent connections\ntotal={},\nseperated={}".format(
            #    self.recent_in_out_packets_total,
            #    self.recent_in_out_packets))
            best_nodes = self.cb_calculate_central_node(
                self.recent_in_out_packets,
                self.recent_in_out_packets_total)

            if best_nodes is not [] and best_nodes[0][0] != self.own_node_id:
                # the instance variable can be set,
                # since the general connection_check_lock has been aquired
                self.best_new_choosen_nodes = []

                # remove the nodes from the list, which are not in the list of possible servers
                if self.server_hosts:
                    for node in best_nodes:
                        if node[0] in self.server_hosts:
                            self.best_new_choosen_nodes.append(node)
                else:
                    self.best_new_choosen_nodes = best_nodes

                LOGGER.info("Best Nodes: " + str(self.best_new_choosen_nodes))

                # if the value between the best new server and the already running server is smaller than the migration threshold, do not migrate
                for node in self.best_new_choosen_nodes:
                    if node[0] == self.own_node_id:
                        best_node_value = self.best_new_choosen_nodes[0][1]
                        own_value = node[1]

                        LOGGER.info("Me=%s, Other=%s", node, self.best_new_choosen_nodes[0])
                        # if there is only one host connecting, this host should be the new server, since it has a value of 0.0
                        if best_node_value > 0.0:
                            percentage_difference = own_value / best_node_value
                            LOGGER.info("own_val=%s, best_val=%s, per_diff=%s, mig_trsh=%s",
                                        own_value, best_node_value, percentage_difference, self.migration_threshold)

                            if percentage_difference < (1 + (self.migration_threshold / 100)):
                                LOGGER.info("The new server wouldn't be really better as a server. Migration rejected.")
                                return

                avg_cpu, avg_ram = self.calculate_avg_cpu_and_ram_out_of_recent_usage()
                LOGGER.info("avg cpu=" + str(avg_cpu) + ", avg ram=" + str(avg_ram))

                if avg_cpu > self.cpu_threshold or avg_ram > self.ram_threshold:
                    self.cb_send_service(True)
                else:
                    self.cb_send_service(False)
            else:
                LOGGER.info("No node as best server found! best_node=" + str(best_nodes))
        except Exception as exc:
            LOGGER.error("Failed while checking recent connections: " + str(exc), exc_info=True)
        finally:
            #self.recently_connected_nodes_counter = {}
            self.recent_in_out_packets = defaultdict(lambda: defaultdict(int))
            self.recent_in_out_packets_total = 0
            self.connection_check_lock.release()
            LOGGER.debug("exit")
