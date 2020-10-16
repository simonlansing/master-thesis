#!/usr/bin/python
import logging
import signal
import socket
import subprocess
import sys
import time
import utils_network_functions as networking

SERVER_PORT_NUMBER = 5000

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

def test_utils_network_routing(host):
    try:
        LOGGER.info("send_message_to_server: start sending")
        client_socket = socket.socket()
        client_socket.settimeout(10.0)
        client_socket.connect((host, SERVER_PORT_NUMBER))
        client_socket.settimeout(None)

        LOGGER.info("Sending test message to server " + str(host) + ':' + str(SERVER_PORT_NUMBER))

        networking.send_packed(client_socket, 'Routing Test')
        answer = networking.recv_packed(client_socket)
        LOGGER.info("Answer from server " + str(host) + ": " + str(answer))
    except Exception as e:
        LOGGER.error("Error while sending message, Error="+str(e))
    finally:
        client_socket.close()


signal.signal(signal.SIGINT, signal_handler)

cmd = "hostname | egrep -o [1-9]+[0-9]*"
hostname_call = subprocess.Popen(cmd, shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
hostname = int(hostname_call.communicate()[0].strip())

LOGGER.info("Starting Client on host "+ str(hostname)+". Now waiting.")
time.sleep(10 + 20 * hostname)
for host_addr_block in range(1, 61):
    for net_addr_block in range(0, 3):
        ip_addr = "10.0" + str(net_addr_block) + "." + str(host_addr_block)
        test_utils_network_routing(ip_addr)
        time.sleep(0.2)
