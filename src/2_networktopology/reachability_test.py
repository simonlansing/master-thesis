#!/usr/bin/python
import logging
import signal
import socket
import sys
#import fcntl
import struct
#import array
import subprocess
import time
import threading
import json
#import netifaces

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

# def get_ip_address(ifname):
#     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     return socket.inet_ntoa(fcntl.ioctl(
#         s.fileno(),
#         0x8915,  # SIOCGIFADDR
#         struct.pack('256s', ifname[:15])
#     )[20:24])

class NetworkTopologyService(object):
    def __init__(self):
        self.ping_results = {}
        self.broadcast_addresses = ['10.0.0.255', '10.0.1.255', '10.0.2.255']

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.startup_wlan_interfaces()

        tcp_service_thread = threading.Thread(target=self.run_ping_service,
                                              args=(self.tcp_socket,
                                                    5000, self.handle_ping_service_request,))
        tcp_service_thread.daemon = True
        tcp_service_thread.start()

        self.ping_flooding_results = {}
        self.ping_flooding_results_lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug('network topology service exit')
        return self

    def recvall(self, sock, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = ''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data

    def send_msg(self, sock, msg):
        # Prefix each message with a 4-byte length (network byte order)
        msg = struct.pack('>I', len(msg)) + msg
        sock.sendall(msg)

    def recv_msg(self, sock):
        # Read message length and unpack it into an integer
        raw_msglen = self.recvall(sock, 4)
        if not raw_msglen:
            return None
        msglen = struct.unpack('>I', raw_msglen)[0]
        # Read the message data
        return self.recvall(sock, msglen)

    def startup_wlan_interfaces(self):
        LOGGER.debug("startup_wlan_interfaces")
        for interface in range(3):
            cmd = "/sbin/ifconfig wlan" + str(interface) + " up"
            out, error = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()
            if out:
                LOGGER.info("startup_wlan_interfaces, out=" + str(out))
            if error:
                LOGGER.error("Error while starting network interfaces: i=" + str(interface) + ", Error=" + str(error))

    # def get_neighbors_of_node(self):
    #     LOGGER.info('get_neighbors_of_node')
    #     neighbor_nodes = []


    #     #send ping broadcast only on wlan interfaces
    #     for index, broadcast_addr in enumerate(self.broadcast_addresses):
    #         host = broadcast_addr

    #         # call ping n+1 times, since the host itself answers directly at time n and instantly stops ping
    #         ping = subprocess.Popen(["ping", "-b", "-c", "11", host],
    #                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #         out, error = ping.communicate()
    #         LOGGER.info("Ping output="+str(out))

    #         if out:                
    #             interface_ping_result = {}
                
    #             re_line = re.compile("^(\d+) bytes from (\d+).(\d+).(\d+).(\d+): icmp_seq=(\d+) ttl=(\d+) time=(\d+).(\d+) ms", re.MULTILINE)
    #             for match in re_line.finditer(out):
    #                 host_ip_address = match.group(2) + '.' + match.group(3) + '.' + match.group(4) + '.' + match.group(5)

    #                 if host_ip_address not in neighbor_nodes:
    #                     neighbor_nodes.append(host_ip_address)

    #     return neighbor_nodes

    def append_ping_flooding_results(self, process_output, host_ip_address):
        self.ping_flooding_results_lock.acquire()
        LOGGER.info("append_ping_flooding_results "+str(host_ip_address))

        self.ping_flooding_results[host_ip_address] = process_output

        self.ping_flooding_results_lock.release()

    def do_ping_flooding_on_host(self, host_ip_address):
        # ping -q -B -c 10000 -s 65507 -l 3 -p 0f1e2d3c4b5a6978 -i 0.2 -f ip.ip.ip.ip
        # ping -q -B -c 10000 -i 0.2 -f ip.ip.ip.ip
        try:
            LOGGER.info("Start flooding host "+str(host_ip_address))
            ping_str = "sudo ping -q -B -c 10000 -s 484 -l 3 -p 0f1e2d3c4b5a6978 -f " + host_ip_address
            ping = subprocess.Popen(ping_str.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, error = ping.communicate()

            if out:
                self.append_ping_flooding_results(out, host_ip_address)
                LOGGER.info(out)
            if error:
                LOGGER.error(error)
        except subprocess.CalledProcessError as e:
            LOGGER.error("CalledProcessError, " +str(e))
        except OSError as e:
            LOGGER.error("OSError, " +str(e))
        except Exception as e:
            LOGGER.error("Exception, " +str(e))

    def handle_ping_service_request(self, conn):
        try:
            for network in range(3):
                network_ping_threads = []

                for host in range(1, 61):
                    host_ip_address = "10.0."+str(network)+"."+str(host)
                    host_thread = threading.Thread(target=self.do_ping_flooding_on_host,
                                                   args=(host_ip_address,))
                    network_ping_threads.append(host_thread)

                for thread in network_ping_threads:
                    thread.start()

                LOGGER.info("wait for threads now")
                for thread in network_ping_threads:
                    thread.join()
        except Exception as exc:
            LOGGER.error("Exception while handle ping service request, Error="+str(exc))
        finally:
            self.send_msg(conn, json.dumps(self.ping_flooding_results))
            conn.close()

    # def do_pings_on_broadcast(self, conn):
    #     LOGGER.info('do_pings_on_broadcast')

    #     #send ping broadcast only on wlan interfaces
    #     for index, broadcast_addr in enumerate(self.broadcast_addresses):
    #         host = broadcast_addr

    #         # call ping n+1 times, since the host itself answers directly at time n and instantly stops ping
    #         ping = subprocess.Popen(["ping", "-b", "-c", "11", host],
    #                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #         out, error = ping.communicate()
    #         LOGGER.info("Ping output="+str(out))

    #         if out:                
    #             interface_ping_result = {}
                
    #             re_line = re.compile("^(\d+) bytes from (\d+).(\d+).(\d+).(\d+): icmp_seq=(\d+) ttl=(\d+) time=(\d+).(\d+) ms", re.MULTILINE)
    #             for match in re_line.finditer(out):
    #                 host_ip_address = match.group(2) + '.' + match.group(3) + '.' + match.group(4) + '.' + match.group(5)
    #                 value = float(match.group(8) + '.' + match.group(9))

    #                 print host_ip_address + ": " + str(value)
    #                 sys.stdout.flush()
    #                 if host_ip_address in interface_ping_result:
    #                     if match.group(6) not in interface_ping_result[host_ip_address]:
    #                         interface_ping_result[host_ip_address][match.group(6)] = value

    #                 else:
    #                     interface_ping_result[host_ip_address] = {}
    #                     interface_ping_result[host_ip_address][match.group(6)] = value

    #                 print interface_ping_result
    #                 sys.stdout.flush()
            
    #             for host_ip_address, answers_per_host in interface_ping_result.iteritems():
    #                 avg_value = 0
    #                 successful_pings = 0
    #                 for sequence_id, ping_rtt in answers_per_host.iteritems():
    #                     successful_pings += 1
    #                     avg_value += ping_rtt
                        
    #                 avg_value = avg_value / successful_pings

    #                 interface_ping_result[host_ip_address] = [successful_pings, round(avg_value, 2)]

    #                 LOGGER.info(interface_ping_result)

    #             #for i in netifaces.ifaddresses(i)[netifaces.AF_INET][0]['addr']
    #             self.ping_results[index] = interface_ping_result

    #     LOGGER.info(self.ping_results)

    #     self.send_msg(conn, json.dumps(self.ping_results))
    #     conn.close()

    def run_ping_service(self, tcp_socket, port, handle_function):
        LOGGER.debug('service handler run_service_port: ' + str(port))

        try:
            tcp_socket.bind(('', port))
            #backlog is set to default value. defined in /proc/sys/net/core/somaxconn
            tcp_socket.listen(128)
        except socket.error as e:
            LOGGER.error('Failed to bind service sockets (socket.error): ' + str(e), exc_info=True)
        except Exception as e:
            LOGGER.error('Failed to bind service sockets: ' + str(e), exc_info=True)

        while True:
            try:
                conn, addr = tcp_socket.accept()
                LOGGER.info('Connected with ' + addr[0] + ':' + str(addr[1]))
                connected_client_thread = threading.Thread(target=handle_function, args=(conn,))
                connected_client_thread.start()
            except socket.error as e:
                LOGGER.error('Failed to accept socket (socket.error): ' + str(e), exc_info=True)
            except Exception as e:
                LOGGER.error('Failed to accept socket: ' + str(e), exc_info=True)
        return

    def run(self):
        while True:
            time.sleep(0.001)
    #port, socket_type, callback_function on port

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    with NetworkTopologyService() as network_topology_service:
        network_topology_service.run()