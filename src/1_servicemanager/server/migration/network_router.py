"""The module contains the functions to calculate the hosts for the service.

The NetworkRouter of this module uses the Dijkstra algorithm to calculates all
routes between the connected hosts and the possible service hosts to create a
descending ordered list of the best hosts to run the service.
"""

import datetime
import json
import logging
import operator
import subprocess
import sys
from collections import deque
from utils import Networking

LOGGER = logging.getLogger(__name__)

class NetworkRouter(object):
    """This class calculates the routes between hosts through the network.

    This NetworkRouter class uses the Dijkstra algorithm to calculates all
    routes between the connected hosts and the possible service hosts to
    create a descending ordered list of the best hosts to run the service.

    Attributes:
        routing_field (:obj:`str`): the field to use for weighting while
            calculating the routing.
        own_hostname (:obj:`str`): the name of the own host.
        adjacency_list (:obj:`list` of :obj:`list`): The adjacency list with
            the predefined routes in the network.
        nodes_connection_cost_table (:obj:`list` of :obj:`list`):
            a precalculated list of the costs from all host to all other.
        nodes_connection_hop_table (:obj:`list` of :obj:`list`):
            a precalculated list of the costs of hops from all host to all
            other.
    """

    def __init__(self, service_manager, configuration):
        """The initialization function of the class NetworkRouter.

        The function initializes the NetworkRouter instance and precalculates
        all needed informations for a fast main calculation of the best
        service running host.

        Args:
            service_manager (:obj:`ServiceManager`): The instance of the
                service manager core to extract the informations.
            configuration (:obj:`optparse.Option`): The configuration of the
                command line interface, e.g. to extract the adjacency list.
        """

        LOGGER.debug("network_routing init")
        self.testing_flag = configuration.testing
        self.own_hostname = None
        self.routing_field = 'etx'

        if self.testing_flag is False:
            cmd = "hostname | egrep -o [1-9]+[0-9]*"
            hostname_call = subprocess.Popen(cmd, shell=True,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.own_hostname = int(hostname_call.communicate()[0].strip())
            self.wireless_interfaces = Networking.get_wireless_interfaces()
            self.startup_wlan_interfaces(self.wireless_interfaces)
        else:
            try:
                cmd = "hostname --all-ip-addresses"
                hostname_call = subprocess.Popen(cmd, shell=True,
                                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.own_hostname = int(hostname_call.communicate()[0].split('.')[3].strip())
                #LOGGER.info("OWN HOSTNAME={}".format(self.own_hostname))
                self.wireless_interfaces = Networking.get_wireless_interfaces()
            except IndexError as exc:
                LOGGER.error("IndexError={}".format(sys.exc_info()[0]), exc_info=True)

        adjacency_list_loaded = False

        try:
            with open(configuration.adjacency_list_file, 'r') as adjacency_list_file:
                self.adjacency_list = json.load(adjacency_list_file)
                #LOGGER.info(self.adjacency_list)
                # remove the given unreachable hosts from the previously recorded adjacency list
                for unreachable_host in configuration.unreachable_hosts:
                    if isinstance(unreachable_host, (str, unicode)):
                        unreachable_host = int(unreachable_host)

                    self.adjacency_list[unreachable_host] = []

                for node in range(0, len(self.adjacency_list)):
                    for node_neighbor in self.adjacency_list[node]:
                        if node_neighbor.get('node') in configuration.unreachable_hosts:
                            self.adjacency_list[node].remove(node_neighbor)

                adjacency_list_loaded = True
        except IOError as exc:
            LOGGER.error("No adjacency file found on location {}, Error({})={}".format(
                configuration.adjacency_list_file,
                exc.errno, exc.strerror))
            adjacency_list_loaded = False
        except Exception as exc:
            LOGGER.error("Unexpected error={}".format(exc), exc_info=True)

        if adjacency_list_loaded is True:
            self.total_num_hosts = len(self.adjacency_list)
            # create table with negative values, so nodes
            # without connections are not used as service nodes
            self.nodes_connection_cost_table = [[-1.0 for x in range(self.total_num_hosts)] for y in range(self.total_num_hosts)]
            self.nodes_connection_hop_table = [[-1.0 for x in range(self.total_num_hosts)] for y in range(self.total_num_hosts)]

            if LOGGER.isEnabledFor(logging.DEBUG):
                time_a = datetime.datetime.now()

            self.calculate_nodes_connection_cost_table()
            #LOGGER.info("nodes connection cost table ={}".format(self.nodes_connection_cost_table))

            if LOGGER.isEnabledFor(logging.DEBUG):
                time_b = datetime.datetime.now()
                LOGGER.debug("Total time to calculate the nodes connection cost table: " + str(time_b - time_a))

    def get_own_hostname(self):
        """Method that returns the own name of the host."""
        return self.own_hostname

    def startup_wlan_interfaces(self, wireless_interfaces):
        """Method to start the wireless interfaces in MIOT-testbed.

        This methods starts up the wireless LAN interfaces of the MIOT-testbed nodes. Sometimes they are down and have to be started first.

        Args:
            wireless_interfaces (:obj:`list` of :obj:`str`): A list of all available wireless LAN interfaces of the host.
        """

        LOGGER.debug("starting up wlan interfaces")
        for interface in wireless_interfaces:
            cmd = "/sbin/ifconfig {} up".format(interface)
            out, error = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()
            if out:
                LOGGER.info("startup_wlan_interfaces, out=" + str(out))
            if error:
                LOGGER.error("Error while starting network interfaces: i=" + str(interface) + ", Error=" + str(error))

    def dijkstra(self, adjacency_list, initial):
        """Calculating the paths from an initial host to all other host

        This method calculates the paths from an initial host to all other
        hosts with the global adjacency list.

        Args:
            adjacency_list (:obj:`list` of :obj:`list`): The interpretation of
                the complete network to search paths in.
            initial (:obj:`int`): The hosts to start the algorithm from.

        Returns:
            The weighted path length of the nodes visited on the path and a
            chained list with the order of visited hosts.
        """

        nodes_visited = {initial: 0.0}
        path_prev_node = {}

        nodes_left = range(1, len(adjacency_list))

        while nodes_left:
            min_node = None
            for node in nodes_left:
                if node in nodes_visited:
                    if min_node is None:
                        min_node = node
                    elif nodes_visited[node] < nodes_visited[min_node]:
                        min_node = node

            if min_node is None:
                break

            nodes_left.remove(min_node)
            current_weight = nodes_visited[min_node]

            for neighbor in adjacency_list[min_node]:
                try:
                    weight = current_weight + neighbor.get(self.routing_field)
                except Exception as exc:
                    LOGGER.error("Error while calucalting dijkstra, Error={}".format(exc))
                    continue
                if neighbor.get('node') not in nodes_visited or weight < nodes_visited[neighbor.get('node')]:
                    nodes_visited[neighbor.get('node')] = weight#float('{0:.2f}'.format(weight))
                    path_prev_node[neighbor.get('node')] = min_node

        #LOGGER.debug("visited nodes: " + str(nodes_visited))
        #LOGGER.debug("path_prev_node: " + str(path_prev_node))
        return nodes_visited, path_prev_node

    def shortest_path(self, adjacency_list, origin, destination):
        """Calculating the path between two hosts

        This method calculates the weigth of the path between two hosts with
        the dijkstra algorithm and the global adjacency list.

        Args:
            adjacency_list (:obj:`list` of :obj:`list`): The interpretation of
                the complete network to search paths in.
            origin (:obj:`int`): The hosts to start the algorithm from.
            destination (:obj:`int`): The hosts to find the path to.

        Returns:
            The weighted path length of the nodes visited on the path and a
            list with the ordered hosts which has been visited on the path.
        """

        nodes_visited, path_prev_node = self.dijkstra(adjacency_list, origin)
        #LOGGER.info("{}\n\n\n{}".format(nodes_visited, path_prev_node))

        if origin == destination:
            return nodes_visited.get(destination), [origin]
        if len(path_prev_node) < 1 or path_prev_node.get(destination) is None:
            return None, None  # return nothing if origin or destination nodes were not available

        full_path = deque()
        node_previous = path_prev_node[destination]

        while node_previous != origin:
            full_path.appendleft(node_previous)
            node_previous = path_prev_node[node_previous]

        full_path.appendleft(origin)
        full_path.append(destination)

        return nodes_visited.get(destination), list(full_path)

    def create_subnet_of_adjacency_list(self, adjacency_list,
                                        hosts_in_subnets):
        """Creates a new adjacency list and removes all not used edges

        This method calculates the a new adjacency list from a given one by
        removing all edges between the nodes, which are not in the same given
        subnet.

        Example:
            An example for the hosts_in_subnets argument is the following list:
                [[1,2,3,4], [4,5], [5,6,7,8,9]]

        Args:
            adjacency_list (:obj:`list` of :obj:`list`): The interpretation of
                the complete network to create a new adjacency list from.
            hosts_in_subnets (:obj:`list` of :obj:`list`): The hosts separated
                into minor subnets

        Returns:
            A new adjacency list with reduces count of edges.
        """

        new_adjacency_list = [[] for x in range(len(adjacency_list))]

        for node in range(0, len(adjacency_list)):
            subnets_of_current_node = []
            for index, subnet in enumerate(hosts_in_subnets):
                if node in subnet:
                    subnets_of_current_node.append(index)

            if not subnets_of_current_node:
                continue

            for node_neighbor in adjacency_list[node]:
                add_neighbor = False
                for subnet in subnets_of_current_node:
                    if node_neighbor.get('node') in hosts_in_subnets[subnet]:
                        add_neighbor = True

                if add_neighbor is True:
                    try:
                        new_adjacency_list[node].append(node_neighbor)

                    except Exception as exc:
                        LOGGER.error("Error while removing edge {}->(iface {})->{}, Error={}".format(node, node_neighbor.get('interface'),node_neighbor.get('node'), exc))

        return new_adjacency_list

    def add_all_network_routes(self):
        """Add the network routes to the MIOT testbed nodes for static routing.

        This method adds all used routes in the network to the MIOT testbed nodes for a static routing functionality.
        """

        hostname = self.get_own_hostname()
        for i in range(1, len(self.adjacency_list)):
            length, full_path = self.shortest_path(self.adjacency_list, hostname, i)

            if length is not None and full_path is not None:
                if LOGGER.getEffectiveLevel() == logging.INFO:
                    full_path_real_node_number = [x for x in full_path]
                    LOGGER.info(str(hostname) + "->" + str(i) + "=" +
                                str(length) + ", array_path=" + str(full_path_real_node_number))
                edge = filter(lambda edge: edge['node'] == full_path[1], self.adjacency_list[hostname])[0]

                for net in range(3):
                    interface = edge.get('interface')
                    cmd = "/sbin/route add 10.0." + str(net) + "." + str(full_path[-1]) + " gw 10.0." + str(interface) + "." + str(full_path[1]) + " wlan" + str(interface)
                    out, error = subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
                    # has already been set on the testbed nodes:
                    # out, error = subprocess.Popen("/sbin/sysctl -w net.ipv4.ip_forward=1",
                    #                                shell=True,stdout=subprocess.PIPE,
                    #                                stderr=subprocess.PIPE).communicate()
                    if out:
                        LOGGER.info("CMD="+str(cmd))
                        LOGGER.info("SET ROUTE, out="+str(out))
                    if error:
                        LOGGER.error("Error: " + error)
            else:
                LOGGER.info("NO ROUTE FOUND: " + str(hostname) + "->" + str(i))

    def calculate_nodes_connection_cost_table(self):
        """Calculates the used cost table with the Dijkstra algorithm.

        This method precalculates the used connection cost table with the
        Dijkstra algorithm to reduce the reading time on the path weight
        between all hosts in the network.
        """

        for host_from in range(self.total_num_hosts):
            nodes_visited, _ = self.dijkstra(self.adjacency_list, host_from)
            for host_to in nodes_visited:
                self.nodes_connection_cost_table[host_from][host_to] = nodes_visited[host_to]
        #LOGGER.info(self.nodes_connection_cost_table)

    def calculate_nodes_connection_hop_table(self):
        """Calculates the hop cost table with the Dijkstra algorithm.

        This method precalculates the hops table with the Dijkstra algorithm
        to reduce the reading time.
        """

        for host_from in range(1, self.total_num_hosts):
            for host_to in range(1, self.total_num_hosts):
                path_cost_value, hop_list = self.shortest_path(self.adjacency_list, host_from, host_to)
                if path_cost_value is not None and hop_list is not None:
                    self.nodes_connection_hop_table[host_from][host_to] = len(hop_list) - 1 # minus 1, since the source is in the list, too

    def calculcate_central_node_from_recent_connections(
            self, recent_in_out_packets, recent_in_out_packets_total):
        """Main algorithm to calculate the best service running hosts.

        This method contains the main function of this class and calculates
        the list of the best hosts to run the service in the next migration
        cycles.

        Args:
            recent_in_out_packets (:obj:`dict` of :obj:`dict` of :obj:`int`):
                A dictionary, containing all recently with the service
                connected client hosts and the amount of the incoming and
                outgoing traffic in this time slot.
            recent_in_out_packets_total(:obj:`int`): The total number of recent
                incoming and outgoing data traffic, measured in bytes.

        Returns:
            A list of the best nodes to run the server in descending order.
        """

        #mostly_connected_nodes = sorted(
        #    recently_connected_nodes_counter.items(),
        #    key=operator.itemgetter(1), reverse=True
        #)

        new_server_ranked = {}
        for possible_new_server in range(self.total_num_hosts):
            for client_node, in_out_values in recent_in_out_packets.iteritems():
                # calculate procentual cost of the mostly_connected_nodes
                # to all possible server nodes
                cost_to_server = self.nodes_connection_cost_table[int(client_node)][possible_new_server]
                cost_from_server = self.nodes_connection_cost_table[possible_new_server][int(client_node)]

                if cost_to_server >= 0.0 and cost_from_server >= 0.0:
                    #LOGGER.debug('cost to server: ' + str(cost_to_server))
                    #LOGGER.debug('cost from server: ' + str(cost_from_server))

                    if possible_new_server not in new_server_ranked:
                        new_server_ranked[possible_new_server] = 0.0
                    new_server_ranked[possible_new_server] += cost_to_server * in_out_values['in'] + \
                                                              cost_from_server * in_out_values['out']
                else:
                    #The cost to server or from server does not exists
                    new_server_ranked[possible_new_server] = -1
                    break

        new_servers_ranked = sorted(new_server_ranked.items(), key=operator.itemgetter(1))
        best_nodes = filter(lambda a: a[1] != -1, new_servers_ranked)

        return best_nodes
