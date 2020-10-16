 #!/usr/bin/python

import json
import logging
import shutil
import sys
import time
import os
from functools import partial
from mininet.topo import Topo
from mininet.net import Mininet
import mininet.node
from mininet.node import CPULimitedHost, RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, debug, info, error
from mininet.cli import CLI
#from pox import POX

mininet_network = None
adjacency_list_file_path = '/mnt/master-thesis/results/reachability_test/output_etx/seperated_adjacency_list.json'
unreachable_hosts = '6,9,15,18,19,22,23,34,37,43,48,52,53,54,55,56,57,58,60'

class MeshNetworkTopo(Topo):
    def build(self, adjacency_list):
        hosts = []
        switches = []

        #operator_host = self.addHost('operator', ip = '10.0.0.100')

        for index, neighbors in enumerate(adjacency_list):
            if neighbors == []:
                continue

            # Each host gets 50%/n of system CPU
            host = self.addHost('h{}'.format(index), ip='10.0.0.{}/24'.format(index))#, cpu=.5/41)
            switch = self.addSwitch('s{}'.format(index), cls=OVSSwitch)
            #, failMode='standalone', stp=1))
            hosts.append(host)
            switches.append(switch)
            
            self.addLink(host, switch)
            #self.addLink(operator_host, switch)

        for index, neighbors in enumerate(adjacency_list):
            if neighbors == []:
                continue

            for neighbor in neighbors:
                node_number = neighbor.get('node')
                bandwidth = neighbor.get('throughput')
                #delay = '1ms'
                loss_rate = float("{0:.0f}".format((1.0 - 1.0 / neighbor.get('etx')) * 100))

                if bandwidth == 50:
                    loss_rate=0
                #, max_queue_size=1000000,
                linkopts = dict(bw=bandwidth, loss=loss_rate, use_htb=True)

                self.addLink('s{}'.format(index), 's{}'.format(node_number), **linkopts)

def initNetwork(client_hosts):
    global mininet_network, adjacency_list_file_path
    
    #Create network and run simple performance test
    adjacency_list = None

    try:
        with open(adjacency_list_file_path, 'r') as adjacency_list_file:
            adjacency_list = json.load(adjacency_list_file)
    except IOError as exc:
        error("No adjacency file found on location {}, Error({})={}".format(
            adjacency_list_file_path,
            exc.errno, exc.strerror))
    except:
        error("Unexpected error={}".format(sys.exc_info()[0]))


    topology = MeshNetworkTopo(adjacency_list)
    switch = partial(OVSSwitch, protocols='OpenFlow13')
    mininet_network = Mininet(topo=topology, link=TCLink, switch=switch, build=False)
    #, host=CPULimitedHost, , autoStaticArp=True)

    mininet_network.addController('c0', controller=RemoteController, ip="127.0.0.1", port=6653)

    for index, switch in enumerate(mininet_network.switches):
        #switch = mininet_network.get(switch_name)
        switch.cmd('ifconfig {} 10.0.1.{}'.format(switch.name, index+1))
        switch.cmd('ovs-vsctl set bridge {} protocols=OpenFlow13 stp-enable=true'.format(switch.name))

    mininet_network.build()

    #controller=POX
    #cleanup=True,
    #host=CPULimitedHost
    mininet_network.start()

    time.sleep(120)


    #CLI(mininet_network)


    # for host in mininet_network.hosts:
    #     info(host.cmd('ping -c10 10.0.0.16'))

    # for host in client_hosts:
    #     for other_host in client_hosts:
    #         host1, host2 = mininet_network.get(host, other_host)
    #         info(host1.cmd('ping -c100 -i0.5 %s' % host2.IP()))

    mininet_network.pingAll()




    #print "starting the pings for host discovery"
    #for index, host_from in enumerate(mininet_network.hosts): 
    #    for index, host_to in enumerate(mininet_network.hosts):        
    #        print host_from.cmd("ping {} -c 100 &".format(host_to.IP()))

    #time.sleep(60)


    #print "Dumping host connections"
    #dumpNodeConnections(net.hosts)
    #print "Testing network connectivity"
    #net.pingAll()
    #print "Testing bandwidth between h1 and h4"
    #h1, h4 = net.get('h1', 'h4')
    #net.iperf((h1, h4))
    
def startOperations(repetitions, start_delay, message_size, repetitions_p_minute, migration_time, server_hosts, first_server, client_hosts):
    global mininet_network, adjacency_list_file_path, unreachable_hosts
    migration_threshold = 2.0
