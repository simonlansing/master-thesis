import os
import ast
import json
import re
import math
import subprocess
import operator
import csv
import sys

class adjacency_list_edge_object(object):
    def __init__(self, node=None, rtt=None, interface=None):
        self.node = node
        self.rtt = rtt
        self.interface = interface

    def default(self, obj):
        return obj.__dict__

def encode_edge(obj):
    if isinstance(obj, adjacency_list_edge_object):
        return obj.__dict__
    return obj

PREFIX_PATH = "/home/simon/Desktop/"
CONNECTIVITY_LIST_PATH = './connectivity_list_2016-07-23'
NODES_COUNT = 60



con_tables_succ_paket_count = [[[0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)],
                               [[0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)],
                               [[0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)]]
con_tables_avg_rtt =          [[[0.0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)],
                               [[0.0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)],
                               [[0.0 for y in range(NODES_COUNT)] for x in range(NODES_COUNT)]]

adjacency_list = [[] for x in range(NODES_COUNT)]
count_distinct_connections = 0

def add_object_to_adjacency_list(source, destination, interface, rtt):
    found_edge = False

    for edge in adjacency_list[source]:
        if edge.node == destination:
            found_edge = True
            if rtt < edge.rtt:
                edge.interface = interface
                edge.rtt = rtt
                break
    if found_edge == False:
        adjacency_list[source].append(adjacency_list_edge_object(destination, rtt, interface))
        adjacency_list[source].sort(key=operator.attrgetter("rtt"), reverse=False)
        global count_distinct_connections
        count_distinct_connections += 1


    #adjacency_list[source].sort()

def evaluate_connectivity_list(minimum_packet_count = 1):
    file = open(CONNECTIVITY_LIST_PATH, 'r')
    content = ast.literal_eval(file.read())
    #print content

    not_available_nodes = []
    # iterate over the 3 wlan interfaces, keys = 0/1/2
    for source_num, interface_list in content.items():
        if interface_list != "":
            for interface, destination_list in interface_list.items():
                if destination_list != "":
                    for destination_ip, values in destination_list.items():
                        dest_num = re.findall(r'\b25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?\.25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?\.25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?\.25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?\b',destination_ip)[3]

                        source = ast.literal_eval(source_num)-1
                        dest = ast.literal_eval(dest_num)-1
                        interface = int(interface)

                        # remove the edges from and to the same node and remove the edge to nodes 61, 62, and 63
                        if source != dest and dest < 60 and 0 <= interface <= 2:
                            con_tables_succ_paket_count[interface][source][dest] = values[0]
                            con_tables_avg_rtt[interface][source][dest] = values[1]

                            if values[0] >= minimum_packet_count:
                                add_object_to_adjacency_list(source, dest, interface, values[1])
        else:
            not_available_nodes.append(source_num)

    print "distinct connections in adjacency list: " + str(count_distinct_connections)
    print "not available nodes:" + str(not_available_nodes)

def output_adjacency_list():
    with open(PREFIX_PATH+'adjacency_list.json', 'w') as outfile:
        json.dump(adjacency_list, outfile, default=encode_edge)

def output_connection_tables():
    for k in range(3):
        with open(PREFIX_PATH+'con_table_succ_packet_count_' + str(k) + '.csv', "wb") as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerows(con_tables_succ_paket_count[k])
        with open(PREFIX_PATH+'con_table_avg_rtt_' + str(k) + '.csv', "wb") as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerows(con_tables_avg_rtt[k])


def output_result_lists():
    #
    # creating tables to graph overviews for paket count, quantized average rtt, and a list of connection number per interface
    #
    total_connection_count_of_interface = [0,0,0]
    #result_list_connections = [[0 for y in range(NODES_COUNT)] for x in range(3)]

    result_list_paket_count = [[0.0 for y in range(11)] for x in range(3)]
    result_list_rtt =         [[0.0 for y in range(100)] for x in range(3)] #100 since no rtt > 100ms    

    for k in range(3):
        for i in range(NODES_COUNT):
            connections_count = 0
            for j in range(NODES_COUNT):
                if con_tables_succ_paket_count[k][i][j] > 0:
                    result_list_paket_count[k][con_tables_succ_paket_count[k][i][j]] += 1
                    connections_count += 1
                    total_connection_count_of_interface[k] += 1
                if con_tables_avg_rtt[k][i][j] > 0.0:
                    result_list_rtt[k][int(math.floor(con_tables_avg_rtt[k][i][j]))] += 1

            #result_list_connections[k][connections_count] += 1                          # not used at this moment

    print "total connections count per interface: " + str(total_connection_count_of_interface) #total number of connections
    
    with open(PREFIX_PATH+'result_list_paket_count.csv', 'wb') as file:
        for k in range(3):
            for i in range(len(result_list_paket_count[k])):
                result_list_paket_count[k][i] = float("{0:.2f}".format((result_list_paket_count[k][i] / total_connection_count_of_interface[k]) * 100))

        writer = csv.writer(file, delimiter=';')
        zipped = zip([0,1,2,3,4,5,6,7,8,9,10], result_list_paket_count[0], result_list_paket_count[1], result_list_paket_count[2])
        zipped.pop(0)
        writer.writerow(["Anzahl erfolgreich uebertragener Pakete","wlan0", "wlan1", "wlan2"])
        writer.writerows(zipped)

    print result_list_rtt
    with open(PREFIX_PATH+'result_list_rtt.csv', 'wb') as file:
        for k in range(3):
            for i in range(len(result_list_rtt[k])):
                result_list_rtt[k][i] = float("{0:.5f}".format((result_list_rtt[k][i] / total_connection_count_of_interface[k]) * 100))

        writer = csv.writer(file, delimiter=';')
        zipped = zip([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99],result_list_rtt[0],result_list_rtt[1],result_list_rtt[2])
        writer.writerow(["ms","wlan0", "wlan1", "wlan2"])
        writer.writerows(zipped)

