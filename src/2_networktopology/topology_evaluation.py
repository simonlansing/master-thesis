from collections import deque
import logging
import json
import re
import subprocess
import operator
import csv
import os
import shutil
import sys
import xml.etree.ElementTree as ET

sys.path.append('../1_servicemanager/server/')
import migration.network_router as routing

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(filename)s:%(lineno)s (%(threadName)s) %(funcName)s\n%(message)s', level=logging.DEBUG)

class final_edge_object(object):
    def __init__(self, node=None, interface=None, etx=None, rtt_avg=None, throughput=None):
        self.node = int(node)
        self.etx = etx
        self.rtt_avg = rtt_avg
        self.interface = interface
        self.throughput = throughput

    def default(self, obj):
        return obj.__dict__

def encode_edge(obj):
    if isinstance(obj, final_edge_object):
        return obj.__dict__
    return obj

class configuration(object):
     def __init__(self):
         pass

class Evaluation(object):
    def __init__(self, prefix_path):
        LOGGER.debug('evaluation init')
        self.prefix_path = prefix_path
        self.connectivity_list_path = '../../Results/reachability_test/ping_flooding_33_lists_c10000_i0.0_2016-08-01/'
        self.throughput_test_path = '../../Results/throughput_test/Iperf_Test_Large-DEScript.xml'
        self.nodes_count = 60+1

        self.raw_connectivity_dict = {}
        #self.node_conenction_list = [[] for x in range(self.nodes_count)]
        self.minimized_adjacency_list = [[] for x in range(self.nodes_count)]
        self.full_adjacency_list = [[] for x in range(self.nodes_count)]
        self.throughput_adjacency_list = [[] for x in range(self.nodes_count)]
        #self.total_connection_count_of_interface = [0 for x in range(3)]


        config = configuration()
        setattr(config, "testing", True)
        setattr(config, "adjacency_list_file", "")
        setattr(config, "unreachable_hosts", UNREACHABLE_HOSTS)
        self.network_router = routing.NetworkRouter(None, config)


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug('evaluation exit')
        return self

    def translate_ip_addr_to_node_id(self, ip_addr):
        ip_address_blocks = str(ip_addr).split('.')
        return int(ip_address_blocks[2]), int(ip_address_blocks[3])

    # def add_object_to_minimized_adjacency_list(self, source, destination, interface, etx, rtt_avg):
    #     found_edge = False

    #     for edge in self.minimized_adjacency_list[source]:
    #         if edge.node == destination:
    #             found_edge = True
    #             if etx < edge.etx:
    #                 edge.interface = interface
    #                 edge.rtt_avg = rtt_avg
    #                 edge.etx = etx
    #                 break

    #     if found_edge == False:
    #         self.minimized_adjacency_list[source].append(final_edge_object(destination, interface, etx, rtt_avg))
    #         self.minimized_adjacency_list[source].sort(key=operator.attrgetter("etx"), reverse=False)

    #     adjacency_list[source].sort()

    def add_object_to_full_adjacency_list(self, source, destination, interface, etx, rtt_avg):
        self.full_adjacency_list[source].append(final_edge_object(destination, interface, etx, rtt_avg))
        self.full_adjacency_list[source].sort(key=operator.attrgetter("etx"), reverse=False)

    def parse_raw_ping_results(self, ping_results):
        '''
        "PING 10.0.1.27 (10.0.1.27) from 10.0.1.1 : 484(512) bytes of data.

        --- 10.0.1.27 ping statistics ---
        1000 packets transmitted, 0 received, +774 errors, 100% packet loss, time 340064ms
        pipe 9"



        "PING 10.0.1.49 (10.0.1.49) from 10.0.1.1 : 484(512) bytes of data.

        --- 10.0.1.49 ping statistics ---
        1000 packets transmitted, 761 received, 23% packet loss, time 199734ms
        rtt min/avg/max/mdev = 1.870/7.881/120.731/8.447 ms, pipe 3, ipg/ewma 199.934/5.967 ms"
        '''
        ping_results_lines = ping_results.split("\n")
        #LOGGER.info(ping_results_lines)
        result_dict = {}
        for line in ping_results_lines:
            try:
                #1000 packets transmitted, 0 received, +1000 errors, 100% packet loss, time 378689ms
                #or
                #1000 packets transmitted, 977 received, 2% packet loss, time 199615ms
                regex_result = re.match(r"(?P<transmitted>\d+) packets transmitted, (?P<received>\d+) received, ([\+]?(?P<duplicates>\d+) duplicates, )?([\+]?(?P<errors>\d+) errors, )?(?P<packet_loss>\d+)% packet loss, time (?P<time>\d+)ms.*", line)
                if regex_result:
                    result_dict.update(regex_result.groupdict())

                #rtt min/avg/max/mdev = 1.870/7.881/120.731/8.447 ms, pipe 3, ipg/ewma 199.934/5.967 ms
                regex_result = re.match(r"rtt min\/avg\/max\/mdev = (?P<rtt_min>(\d+).(\d+))\/(?P<rtt_avg>(\d+).(\d+))\/(?P<rtt_max>(\d+).(\d+))\/(?P<rtt_mdev>(\d+).(\d+)) ms,( pipe (?P<pipe>(\d+)),)? ipg\/ewma (?P<ipg>(\d+).(\d+))\/(?P<ewma>(\d+).(\d+)) ms", line)

                if regex_result:
                    result_dict.update(regex_result.groupdict())

                #LOGGER.info(result_dict)
            except Exception as exc:
                LOGGER.error(exc)

        return result_dict

    def import_raw_connectivity_dicts(self):
        LOGGER.debug('evaluation import_raw_connectivity_dicts')
        for source_node_id in range(1, self.nodes_count):
            try:
                with open(self.connectivity_list_path+'connectivity_list_' + str(source_node_id)) as connectivity_file:
                    content = json.loads(connectivity_file.read())
                    ping_result_dict = content[str(source_node_id)]
                    if isinstance(ping_result_dict, dict):
                        for destination_ip, ping_results in ping_result_dict.iteritems():
                            try:
                                network_interface, destination_node_id = self.translate_ip_addr_to_node_id(destination_ip)
                                ping_results = self.parse_raw_ping_results(ping_results)

                                if int(ping_results['received']) > 0 and source_node_id != int(destination_node_id):
                                    #self.total_connection_count_of_interface[int(network_interface)] += 1
                                    etx = float(ping_results['transmitted']) / int(ping_results['received'])
                                    #etx = 1 / etx_inverse
                                    #LOGGER.info(etx)
                                    #LOGGER.info(ping_results['transmitted'] + " " + ping_results['received'] + " " + str(etx))
                                    # self.add_object_to_minimized_adjacency_list(
                                    #     source_node_id,
                                    #     destination_node_id,
                                    #     network_interface,
                                    #     etx,
                                    #     float(ping_results['rtt_avg']))

                                    self.add_object_to_full_adjacency_list(
                                        source_node_id,
                                        destination_node_id,
                                        network_interface,
                                        etx,
                                        float(ping_results['rtt_avg']))

                                #self.raw_connectivity_dict.update(content)
                            except Exception as exc:
                                LOGGER.error("inner_error="+str(exc)+
                                             ", source="+str(source_node_id)+
                                             ", dest="+str(destination_node_id)+
                                             ", received="+str(ping_results))
                    else:
                        LOGGER.info("NO LIST FOUND:" +str(source_node_id))
            except Exception as exc:
                LOGGER.error("error="+str(exc))
                LOGGER.error("from "+str(source_node_id)+" to "+str(destination_node_id)+", ping_results="+str(ping_results))

        try:
            self.full_adjacency_list = json.dumps(self.full_adjacency_list, default=encode_edge)
            self.full_adjacency_list = json.loads(self.full_adjacency_list)
            
            #LOGGER.info(self.full_adjacency_list)
            #sys.exit(0)
            

            #self.minimized_adjacency_list = json.dumps(self.minimized_adjacency_list, default=encode_edge)
            #self.minimized_adjacency_list = json.loads(self.minimized_adjacency_list)

            # minimized_counter = [0 for x in range(3)]
            # for node in self.minimized_adjacency_list:
            #     for neighbor in node:
            #         minimized_counter[neighbor['interface']] += 1
            # LOGGER.info("minimized_conn_counter=%s, sum=%s", minimized_counter, str(sum(minimized_counter)))


        except Exception as exc:
            LOGGER.error("Error while reloading adjacency list="+str(exc))
            sys.exit(0)

        #LOGGER.info("total_conn_counter=" + str(self.total_connection_count_of_interface) + ", sum=" +str(sum(self.total_connection_count_of_interface)))
        #LOGGER.info(self.raw_connectivity_dict)
        #sys.exit(0)

    def add_throughput_to_adjacency_list(self, local_address, remote_address, throughput, throughput_unit):
        try:
            local_interface, local_node_id = self.translate_ip_addr_to_node_id(local_address)
            remote_interface, remote_node_id = self.translate_ip_addr_to_node_id(remote_address)

            normalized_throughput = 0

            if throughput_unit == "Mbits/sec":
                normalized_throughput = float(throughput)
            elif throughput_unit == "Kbits/sec":
                normalized_throughput = float(throughput) / 1000
            else:
                LOGGER.warn("UNKNOWN THROUGHPUT UNIT {}".format(throughput_unit))

            if normalized_throughput > 0:
                if local_node_id != remote_node_id:
                    new_throughput_edge = final_edge_object(remote_node_id, local_interface, 0, 0, normalized_throughput)
                    self.throughput_adjacency_list[local_node_id].append(new_throughput_edge)

                added = False
                for neighbor in self.full_adjacency_list[local_node_id]:
                    if neighbor['node'] == remote_node_id and neighbor['interface'] == local_interface:
                        neighbor['throughput'] = normalized_throughput
                        added = True
                        break

                #if added is False:
                    #LOGGER.warn("Could not add link from {} to {}".format(local_node_id, remote_node_id))
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)

    def remove_edges_without_throughput_from_adjacency_list(self):
        try:
            new_adjacency_list = [[] for x in range(self.nodes_count)]

            for index, source_list in enumerate(self.full_adjacency_list):
                for edge_object in source_list:
                    if 'throughput' in edge_object:
                        if edge_object['throughput'] is not None:
                            new_adjacency_list[index].append(edge_object)

            self.full_adjacency_list = new_adjacency_list
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)


    def remove_multiple_edges_from_adjacency_list(self):
        try:
            new_adjacency_list = [[] for x in range(self.nodes_count)]

            for index, nodes_neighbor_list in enumerate(self.full_adjacency_list):
                for _, iter_neighbor in enumerate(nodes_neighbor_list):
                    new_edge = iter_neighbor

                    already_added = False
                    for already_added_node in new_adjacency_list[index]:
                        if already_added_node['node'] == new_edge['node']:
                            already_added = True
                            #LOGGER.info("not added:\t%s\nadded:\t\t%s", new_edge, already_added_node)
                            break

                    if already_added is True:
                        continue

                    for _, another_neighbor in enumerate(nodes_neighbor_list):
                        if new_edge['node'] == another_neighbor['node'] and \
                           new_edge['interface'] != another_neighbor['interface']:

                            #LOGGER.info("found same edge:\t%s\n->\t\t\t%s", new_edge, another_neighbor)
                            if another_neighbor['etx'] < new_edge['etx']:
                                #LOGGER.info("changed edge:\t%s\n->\t\t%s", new_edge, another_neighbor)
                                new_edge = another_neighbor

                    new_adjacency_list[index].append(new_edge)

                #LOGGER.info("\n\n%s\n\n%s\n\n", nodes_neighbor_list, new_adjacency_list[index])


            self.full_adjacency_list = new_adjacency_list
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)


    def import_raw_iperf_throughput(self):
        tree = ET.parse(self.throughput_test_path)
        root = tree.getroot()

        action = root.findall("./results/replication[@id='17']/iteration[@id='0']/action_block[@id='3']/action[@id='0']")

        for invocation in action[0]:
            result_element = invocation.find('result')

            if result_element is not None:
                result = json.loads(result_element.text)

                self.add_throughput_to_adjacency_list(result['local'], result['remote'], result['throughput_val'], result['throughput_unit'])

    def output_etx_throughput_comparison(self):
        LOGGER.debug('evaluation output_etx_throughput_comparison')
        etx_throughput_comparison_list = [[] for x in range(3)]
        total_len = 0
        try:
            for index, source_list in enumerate(self.full_adjacency_list):
                total_len += len(source_list)
                for edge_object in source_list:
                    destination_node_edge = encode_edge(edge_object)
                    #LOGGER.info(destination_node_edge)
                    interface = destination_node_edge['interface']
                    etx_inverse_percentage = (1 / destination_node_edge['etx']) * 100
                    etx_throughput_comparison_list[int(interface)].append(
                        [etx_inverse_percentage,
                         destination_node_edge['throughput']]
                    )

            LOGGER.info("total LEN="+str(total_len))
            for interface in range(3):
                with open(self.prefix_path+'etx_throughput_comparison_iface_'+str(interface)+'.csv', 'wb') as outfile:
                    writer = csv.writer(outfile, delimiter=';')
                    writer.writerow(['etx', 'throughput'])
                    writer.writerows(etx_throughput_comparison_list[interface])
        except Exception as exc:
            LOGGER.error(exc)

        #LOGGER.info(etx_rtt_avg_comparison_list)

    def output_best_connected_nodes(self, adjacency_list, file_prefix):
        '''
        creating a table with the numbers of node to node connections
        '''
        try:
            result_list_best_connected_nodes = {}
            for i in range(1, self.nodes_count):
                result_list_best_connected_nodes[i] = len(adjacency_list[i])
                if result_list_best_connected_nodes[i] > 70:
                    LOGGER.info(json.loads(json.dumps(adjacency_list[i], default=encode_edge)))

            sorted_result_list_best_connected_nodes = sorted(result_list_best_connected_nodes.items(),
                                                             key=operator.itemgetter(1),
                                                             reverse=True)

            with open(self.prefix_path+file_prefix+'_sorted_result_list_best_connected_nodes.csv', 'wb') as outfile:
                writer = csv.writer(outfile, delimiter=';')
                writer.writerow(["Knotenpunkt","Anzahl der Verbindungen"])
                writer.writerows(sorted_result_list_best_connected_nodes)
        except Exception as exc:
            LOGGER.error(exc)

    def output_graphviz_from_adjacency_list(self, adjacency_list, file_prefix, draw_graphs=False):
        try:
            con_graphviz_file_adl = open(self.prefix_path+file_prefix+'_graph_adl.gv', 'w')
            con_graphviz_file_adl.write('digraph G {\n')
            con_graphviz_file_adl.write('graph [overlap=false, splines=true, nodesep="1", ranksep="2"];\n') #pad="0.5",
            con_graphviz_file_adl.write('node [shape=circle];\n')
            con_graphviz_file_adl.write('edge [arrowhead=vee, arrowsize=.5];\n')

            for i in range(1, self.nodes_count):
                for j, edge in enumerate(adjacency_list[i]):
                    con_graphviz_file_adl.write(str(i) + " -> " + str(edge['node']) + "\n")

            con_graphviz_file_adl.write('}')
            con_graphviz_file_adl.close()

            if draw_graphs is True:
                process = subprocess.Popen(['/usr/bin/neato', '-Tpdf', self.prefix_path+file_prefix+'_graph_adl.gv', '-o', self.prefix_path+file_prefix+'_graph_neato.pdf'], stderr=subprocess.PIPE)
                #process = subprocess.Popen(['/usr/bin/dot',   '-Tpdf', './graph_adl.gv', '-o', './graph_dot.pdf'], stderr=subprocess.PIPE)
                process = subprocess.Popen(['/usr/bin/fdp', '-Tpdf', self.prefix_path+file_prefix+'_graph_adl.gv', '-o', self.prefix_path+file_prefix+'_graph_fdp.pdf'], stderr=subprocess.PIPE)
                process = subprocess.Popen(['/usr/bin/sfdp', '-Tpdf', self.prefix_path+file_prefix+'_graph_adl.gv', '-o', self.prefix_path+file_prefix+'_graph_sfdp.pdf'], stderr=subprocess.PIPE)
                process = subprocess.Popen(['/usr/bin/circo', '-Tpdf', self.prefix_path+file_prefix+'_graph_adl.gv', '-o', self.prefix_path+file_prefix+'_graph_circo.pdf'], stderr=subprocess.PIPE)
                process = subprocess.Popen(['/usr/bin/twopi', '-Tpdf', self.prefix_path+file_prefix+'_graph_adl.gv', '-o', self.prefix_path+file_prefix+'_graph_twopi.pdf'], stderr=subprocess.PIPE)
        except Exception as exc:
            LOGGER.error(exc)

    def find_dict(self, lst, key, value):
        for i, dic in enumerate(lst):
            if dic[key] == value:
                return dic
        return -1

    def remove_unused_edges_from_adjacency_list(self, adjacency_list, subnets):
        new_adjacency_list = [[] for x in range(len(adjacency_list))]
        try:
            host_unreachable = False
            for source in range(1, len(adjacency_list)):
                if not adjacency_list[source]:
                    #LOGGER.info("No entry for source {} found".format(source))
                    continue

                for destination in range(1, len(adjacency_list)):
                    if source == destination:
                        continue

                    length, full_path = self.network_router.shortest_path(adjacency_list, source, destination)
                    #LOGGER.info(full_path)
                    if length is not None and full_path is not None:
                        #LOGGER.info("{}, {}, {}, {}, {}".format(source, destination, length, full_path, adjacency_list[source]))
                        edge = self.find_dict(adjacency_list[source], "node", full_path[1])
                        #LOGGER.info(edge)
                        if self.find_dict(new_adjacency_list[source], "node", full_path[1]) == -1:
                            new_adjacency_list[source].append(edge)
                            #LOGGER.info(str(source) + "->" + str(i) + "=" +
                            #            str(length) + ", array_path=" + str(full_path))
                    else:  # no route has been between source and i
                        if source != destination:
                            source_in_subnets = False
                            destination_in_subnets = False

                            for subnet in subnets:
                                if isinstance(subnet, list):
                                    if source in subnet:
                                        source_in_subnets = True
                                    if destination in subnet:
                                        destination_in_subnets = True
                                else:
                                    if source in subnets:
                                        source_in_subnets = True
                                    if destination in subnets:
                                        destination_in_subnets = True
                                    break

                            if source_in_subnets and destination_in_subnets:
                                host_unreachable = True
                                LOGGER.info("NO ROUTE FOUND: " + str(source) + "->" + str(destination))

                #LOGGER.info('{} {}'.format(len(adjacency_list[hostname]), len(self.final_adjacency_list[hostname])))
            if host_unreachable is False:
                LOGGER.info("All hosts can reach each other.")
                return new_adjacency_list
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)

        return None

    def output_adjacency_list(self, adjacency_list, output_name):
        with open(self.prefix_path+str(output_name)+'.json', 'w') as outfile:
            try:
                #LOGGER.info(json.dumps(self.minimized_adjacency_list, default=encode_edge))
                json.dump(adjacency_list, outfile, default=encode_edge)
            except Exception as exc:
                LOGGER.error(exc)

        # reload the minimized_adjacency_list to simulate the condition in the final program
        # (simulation scenario of file utils_network_routing.py)
        # self.final_adjacency_list = None
        # with open(self.prefix_path+'final_adjacency_list.json', 'r') as adjacency_list_file:
        #     self.final_adjacency_list = json.load(adjacency_list_file)

    def mean(self, data):
        """Return the sample arithmetic mean of data."""
        n = len(data)
        if n < 1:
            raise ValueError('mean requires at least one data point')
        return sum(data)/n # in Python 2 use sum(data)/float(n)

    def _ss(self, data):
        """Return sum of square deviations of sequence data."""
        c = self.mean(data)
        ss = sum((x-c)**2 for x in data)
        return ss

    def pstdev(self, data):
        """Calculates the population standard deviation."""
        n = len(data)
        if n < 2:
            raise ValueError('variance requires at least two data points')
        ss = self._ss(data)
        pvar = ss/n # the population variance
        return pvar**0.5

    def stdev(self, data):
        """Calculates the population standard deviation."""
        n = len(data)
        if n < 2:
            raise ValueError('variance requires at least two data points')
        ss = self._ss(data)
        var = ss/(n-1) # the population variance
        return var**0.5

    def calculate_seperate_interface_statistical_results(self, adjacency_list):
        '''
        1. mean of the RTT and its standard deviation
        2. min max mean of packet loss rate and its standard deviation
        3. min max mean of the path length and its standard deviation
        '''

        adjacency_counter = [0 for x in range(3)]
        for node in adjacency_list:
            for neighbor in node:
                adjacency_counter[neighbor['interface']] += 1
        LOGGER.info("adjacency_counter=%s, sum=%s", adjacency_counter, str(sum(adjacency_counter)))

        try:
            rtt_lists = [[] for x in range(3)]
            connectivity_lists = [[] for x in range(3)]
            throughput_lists = [[] for x in range(3)]

            global_rtt = []
            global_connectivity = []
            global_throughput = []
            global_nodes_connections = []

            connectivity_minimum = 100000
            connectivity_maximum = 0
            throughput_minimum = 100000
            throughput_maximum = 0

            global_nodes_connections_mininum = 100000
            global_nodes_connections_maximum = 0

            for index, source_list in enumerate(adjacency_list):
                if index in UNREACHABLE_HOSTS or index == 0:
                    continue

                global_nodes_connections.append(len(source_list))
                if len(source_list) < global_nodes_connections_mininum:
                    global_nodes_connections_mininum = len(source_list)
                if len(source_list) > global_nodes_connections_maximum:
                    global_nodes_connections_maximum = len(source_list)

                for edge_object in source_list:
                    destination_node_edge = encode_edge(edge_object)
                    try:
                        interface = destination_node_edge['interface']

                        if destination_node_edge['etx']:
                            connectivity_percentage = (1 / destination_node_edge['etx']) * 100

                            if connectivity_percentage < connectivity_minimum:
                                connectivity_minimum = connectivity_percentage
                            if connectivity_percentage > connectivity_maximum:
                                connectivity_maximum = connectivity_percentage

                            connectivity_lists[int(interface)].append(connectivity_percentage)
                            global_connectivity.append(connectivity_percentage)

                        rtt_avg = destination_node_edge['rtt_avg']
                        if rtt_avg is not None:
                            rtt_lists[int(interface)].append(rtt_avg)
                            global_rtt.append(rtt_avg)

                        throughput = destination_node_edge['throughput']
                        if throughput is not None:
                            if throughput < throughput_minimum:
                                throughput_minimum = throughput
                            if throughput > throughput_maximum:
                                throughput_maximum = throughput

                            throughput_lists[int(interface)].append(throughput)
                            global_throughput.append(throughput)

                    except Exception as exc:
                        LOGGER.error(exc, exc_info=True)
                        #pass

            if global_nodes_connections:
                LOGGER.info('connections mean={mean}, sd={sd}, psd={psd}\nmin={min}, max={max}'.format(
                            mean=self.mean(global_nodes_connections),
                            sd=self.stdev(global_nodes_connections),
                            psd=self.pstdev(global_nodes_connections),
                            min=global_nodes_connections_mininum,
                            max=global_nodes_connections_maximum))
            if global_connectivity:
                LOGGER.info('rtt  mean={mean}, sd={sd}, psd={psd}'.format(
                            mean=self.mean(global_rtt),
                            sd=self.stdev(global_rtt),
                            psd=self.pstdev(global_rtt))+\
                            '\nconn mean={mean}, sd={sd}, psd={psd}\nmin={min}, max={max}'.format(
                            mean=self.mean(global_connectivity),
                            sd=self.stdev(global_connectivity),
                            psd=self.pstdev(global_connectivity),
                            min=connectivity_minimum,
                            max=connectivity_maximum))
            if global_throughput:
                LOGGER.info('thro mean={mean}, sd={sd}, psd={psd}\nmin={min}, max={max}'.format(
                            mean=self.mean(global_throughput),
                            sd=self.stdev(global_throughput),
                            psd=self.pstdev(global_throughput),
                            min=throughput_minimum,
                            max=throughput_maximum))

            for x in range(3):
                if global_connectivity:
                    LOGGER.info('rtt  mean{interface}={mean}, sd{interface}={sd}, psd{interface}={psd}'.format(
                        interface=x,
                        mean=self.mean(rtt_lists[x]),
                        sd=self.stdev(rtt_lists[x]),
                        psd=self.pstdev(rtt_lists[x]))+\
                        '\nconn mean{interface}={mean}, sd{interface}={sd}, psd{interface}={psd}'.format(
                            interface=x,
                            mean=self.mean(connectivity_lists[x]),
                            sd=self.stdev(connectivity_lists[x]),
                            psd=self.pstdev(connectivity_lists[x])))
                if global_throughput:
                    LOGGER.info('thro mean{interface}={mean}, sd{interface}={sd}, psd{interface}={psd}'.format(
                        interface=x,
                        mean=self.mean(throughput_lists[x]),
                        sd=self.stdev(throughput_lists[x]),
                        psd=self.pstdev(throughput_lists[x])))
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)

    # def calculate_statistical_results(self, adjacency_list):
    #     '''
    #     1. mean of the RTT and its standard deviation
    #     2. min max mean of packet loss rate and its standard deviation
    #     3. min max mean of the path length and its standard deviation
    #     '''
    #     try:
    #         rtt_list = []
    #         connectivity_list = []
    #         for index, source_list in enumerate(adjacency_list):

    #             for edge_object in source_list:
    #                     destination_node_edge = encode_edge(edge_object)
    #                     try:
    #                         connectivity_percentage = (1 / destination_node_edge['etx']) * 100
    #                         connectivity_list.append(connectivity_percentage)

    #                         rtt_avg = destination_node_edge['rtt_avg']
    #                         rtt_list.append(rtt_avg)

    #                     except Exception as exc:
    #                         LOGGER.error(exc)

    #         LOGGER.info('rtt mean={mean}, sd={sd}, psd={psd}'.format(mean=self.mean(rtt_list), sd=self.stdev(rtt_list), psd=self.pstdev(rtt_list)))

    #         LOGGER.info('conn mean={mean}, sd={sd}, psd={psd}'.format(mean=self.mean(connectivity_list), sd=self.stdev(connectivity_list), psd=self.pstdev(connectivity_list)))
    #     except Exception as exc:
    #         LOGGER.error(exc)

    def output_subnetted_adjacency_lists_and_graphs(self, subnets, file_prefix, draw_graphs, add_internet_connections=False):

        subnetted_adjacency_list = self.network_router.create_subnet_of_adjacency_list(
            self.full_adjacency_list,
            subnets)

        if add_internet_connections:
            for node_id in subnets[2]:
                for node2_id in subnets[2]:
                    if node_id == node2_id:
                        continue

                    new_edge_list = []
                    for edge in subnetted_adjacency_list[node_id]:
                        if edge["node"] == node2_id:
                            continue
                        else:
                            new_edge_list.append(edge)

                    subnetted_adjacency_list[node_id] = new_edge_list

                    if (node_id in subnets[0] and node2_id in subnets[1]) or \
                       (node_id in subnets[1] and node2_id in subnets[0]):
                        LOGGER.info("%s and %s", node_id, node2_id)
                        continue
                    else:
                        LOGGER.info("OK: %s and %s", node_id, node2_id)
                        new_edge = {"node": node2_id, "rtt_avg": 1.0, "etx": 1.0, "interface": 0, "throughput": 50.0}
                        subnetted_adjacency_list[node_id].append(new_edge)

            #self.output_adjacency_list(self.full_adjacency_list, file_prefix+"full_adjacency_list")
        
        #if file_prefix != "full":
        #    subnetted_adjacency_list = self.remove_unused_edges_from_adjacency_list(
        #    subnetted_adjacency_list,
        #    subnets)

        self.output_best_connected_nodes(subnetted_adjacency_list, file_prefix)
        self.output_adjacency_list(subnetted_adjacency_list, file_prefix+"_adjacency_list")
        self.output_graphviz_from_adjacency_list(subnetted_adjacency_list, file_prefix, draw_graphs)

