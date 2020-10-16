"""A bundle of global network functions for all classes.

The network functions give all classes the ability to send their data in the
same manner and builds a basis in the network communication of the service
manager.
"""

import logging
import json
import select
import struct
import socket
import os

LOGGER = logging.getLogger(__name__)

def recvall(sock, n, timeout=None):
    """Helper function to the recv_packet function.

    This functions receives n bytes on a socket or return None if EOF is hit.
    The socket is nonblocking, but will throw an exception, if the timeout is
    set.

    Args:
        sock (:obj:`socket`): The socket to receive data.
        n (:obj:`int`): The number of bytes to receive on the socket.
        timeout (:obj:`int`, optional): The given timeout for the complete
            receving process.

    Returns:
        The n bytes of received data.

    """

    try:
        data = ''
        sock.setblocking(0)
        while len(data) < n:
            read_ready = None
            if timeout is not None:
                read_ready, _, _ = select.select([sock], [], [], timeout)
            else:
                read_ready, _, _ = select.select([sock], [], [])

            if read_ready:
                packet = sock.recv(n - len(data))

                if not packet:
                    return None

                data += packet
            else:
                raise socket.timeout("timed out")
        return data
    except socket.timeout as exc:
        LOGGER.error("Timeout while receiving data, Timeout=%s, Error=%s",
                     timeout, exc)
        raise socket.timeout(exc)
    except Exception as exc:
        raise
    finally:
        sock.setblocking(1)
        sock.settimeout(None)

def send_packed(sock, msg, timeout=None):
    """Helper function to the send data with a socket.

    This functions sends a Message over the given socket or throws a timeout
    exception, if the host is not reachable.

    Args:
        sock (:obj:`socket`): The socket to send data.
        msg (:obj:`str`): The Message to send.
        timeout (:obj:`int`, optional): The given timeout for the complete
            sending process.

    Returns:
        The answer of the connected host.
    """

    try:
        # Prefix each message with a 4-byte length (network byte order)
        msg = struct.pack('>I', len(msg)) + msg
        sock.settimeout(timeout)
        answer = sock.sendall(msg)
        return answer
    except socket.timeout as exc:
        #LOGGER.error("Timeout while sending data, Timeout=%s, Error=%s",
        #             timeout, exc)
        raise socket.timeout(exc)
    except Exception as exc:
        raise
    finally:
        sock.settimeout(None)

    return None

def recv_packed(sock, timeout=None):
    """Helper function to the receive data with a socket.

    This functions receives Messages over the given socket or throws a timeout
    exception, if the host is not reachable.

    Args:
        sock (:obj:`socket`): The socket to receive data.
        timeout (:obj:`int`, optional): The given timeout for the complete
            sending process.

    Returns:
        The message of the connected host.
    """

    try:
        # Read message length and unpack it into an integer
        raw_msglen = recvall(sock, 4, timeout)
        if not raw_msglen:
            return None
        msglen = struct.unpack('>I', raw_msglen)[0]
        # Read the message data
        return recvall(sock, msglen)
    except:
        raise

def translate_ip_addr_to_node_id(ip_addr):
    """Helper function to translate an IP address to the node ID.

    This functions is a helper method to translate between IP addresses and
    the node IDs from the MIOT-testbed. It helps in the work with network
    packets and connecting to specific hosts.

    Args:
        ip_addr (:obj:`str`): The string of the IP address.

    Returns:
        The node ID of the MIOT-testbed node or None on wrong input.
    """

    if ip_addr is not None:
        ip_address_blocks = str(ip_addr).split('.')
        return int(ip_address_blocks[3])
    else:
        return None

def translate_node_id_to_ip_addr(node_id):
    """Helper function to translate an node ID to the IP address.

    This functions is a helper method to translate between node IDs and the IP
    addresses from the MIOT-testbed. It helps in the work with network packets
    and connecting to specific hosts.

    Args:
        node_id (:obj:`int`): The value of the node ID.

    Returns:
        The IP address of the MIOT-testbed node or None on wrong input.
    """

    if node_id is not None:
        return "10.0.0.{}".format(str(node_id))
    else:
        return None

def broadcast_service_status(broadcast_addresses, node_id,
                             service_name, event, counter=None):
    """Helper function to broadcast a specific event from the service.

    This functions is a helper method to send a specific event to all
    listening clients in the network, e.g. the new service instance or the
    stopping service instance.

    Args:
        broadcast_addresses (:obj:`str`): The address to send the broadcast to.
        node_id (:obj:`int`): The node ID of this service manager instance.
        service_name (:obj:`int`): The name of the service.
        event (:obj:`int`): The event of this broadcast.
        counter (:obj:`int`, optional): The network wide unique service
            instance ID.
    """

    try:
        client_broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        publish_options = {}
        publish_options['service_name'] = str(service_name)
        publish_options['event'] = event
        publish_options['counter'] = counter

        for broadcast_addr in broadcast_addresses:
            if node_id is not None:
                publish_options['server_ip'] = translate_node_id_to_ip_addr(
                    node_id)
            else:
                publish_options['server_ip'] = None
            client_broadcast_socket.sendto(json.dumps(publish_options),
                                           (broadcast_addr, 6500))
    except Exception as exc:
        raise

def multicast_service_status(multicast_address, node_id,
                             service_name, event, counter=None):
    """Helper function to multicast a specific event from the service.

    This functions is a helper method to send a specific event to all
    listening clients in the multicast group, e.g. the new service instance or
    the stopping service instance.

    Args:
        multicast_address (:obj:`str`): The address to send the multicast to.
        node_id (:obj:`int`): The node ID of this service manager instance.
        service_name (:obj:`int`): The name of the service.
        event (:obj:`int`): The event of this broadcast.
        counter (:obj:`int`, optional): The network wide unique service
            instance ID.
    """

    try:
        client_multicast_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP)
        client_multicast_socket.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            2)

        publish_options = {}
        publish_options['service_name'] = str(service_name)
        publish_options['event'] = event
        publish_options['counter'] = counter

        if node_id is not None:
            publish_options['server_ip'] = translate_node_id_to_ip_addr(node_id)
        else:
            publish_options['server_ip'] = None
        client_multicast_socket.sendto(json.dumps(publish_options),
                                       (multicast_address, 6500))
    except Exception as exc:
        raise

def get_all_interfaces():
    """Helper function to extract all network interfaces from the linux system.

    This functions is a helper method to extract all network interfaces of the
    underlying linux system.

    Returns:
        A list of all network interfaces.
    """

    all_interfaces = os.listdir('/sys/class/net/')
    return all_interfaces

def get_wireless_interfaces():
    """Helper function to extract all wireless interfaces from the system.

    This functions is a helper method to extract all wireless network
    interfaces of the underlying linux system.

    Returns:
        A list of all wireless network interfaces.
    """
    interfaces = get_all_interfaces()

    wireless_interfaces = []
    for interface in interfaces:
        if interface.startswith('wlan') is True:
            wireless_interfaces.append(interface)

    return wireless_interfaces