#    if server_hosts and  first_server not in server_hosts.split(','):
#        first_server = "1"


    project_path = '/mnt/master-thesis/src/'
    output_path_prefix = project_path + '4_mininet/'
    test_path = output_path_prefix + 'test_time{}_rep{}_sd{}_ms{}_rpm{}_mt{}_mtr{}/'.format(
        time.strftime("%Y-%m-%d-%H-%M-%S"), repetitions, 
        start_delay, message_size, repetitions_p_minute,
        migration_time, migration_threshold)

    #adjacency_list, unreachable_hosts, repetitions, start_delay, message_size, requests_p_minute
    client_execfile_path = project_path + '3_performance/performance_client.py {} {} {} {} {} {} {}'.format(
        adjacency_list_file_path, unreachable_hosts,
        repetitions, start_delay, message_size, repetitions_p_minute, "10.0.0."+first_server)
    #operator_execfile_path = project_path + '3_performance_test/1_testing/performance_operator.py'
    service_execfile_path = project_path + '3_performance/performance_service.py'
    server_execfile_path = project_path + '1_servicemanager/server/main.py -a {} -t -u {} -c {} -g {}'.format(
        adjacency_list_file_path, unreachable_hosts,
        migration_time, migration_threshold)

    if server_hosts:
        server_execfile_path = '{} -v {}'.format(server_execfile_path, server_hosts)


    # test_number = 1 
    # while os.path.exists(test_path):
    #     test_number += 1
    #     test_path = output_path_prefix + "test_{}_out/".format(test_number)

    os.mkdir(test_path)
    #os.mkdir(test_path + "operator/")

    client_exection_paths = {}
    for index, host in enumerate(mininet_network.hosts):
        #if host.name == "operator":
        #    continue

        os.mkdir(test_path + '{}/'.format(host.name))

        client_exection_path = "cd " + test_path + "{}/".format(host.name) + \
                               " && python " + client_execfile_path + \
                               " >> ./performance_client.log 2>&1 &"

        client_exection_paths[host.name] = client_exection_path

        if host.name == "h{}".format(first_server):
            info("h{} is executing the first server now".format(first_server))
            shutil.copy(service_execfile_path, test_path + "{}/service.py".format(host.name))
            server_exection_path = "cd " + test_path + "{}/".format(host.name) + \
                                   " && python " + server_execfile_path + \
                                   " -r" + \
                                   " >> ./performance_server.log 2>&1 &"

        else:
            server_exection_path = "cd " + test_path + "{}/".format(host.name) + \
                                   " && python " + server_execfile_path + \
                                   " >> ./performance_server.log 2>&1 &"

        host.cmd(server_exection_path)

    for index, host in enumerate(mininet_network.hosts):
        #     continue
        # if host.name == "operator":
        
        if host.name in client_hosts:
            host.cmd(client_exection_paths[host.name])


    # operator_exection_path = "cd " + test_path + "operator/" + \
    #                          " && python " + operator_execfile_path + \
    #                          " >> ./operator.log 2>&1 &"

    # mininet_network.get('operator').cmd(operator_exection_path)    

def stopNetwork():
    global mininet_network

    mininet_network.stop()

if __name__ == '__main__':
    ## SERVER HOSTS
    #IOT_A_THROUGHPUT       = "11,45,30,50,12,28,33,44,1,17,39,49,10,24,32,2,8,27,47,25"
    #IOT_B_THROUGHPUT       = "42,13,31,7,4,29,41,51,14,36,40,59,16,26,46,5,21,38,20,35"
    #IOT_A_THROUGHPUT_HOSTS = ["h24", "h32", "h28", "h11", "h47"]
    #IOT_B_THROUGHPUT_HOSTS = ["h5", "h16", "h38", "h42", "h59"]

    INTERNET    = "3"

    IOT_A_ETX              = "35,26,28,24,29,11,16,31,30,21,27,25,5,10,4,2,1,7,8,20"
    IOT_A_ETX_WO_CLIENTS   = "26,28,24,16,31,30,27,25,5,10,4,2,1,7,8"
    IOT_B_ETX              = "47,59,46,51,50,13,14,49,42,41,45,17,12,40,44,38,39,33,32,36"
    IOT_A_ETX_HOSTS        = [ 'h20', 'h35', 'h29', 'h11', 'h21'] # h8>h20
    IOT_B_ETX_HOSTS        = ['h59', 'h47', 'h49', 'h44', 'h39'] #h32 > h39
    IOT_A_ETX_FIRST_SERVER = '16'
    IOT_B_ETX_FIRST_SERVER = '14'

    ###################################################
    ################## CONFIGURATION ##################
    ###################################################
    repetitions             = 2000
    start_delay             = 0.0
    message_size            = 14600
    repetitions_p_minute    = 10
    migration_time          = 30
    server_hosts            = IOT_A_ETX
    client_hosts            = IOT_A_ETX_HOSTS# + IOT_B_ETX_HOSTS

    if server_hosts == IOT_A_ETX or server_hosts == IOT_A_ETX_WO_CLIENTS:
        first_server = IOT_A_ETX_FIRST_SERVER
    else:
        first_server = IOT_B_ETX_FIRST_SERVER
    ###################################################
    ###################################################
    ###################################################

    ###### FIXED SERVER ######
    # first_server = '3'
    # server_hosts = '3'

    ###### FULL NETWORK ######
    # repetitions             = 10000
    # start_delay             = 0.0
    # message_size            = 1460
    # repetitions_p_minute    = 240
    # migration_time          = 30
    # server_hosts            = None
    # client_hosts            = ['h1', 'h5', 'h16', 'h11', 'h24', 'h28', 'h32', 'h38', 'h42', 'h59', 'h47']
    # first_server            = '1'

    setLogLevel('info')
    initNetwork(client_hosts)
    time.sleep(10)
    startOperations(repetitions, start_delay, message_size,
                    repetitions_p_minute, migration_time,
                    server_hosts, first_server, client_hosts)
    CLI(mininet_network)
    stopNetwork()


    #floodlight config in
    # ~/floodlight/src/main/resources/floodlightdefault.properties
    # von net.floodlightcontroller.topology.TopologyManager.pathMetric=latency
    # zu link_speed

    # von net.floodlightcontroller.core.internal.OFSwitchManager.supportedOpenFlowVersions=1.0 1.1 1.2 1.3
    # zu 1.3