if __name__ == "__main__":
    draw_graphs = False
    prefix_path = "/home/simon/Desktop/output/"
    UNREACHABLE_HOSTS = [6,9,15,18,19,22,23,34,37,43,48,52,53,54,55,56,57,58,60]

    if sys.platform == "linux2":
        if os.path.exists(prefix_path):
            shutil.rmtree(prefix_path)
        os.mkdir(prefix_path)
        draw_graphs = True
    else:
        draw_graphs = False
        prefix_path = './output/'

    with Evaluation(prefix_path) as evaluation:
        try:
            evaluation.import_raw_connectivity_dicts()
            LOGGER.info("\n\n\nResults of network with ETX only (w/ Multiedges):")
            evaluation.calculate_seperate_interface_statistical_results(evaluation.full_adjacency_list)
            
            #LOGGER.info("\n\n\nResults of network with ETX only (w/o Multiedges):")
            #evaluation.remove_multiple_edges_from_adjacency_list()
            #evaluation.calculate_seperate_interface_statistical_results(evaluation.full_adjacency_list)
            #sys.exit(0)
            
            LOGGER.info("\n\n\nResults of network with Throughput only (w/ Multiedges):")
            evaluation.import_raw_iperf_throughput()
            evaluation.throughput_adjacency_list = json.dumps(evaluation.throughput_adjacency_list, default=encode_edge)
            evaluation.throughput_adjacency_list = json.loads(evaluation.throughput_adjacency_list)
            evaluation.calculate_seperate_interface_statistical_results(evaluation.throughput_adjacency_list)

            LOGGER.info("\n\n\nResults of shrinked network with ETX and Throughput (w/ Multiedges):")
            evaluation.remove_edges_without_throughput_from_adjacency_list()
            evaluation.calculate_seperate_interface_statistical_results(evaluation.full_adjacency_list)
            evaluation.output_etx_throughput_comparison()

            LOGGER.info("\n\n\nResults of shrinked network with ETX and Throughput (w/o Multiedges):")
            evaluation.remove_multiple_edges_from_adjacency_list()
            evaluation.calculate_seperate_interface_statistical_results(evaluation.full_adjacency_list)

            #evaluation.output_etx_throughput_comparison()
            #evaluation.calculate_statistical_results(evaluation.minimized_adjacency_list)
            #evaluation.calculate_seperate_interface_statistical_results(evaluation.minimized_adjacency_list)

            evaluation.output_subnetted_adjacency_lists_and_graphs(
                [[x for x in range(len(evaluation.full_adjacency_list)) if x not in UNREACHABLE_HOSTS]],
                'full',
                draw_graphs)
            #############################################################################################
            ##################################### THROUGHPUT BASED ######################################
            #############################################################################################
            # evaluation.output_subnetted_adjacency_lists_and_graphs(
            #     [[42, 13, 31,  7,  4, 29, 41, 51, 14, 36, 40, 59, 16, 26, 46, 5, 21, 38, 20, 35]],
            #     'seperated1',
            #     draw_graphs)
            # evaluation.output_subnetted_adjacency_lists_and_graphs(
            #     [[11, 45, 30, 50, 12, 28, 33, 44,  1, 17, 39, 49, 10, 24, 32, 2,  8, 27, 47, 25]],
            #     'seperated2',
            #     draw_graphs)

            # evaluation.output_subnetted_adjacency_lists_and_graphs(
            #     [[42, 13, 31,  7,  4, 29, 41, 51, 14, 36, 40, 59, 16, 26, 46, 5, 21, 38, 20, 35],
            #      [11, 45, 30, 50, 12, 28, 33, 44,  1, 17, 39, 49, 10, 24, 32, 2,  8, 27, 47, 25],
            #      [40,3,50]],
            #     'seperated',
            #     draw_graphs,
            #     True)


            #############################################################################################
            ######################################### ETX BASED #########################################
            #############################################################################################
            evaluation.output_subnetted_adjacency_lists_and_graphs(
                [[47, 59, 46, 51, 50, 13, 14, 49, 42, 41, 45, 17, 12, 40, 44, 38, 39, 33, 32, 36]],
                'seperated1',
                draw_graphs)
            evaluation.output_subnetted_adjacency_lists_and_graphs(
                [[35, 26, 28, 24, 29, 11, 16, 31, 30, 21, 27, 25, 5, 10, 4, 2, 1, 7, 8, 20]],
                'seperated2',
                draw_graphs)
            evaluation.output_subnetted_adjacency_lists_and_graphs(
                [[47, 59, 46, 51, 50, 13, 14, 49, 42, 41, 45, 17, 12, 40, 44, 38, 39, 33, 32, 36],
                 [35, 26, 28, 24, 29, 11, 16, 31, 30, 21, 27, 25, 5, 10, 4, 2, 1, 7, 8, 20],
                 [14, 3, 16]],
                'seperated',
                draw_graphs,
                True)

            # subnets_dict = {"small_test_net": [[40, 22, 1, 14, 23, 8, 7, 10, 2, 20], [40, 12], [12, 44, 50, 49, 17, 37, 26, 41, 47]],
            #                 "all_in_two_seperate_net": [
            #                     [2, 1, 4, 7, 10, 5, 25, 21, 16, 27, 30, 3, 31, 29, 11, 26, 24, 20, 8, 23, 28, 32, 35, 36],
            #                     [33, 36],
            #                     [33, 39, 38, 34, 12, 44, 40, 17, 54, 60, 53, 41, 51, 47, 18, 46, 59, 50, 14, 13, 45, 42, 49, 37]
            #                 ]
            #                }

            # for prefix_name, subnets in subnets_dict.iteritems():
            #     evaluation.output_subnetted_adjacency_lists_and_graphs(subnets, prefix_name, draw_graphs)


        except Exception as exc:
            LOGGER.error(exc)

        #evaluation.output_connection_tables()
        #evaluation.output_result_lists()
        #evaluation.output_graphviz_from_tables(draw_graphs)
