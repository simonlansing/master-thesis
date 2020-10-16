"""This module contains the NetworkPacket as a value object class.

All network packets can be extracted into this value object class to easily
read informations from the network packet.
"""

import binascii
import logging
import socket
import struct

LOGGER = logging.getLogger(__name__)

def enum(**enums):
    """function to give python 2.7 the ability for enum types."""
    return type('Enum', (), enums)

class NetworkPacket(object):
    """A value object class for analyzed network packets.

    The NetworkPacket class is a value object class, which unpack all bytes of a network packet into single readable attributes.

    Attributes:
        protocol_type (:obj:`Enum` of :obj:`int`): The protocol type of the
            analyzed network packet.

        total_size (:obj:`int`): The total size of the whole network packet.
        source_mac (:obj:`str`): The MAC address of the source.
        dest_mac (:obj:`str`): The MAC address of the destination.
        ether_type (:obj:`int`): The ether type, which determines the IP
            version of the inner IP packet.

        ip_version (:obj:`int`): The version of the IP packet.
        ihl (:obj:`int`): The length of the IP header.
        ttl (:obj:`int`): The Time to live value.
        protocol (:obj:`int`): The protocol type of the inner packet. In this
            case it could be for TCP, UDP or ICMP
        source_ip_address (:obj:`str`): The IP address of the source.
        dest_ip_address (:obj:`str`): The IP address of the destination.

        source_port (:obj:`int`): The port of the source in the TCP/UDP packet.
        dest_port (:obj:`int`):  The port of the destination in the TCP/UDP
            packet.
        seq_number (:obj:`int`): The sequence number of the TCP packet.
        ack_number (:obj:`int`): The acknowledge number of the TCP packet.
        doff_reserved (:obj:`int`): data offset and reserved fields.
        data (:obj:`str`): The containing data of the packet.
        data_size (:obj:`int`): the size of the TCP data packet.
        icmp_type (:obj:`int`): The type of the ICMP packet.
        code (:obj:`int`): The code of the ICMP content.
        checksum (:obj:`int`): The checksum of the UDP packet.
        udp_length (:obj:`int`): The length of the UDP content.
    """

    protocol_type = enum(IPv4=0x0800,
                         IPv6=0x86DD,
                         TCP=6,
                         UDP=17,
                         ICMP=1)

    def __init__(self, packet_string):
        """The initialization function of the class NetworkPacket.

        The function gets the given network string and unpacks it into all
        possible attributes.

        Args:
            packet_string (:obj:`str`): The complete packet in a full string
                line.
        """

        try:
            self.packet = binascii.unhexlify(packet_string)

            self.total_size = len(packet_string)

            self.source_mac = None
            self.dest_mac = None
            self.ether_type = None

            self.ip_version = None
            self.ihl = None
            self.ttl = None
            self.protocol = None
            self.source_ip_address = None
            self.dest_ip_address = None

            self.source_port = None
            self.dest_port = None
            self.seq_number = None
            self.ack_number = None
            self.doff_reserved = None
            self.data = None
            self.data_size = None

            self.icmp_type = None
            self.code = None
            self.checksum = None

            self.udp_length = None

            self.extract_ethernet_header()

            if self.ether_type == NetworkPacket.protocol_type.IPv4:
                self.extract_ipv4_header()

                if self.protocol == NetworkPacket.protocol_type.TCP:
                    self.extract_tcp_header()
                elif self.protocol == NetworkPacket.protocol_type.ICMP:
                    self.extract_icmp_header()
                elif self.protocol == NetworkPacket.protocol_type.UDP:
                    self.extract_udp_header()
            #else:
                #LOGGER.debug("Non-IPv4 packet found, ether_type=" + str(self.ether_type))
        except TypeError as e:
            LOGGER.error("Error while extracting packet (TypeError): " + str(e))
        except Exception as e:
            LOGGER.error("Error while extracting packet: " + str(e))
            
    def __str__(self):
        """returns the NetworkPacket in a human readable format."""

        return "\nTOTAL SIZE=" + str(self.total_size) + \
               "\nETHERNET\n  source mac=" + str(self.source_mac) + \
               "\n  dest mac=" + str(self.dest_mac) + \
               "\n  ether_type=" + str(self.ether_type) + \
               "\n\nIPv4\n  protocol (TCP 6/UDP 17/ICMP 1)=" + str(self.protocol) + \
               "\n  source ip address=" + str(self.source_ip_address) + \
               "\n  dest ip address=" + str(self.dest_ip_address) + \
               "\n\nTCP/UDP/ICMP\n  source_port=" + str(self.source_port) + \
               "\n  dest_port=" + str(self.dest_port) + \
               "\n  data_size=" + str(self.data_size) + \
               "\n  length (UDP)=" + str(self.udp_length)

    def eth_addr(self, a):
        """method to order the MAC address.

        Converts a string of 6 characters of ethernet address into a dash
        separated hex string
        """

        b = "%.2x:%.2x:%.2x:%.2x:%.2x:%.2x" % (ord(a[0]), ord(a[1]), ord(a[2]), ord(a[3]), ord(a[4]), ord(a[5]))
        return b

    def extract_ethernet_header(self):
        """method the extract the ethernet header"""

        self.ETH_LENGTH = 14
        eth_header = self.packet[:self.ETH_LENGTH]
        eth = struct.unpack('!6s6sH', eth_header)
        self.dest_mac = self.eth_addr(eth[0])
        self.source_mac = self.eth_addr(eth[1])
        self.ether_type = int(hex(eth[2]), 16)

    def extract_ipv4_header(self):
        """method to extract the IPv4 header of the given packet"""

        ip_header = self.packet[self.ETH_LENGTH:20+self.ETH_LENGTH]
        iph = struct.unpack('!BBHHHBBH4s4s', ip_header)
        self.iph = iph

        version_ihl = iph[0]
        self.ip_version = version_ihl >> 4
        self.ihl = version_ihl & 0xF

        self.IPH_LENGTH = self.ihl * 4
        self.ttl = iph[5]
        self.protocol = iph[6]
        self.source_ip_address = socket.inet_ntoa(iph[8])
        self.dest_ip_address = socket.inet_ntoa(iph[9])

    def extract_tcp_header(self):
        """method to extract the TCP header of the given packet"""

        t = self.IPH_LENGTH + self.ETH_LENGTH
        tcp_header = self.packet[t:t+20]
        tcph = struct.unpack('!HHLLBBHHH', tcp_header)

        self.source_port = tcph[0]
        self.dest_port = tcph[1]
        self.seq_number = tcph[2]
        self.ack_number = tcph[3]
        self.doff_reserved = tcph[4]
        tcph_length = self.doff_reserved >> 4

        h_size = self.ETH_LENGTH + self.IPH_LENGTH + tcph_length * 4
        #data_size          = len(self.packet) - h_size
        self.data_size = self.iph[2] - self.IPH_LENGTH - tcph_length * 4
        #get data from the packet
        self.data = self.packet[h_size:]

    def extract_icmp_header(self):
        """method to extract the ICMP header of the given packet"""

        u = self.IPH_LENGTH + self.ETH_LENGTH
        icmph_length = 4
        icmp_header = self.packet[u:u+4]
        icmph = struct.unpack('!BBH', icmp_header)

        self.icmp_type = icmph[0]
        self.code = icmph[1]
        self.checksum = icmph[2]

        h_size = self.ETH_LENGTH + self.IPH_LENGTH + icmph_length
        self.data_size = len(self.packet) - h_size   
        #get data from the packet
        self.data = self.packet[h_size:]

    def extract_udp_header(self):
        """method to extract the UDP header of the given packet"""

        u = self.IPH_LENGTH + self.ETH_LENGTH
        udph_length = 8
        udp_header = self.packet[u:u+8]
        udph = struct.unpack('!HHHH', udp_header)

        self.source_port = udph[0]
        self.dest_port = udph[1]
        self.udp_length = udph[2]
        self.checksum = udph[3]

        h_size = self.ETH_LENGTH + self.IPH_LENGTH + udph_length
        self.data_size = len(self.packet) - h_size
        #get data from the packet
        self.data = self.packet[h_size:]
