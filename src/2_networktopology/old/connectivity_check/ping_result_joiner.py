#!/usr/bin/python
import logging
import socket
import sys
import time
import json
import struct

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

ping_clients = ['10.5.202.6', '10.5.202.5', '10.5.202.4', '10.5.202.20', '10.5.202.19',
                '10.5.202.13', '10.5.202.21', '10.5.202.22', '10.5.202.23', '10.5.202.24',
                '10.5.202.25', '10.5.202.26', '10.5.202.27', '10.5.202.30', '10.5.202.29',
                '10.5.202.28', '10.5.202.31', '10.5.202.32', '10.5.202.33', '10.5.202.36',
                '10.5.202.37', '10.5.202.38', '10.5.202.39', '10.5.202.40', '10.5.202.41',
                '10.5.202.42', '10.5.202.43', '10.5.202.45', '10.5.202.44', '10.5.202.46',
                '10.5.202.47', '10.5.202.48', '10.5.202.49', '10.5.202.50', '10.5.202.51',
                '10.5.202.52', '10.5.202.53', '10.5.202.54', '10.5.202.57', '10.5.202.58',
                '10.5.202.59', '10.5.202.60', '10.5.202.55', '10.5.202.56', '10.5.202.61',
                '10.5.202.62', '10.5.202.63', '10.5.202.64', '10.5.202.65', '10.5.202.66',
                '10.5.202.67', '10.5.202.68', '10.5.202.69', '10.5.202.70', '10.5.202.71',
                '10.5.202.72', '10.5.202.73', '10.5.202.74', '10.5.202.75', '10.5.202.76']
def recvall(sock, n):
    # Helper function to recv n bytes or return None if EOF is hit
    data = ''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

def send_msg(sock, msg):
    # Prefix each message with a 4-byte length (network byte order)
    msg = struct.pack('>I', len(msg)) + msg
    sock.sendall(msg)

def recv_msg(sock):
    # Read message length and unpack it into an integer
    raw_msglen = recvall(sock, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack('>I', raw_msglen)[0]
    # Read the message data
    return recvall(sock, msglen)


def get_connectivity_list(index, host, port_number):
    try:
        client_socket = socket.socket()
        client_socket.settimeout(2)
        client_socket.connect((host, port_number))
        client_socket.settimeout(None)

        answer = recv_msg(client_socket)
        client_socket.close()
        #print "get_connectivity_list: " + answer
        return answer
    except socket.error as socketerror:
        LOGGER.error(str(host) + " - socket error: " + str(socketerror))
        return None


time.sleep(60)
for index, client in enumerate(ping_clients):
    answer = {}
    LOGGER.info("connect to Node " + str(index) + " - IP:" + str(client))
    node_id = index+1
    result = get_connectivity_list(index, client, 5000)
        
    if result is not None:
        answer[str(node_id)] = json.loads(result)
    else:
        answer[str(node_id)] = ""

    LOGGER.info(str(answer))
    connectivity_file = open('../connectivity_list_'+str(node_id), 'wb')
    try:
        connectivity_file.write(str(json.dumps(answer)))
    finally:
        connectivity_file.close()

LOGGER.info("Ping result joiner completed")