def output_best_connected_nodes():
    #
    # creating a table of numbers of node to node connections
    #
    result_list_connections_combined = [0 for y in range(NODES_COUNT)]
    result_list_best_connected_nodes = {}
    for i in range(NODES_COUNT):
        connections_count_combined = 0
        for j in range(NODES_COUNT):
            if con_tables_succ_paket_count[0][i][j] is not 0 or con_tables_succ_paket_count[1][i][j] is not 0 or con_tables_succ_paket_count[2][i][j] is not 0:
                connections_count_combined += 1

        result_list_connections_combined[connections_count_combined] += 1
        result_list_best_connected_nodes[i+1] = connections_count_combined

    sorted_result_list_best_connected_nodes = sorted(result_list_best_connected_nodes.items(), key=operator.itemgetter(1), reverse=True)

    with open(PREFIX_PATH+'sorted_result_list_best_connected_nodes.csv', 'wb') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(["Knotenpunkt","Anzahl der Verbindungen"])
        writer.writerows(sorted_result_list_best_connected_nodes)



def output_graphviz_from_adjacency_list(draw_graphs = False):
    con_graphviz_file_adl = open(PREFIX_PATH+'graph_adl.gv', 'w')
    con_graphviz_file_adl.write('digraph G {\n')
    con_graphviz_file_adl.write('graph [overlap=false, splines=true];\n')
    con_graphviz_file_adl.write('node [shape=circle];\n')
    for i in range(NODES_COUNT):
        for j, edge in enumerate(adjacency_list[i]):
            con_graphviz_file_adl.write(str(i+1) + " -> " + str(edge.node+1) + "\n")

    con_graphviz_file_adl.write('}')
    con_graphviz_file_adl.close()

    if draw_graphs is True:
        process = subprocess.Popen(['/usr/bin/neato', '-Tpdf', PREFIX_PATH+'graph_adl.gv', '-o', PREFIX_PATH+'graph_neato.pdf'],
                                   stderr=subprocess.PIPE)
        #process = subprocess.Popen(['/usr/bin/dot',   '-Tpdf', './graph_adl.gv', '-o', './graph_dot.pdf'], stderr=subprocess.PIPE)
        process = subprocess.Popen(['/usr/bin/fdp', '-Tpdf', PREFIX_PATH+'graph_adl.gv', '-o', PREFIX_PATH+'graph_fdp.pdf'],
                                   stderr=subprocess.PIPE)
        process = subprocess.Popen(['/usr/bin/sfdp', '-Tpdf', PREFIX_PATH+'graph_adl.gv', '-o', PREFIX_PATH+'graph_sfdp.pdf'],
                                   stderr=subprocess.PIPE)
        process = subprocess.Popen(['/usr/bin/circo', '-Tpdf', PREFIX_PATH+'graph_adl.gv', '-o', PREFIX_PATH+'graph_circo.pdf'],
                                   stderr=subprocess.PIPE)
        process = subprocess.Popen(['/usr/bin/twopi', '-Tpdf', PREFIX_PATH+'graph_adl.gv', '-o', PREFIX_PATH+'graph_twopi.pdf'],
                                   stderr=subprocess.PIPE)



def output_graphviz_from_tables(draw_graphs = False):
    for k in range(3):
        con_graphviz_file = open('graph_'+str(k)+'.gv', 'w')
        con_graphviz_file.write('digraph G {\n')
        con_graphviz_file.write('graph [overlap=false, splines=true];\n')
        con_graphviz_file.write('node [shape=circle];\n')
        for i in range(NODES_COUNT):
            for j in range(NODES_COUNT):
                if con_tables_succ_paket_count[k][i][j] != 0:
                    con_graphviz_file.write(str(i+1)+"."+str(k) + " -> " + str(j+1)+"."+str(k) + "\n")#"[label=\"wlan" + str(k) + ": " + str(con_tables_avg_rtt[k][i][j]) + "\"]\n")

        con_graphviz_file.write('}')
        con_graphviz_file.close()

    if draw_graphs is True:
        for k in range(3):
            process = subprocess.Popen(['/usr/bin/neato', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_neato_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            process = subprocess.Popen(['/usr/bin/dot', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_dot_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            process = subprocess.Popen(['/usr/bin/fdp', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_fdp_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            process = subprocess.Popen(['/usr/bin/sfdp', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_sfdp_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            process = subprocess.Popen(['/usr/bin/circo', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_circo_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            process = subprocess.Popen(['/usr/bin/twopi', '-Tpdf', './graph_'+str(k)+'.gv', '-o', './graph_twopi_'+str(k)+'.pdf'], stderr=subprocess.PIPE)
            if process.stderr:
                print process.stderr.readlines()

def main(argv):
    draw_graphs = False
    if sys.platform == "linux2":
        draw_graphs = True
    else:
        draw_graphs = False

    evaluate_connectivity_list(9)

    output_adjacency_list()
    #output_connection_tables()
    #output_result_lists()
    #output_best_connected_nodes()
    output_graphviz_from_adjacency_list(draw_graphs)
    #output_graphviz_from_tables(draw_graphs)

if __name__ == "__main__":
  main(sys.argv[1:])