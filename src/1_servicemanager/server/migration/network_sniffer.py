"""The module contains the functions to sniff the ports of the service.

The NetworkSniffer of this module sniffs on all incoming and outgoing packets
on the ports of the service to collect enough data for a migration decision.
"""

import logging
import subprocess
import threading
import re
from utils import Networking
from utils import NetworkPacket

LOGGER = logging.getLogger(__name__)

class NetworkSniffer(object):
    """This class sniffs all incoming and outgoing network packets.

    This NetworkSniffer class sniffs all data on the host and sends them to
    the service manager core. The sniffer uses the program tcpdump for this
    process.

    Attributes:
        ports (:obj:`list` of :obj:`int`): The ports of the service to sniff
            on.
        stopped_event (:obj:`threading.Event`): Event to stop the sniffing.
        network_sniffer_thread (:obj:`threading.Thread`): The thread of the
            network sniffing process.
        tcpdump_hex_row_regex (:obj:`re.regex`): The regex to process sniffed
            data from the tcpdump output.
    """

    def __init__(self, service_manager, configuration):
        """The initialization function of the class NetworkSniffer.

        The function initializes the NetworkSniffer instance and extracts all needed information to sniff the incoming and outgoing network packets.

        Args:
            service_manager (:obj:`ServiceManager`): The instance of the
                service manager core to extract the informations.
            configuration (:obj:`optparse.Option`): The configuration of the
                command line interface.
        """

        LOGGER.debug("network sniffer init")

        self.testing_flag = configuration.testing
        self.own_node_id = service_manager.get_own_hostname_callback()
        self.ports = []
        self.stopped_event = threading.Event()
        self.cb_new_packet = service_manager.new_packet_callback
        self.cb_new_packet_for_service = service_manager.new_service_packet_callback

        self.network_sniffer_thread = threading.Thread(target=self.run, args=())
        self.network_sniffer_thread.daemon = True

        self.tcpdump_hex_row_regex = re.compile(r".*0x(?P<row_id>[0-9a-f]{4}):[ ]*(?P<content>([ ]([0-9a-f]{2,4})){1,8})")
        self.tcpdump_hex_content_regex = "[ ]([0-9a-f]{2,4})"


        LOGGER.info("ALL INTERFACES: " + str(Networking.get_all_interfaces()))
        if self.testing_flag is False:
            self.sniffing_interfaces = Networking.get_wireless_interfaces()
        else:
            self.sniffing_interfaces = filter(lambda element: 'eth' in element, Networking.get_all_interfaces())
            
        LOGGER.info("SNIFFING INTERFACES: " + str(self.sniffing_interfaces))

    def __enter__(self):
        LOGGER.debug("network sniffer enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("network sniffer exit")
        self.cancel_sniffing()
        return self

    def run(self):
        """Main method of the NetworkSniffer to process the sniffed data.

            This method sniffs all data incoming and outgoing over the ports
            of the service and process them on the fly. All gathered
            information will be forwarded to the service manager core.
        """

        LOGGER.info("network sniffer started")
        command = "/usr/sbin/tcpdump -ntlqxx"
        
        if self.testing_flag is False:
            command += " -Q inout" # add -v to testbed command?

        for interface in self.sniffing_interfaces:
            command += " -i " + interface

        while self.stopped_event.is_set() is False:
            act_packet = ""
            last_row_id = -1
            tcp_dump = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, bufsize=1)
            for line in iter(tcp_dump.stdout.readline, b''):
                line_match = self.tcpdump_hex_row_regex.match(line)

                if line_match is not None:
                    row_id = int(line_match.group('row_id'), 16)
                    
                    hex_line = line_match.group('content').replace(' ', '')
                    #LOGGER.info(hex_line)
                    #LOGGER.info(len(hex_line))

                    if row_id > last_row_id:
                        act_packet += hex_line

                    if len(hex_line) < 32 or (row_id < last_row_id and act_packet != ""):
                        net_packet = NetworkPacket(act_packet)
                        act_packet = ""
                        if net_packet.ether_type == NetworkPacket.protocol_type.IPv4:
                            if int(net_packet.dest_ip_address.split('.')[3]) == self.own_node_id \
                            and net_packet.dest_port in self.ports:
                                self.cb_new_packet_for_service(net_packet, True)
                            if int(net_packet.source_ip_address.split('.')[3]) == self.own_node_id \
                            and net_packet.source_port in self.ports:
                                self.cb_new_packet_for_service(net_packet, False)

                        self.cb_new_packet(net_packet.total_size)
                    last_row_id = -1 if act_packet == "" else row_id
                #else:
                    #LOGGER.info(line)

                if self.stopped_event.is_set() is True:
                    break

            tcp_dump.stdout.close()
            tcp_dump.wait()

        self.stopped_event.clear()

    def cancel_sniffing(self):
        """Method to cancel the sniffing process"""

        LOGGER.debug("cancel sniffing")
        self.stopped_event.set()

    def set_sniffing_ports(self, ports):
        """Method to set the ports to sniff on"""

        LOGGER.info("SNIFFING PORTS:" + str(ports))
        self.ports = ports
        if self.network_sniffer_thread.is_alive() is False:
            self.network_sniffer_thread.start()
