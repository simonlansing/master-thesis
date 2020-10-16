#!/usr/bin/python

import datetime
import json
import logging
import os
import signal
import subprocess
import struct
import socket
import sys
import time
import threading

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

class PerformanceClient(object):
    def __init__(self):
        LOGGER.debug("iperf client init")
        self.current_server = "10.0.0.1"
        self.OPERATOR_PORT = 7000

        self.operator_info_event = threading.Event()
        self.operator_info_thread = threading.Thread(target = self.recv_operator_info, args=())
        self.operator_info_thread.daemon = True
        self.operator_info_thread.start()

        self.process = None
        self.out = None
        self.error = None


        cmd = "hostname | egrep -o [1-9]+[0-9]*"
        hostname_call = subprocess.Popen(cmd, shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.own_hostname = int(hostname_call.communicate()[0].strip())

        unreachable_hosts = [6, 9, 15, 19, 43, 48, 52, 55, 57, 58]
        with open('../full_adjacency_list.json', 'r') as adjacency_list_file:
            self.adjacency_list = json.load(adjacency_list_file)
            #LOGGER.info(self.adjacency_list)
            for unreachable_host in unreachable_hosts:
                unreachable_host = int(unreachable_host)
                self.adjacency_list[unreachable_host] = []

                for node in range(0, len(self.adjacency_list)):
                    for node_neighbor in self.adjacency_list[node]:
                        if node_neighbor.get('node') is unreachable_host:
                            self.adjacency_list[node].remove(node_neighbor)

        LOGGER.info("Own neighbors with multiple links = "+str(len(self.adjacency_list[self.own_hostname])))

    def __enter__(self):
        LOGGER.debug("iperf client enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("iperf client exit")
        self.operator_info_event.set()
        return self

    def send_msg(self, sock, msg):
        # Prefix each message with a 4-byte length (network byte order)
        msg = struct.pack('>I', len(msg)) + msg
        sock.sendall(msg)

    def recv_operator_info(self):
        LOGGER.info("Start listening for operator's instructions to start")
        operator_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        operator_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            operator_socket.bind(('', self.OPERATOR_PORT))
        except socket.error as e:
            logging.error('Failed to bind operator socket (socket.error): ' + str(e), exc_info=True)
        except Exception as e:
            logging.error('Failed to bind operator socket: ' + str(e), exc_info=True)

        operator_socket.listen(128)

        while self.operator_info_event.is_set() is False:
            try:
                conn, addr = operator_socket.accept()

                LOGGER.info("Connecton from operator, addr="+str(addr))
                # read json and put into object

                # read the adjacency list here for known ETX values
                # connect here to all servers on all three network interfaces
                for destination_node in self.adjacency_list[self.own_hostname]:
                    destination_ip_address = "10.0.{}.{}".format(destination_node['interface'], destination_node['node'])

                    try:
                        for i in range(100):
                            self.process = None
                            self.out = None
                            self.error = None
                            def target():
                                self.process = subprocess.Popen(['/usr/bin/iperf3', '-c', destination_ip_address, '-t', '30'],
                                                              stdout=subprocess.PIPE,
                                                              stderr=subprocess.PIPE)
                                self.out, self.error = self.process.communicate()
                            thread = threading.Thread(target=target)
                            thread.start()

                            thread.join(40)
                            if thread.is_alive():
                                print 'Terminating process'
                                self.process.terminate()
                                thread.join()
                                self.out = None
                                self.error = "Thread timed out...tried to send 4GB without reason"

                            if self.out:
                                with open('iperf_client_results{}_{}.log'.format(
                                        self.own_hostname,destination_ip_address), 'wb') as success_file:
                                    success_file.write(self.out)
                                    LOGGER.info("{} try to connect to host {}...success".format(i, destination_ip_address))
                                    break
                            elif self.error:
                                with open('iperf_client_err{}_{}.log'.format(self.own_hostname, destination_ip_address), 'wb') as error_file:
                                    LOGGER.info("{} try to connect to host {}...error".format(i, destination_ip_address))
                                    error_file.write(self.error)
                                    self.out = None
                                    self.error = None
                                    continue
      
                    except Exception as e:
                        LOGGER.error('Failed to start iperf service: ' + str(e), exc_info=True)

                self.send_msg(conn, "OK")
            except socket.error as e:
                logging.error('Failed to accept socket (socket.error): ' + str(e), exc_info=True)
            except Exception as e:
                logging.error('Failed to accept socket: ' + str(e), exc_info=True)
            finally:
                conn.close()

        operator_socket.close()

    def run(self):
        while True:
            time.sleep(0.001)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    with PerformanceClient() as performance_client:
        performance_client.run()
