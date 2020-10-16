import ast
import json
import subprocess
import sys
sys.path.append('../../../1_servicemanager/server/utils')

from network_routing import NetworkRouting


def start_testing(argv, packet_lost):
    routing = NetworkRouting('../adjacency_list_' + str(packet_lost) + '.json', argv)
    not_found_routes = 0

    for i in range(0, 60):
        hostname = int(i)
        for j in range(0, len(routing.adjacency_list)):
            length, full_path = routing.shortest_path(hostname, j)

            if length is not None and full_path is not None:
                full_path_real_node_number = [x+1 for x in full_path]
                #print str(hostname+1) + '->'+str(j+1) + '=' + str(length) + ', array_path=' + str(full_path_real_node_number)
                edge = filter(lambda edge: edge['node'] == full_path[1], routing.adjacency_list[hostname])[0]
                
                for net in range(0, 3):
                    interface = edge.get("interface")
                    cmd = "/sbin/route add 10.0." + str(net) + "." + str(full_path[-1]+1) + " gw 10.0." + str(interface) + "." + str(full_path[1]+1) + " wlan" + str(interface)
                    #print cmd
            else:
                #print "NO ROUTE FOUND: " + str(hostname+1) + "->" + str(j+1)
                not_found_routes += 1

    print str(packet_lost) + ": not found routes count: " + str(not_found_routes)


def main(argv):
    for i in range(1,11):
        start_testing(sys.argv[1:], i)

if __name__ == "__main__":
    main(sys.argv[1:])