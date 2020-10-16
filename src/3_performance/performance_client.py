#!/usr/bin/python
import datetime
import imp
import json
import logging
import logging.config
import os
import select
import signal
import socket
import struct
import sys
import time
import threading
import random
sys.path.append('/mnt/master-thesis/src/1_servicemanager/server/')
import migration.network_router as routing

LOGGER = logging.getLogger(__name__)
logging.config.fileConfig("/mnt/master-thesis/src/1_servicemanager/logging.conf", disable_existing_loggers=False)
#logging.config.fileConfig("../../1_servicemanager/logging.conf", disable_existing_loggers=False)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

class configuration(object):
     def __init__(self):
         pass

class PerformanceClient(object):
    def __init__(self, arguments):
        # sequence of arguments: adjacency_list, unreachable_hosts, repetitions, start_delay, message_size, requests_p_minute
        LOGGER.info(arguments)
        self.global_connection_timeout = 60.0

        unreachable_hosts = []
        if len(arguments) > 1:
            unreachable_hosts = arguments[1].split(',')
        elif len(arguments) == 0:
            LOGGER.info("Need adjacency list for working.")
            sys.exit(0)

        config = configuration()
        setattr(config, "testing", True)
        setattr(config, "adjacency_list_file", arguments[0])
        setattr(config, "unreachable_hosts", unreachable_hosts)
        self.network_router = routing.NetworkRouter(None, config)

        self.network_router.calculate_nodes_connection_hop_table()
        self.own_hostname = self.network_router.get_own_hostname()

        #LOGGER.info(self.network_router.nodes_connection_hop_table)
        
        self.current_performance_set = {'repetitions'          : int(arguments[2]),
                                        'start_delay'          : float(arguments[3]),
                                        'message_size'         : int(arguments[4]),
                                        'requests_p_minute'    : float(arguments[5])
                                       }   
        #LOGGER.debug("performance client init")
        self.current_server = arguments[6]
        self.current_server_id = 1

        LOGGER.info("The first server runs on host %s", self.current_server)

        self.SERVER_PORT = 5000
        self.BROADCAST_PORT = 6500
        self.OPERATOR_PORT = 7000
        self.current_server_lock = threading.Lock()

        self.server_broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.server_broadcast_socket.bind(('', self.BROADCAST_PORT))
        self.server_broadcast_event = threading.Event()
        self.server_broadcast_thread = threading.Thread(target = self.recv_server_changes_from_broadcast, args=())
        self.server_broadcast_thread.daemon = True
        self.server_broadcast_thread.start()
        self.wait_for_who_is_answer_event = threading.Event()
        self.whois_broadcast_sent = threading.Event()

        # self.operator_info_event            = threading.Event()
        # self.operator_info_thread           = threading.Thread(target = self.recv_operator_info, args=())
        # self.operator_info_thread.daemon    = True
        # self.operator_info_thread.start()

        self.running_performance_event      = threading.Event()
        self.stop_running_performance_event = threading.Event()
        
        self.current_performance_test_results = {}

        self.pausing_probability = 1.0 / (2*self.current_performance_set['requests_p_minute'])
        self.message_sending_time_slot = 45.0
        self.pause_account = 0.0
        self.pause_account_lock = threading.Lock()

    def __enter__(self):
        LOGGER.debug("performance client enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug("performance client exit")
        self.server_broadcast_event.set()
        #self.operator_info_event.set()
        self.running_performance_event.clear()
        return self

    @staticmethod
    def translate_ip_addr_to_node_id(ip_addr):
        if ip_addr is not None:
            ip_address_blocks = str(ip_addr).split('.')
            return int(ip_address_blocks[3])
        else:
            return None

    @staticmethod
    def translate_node_id_to_ip_addr(node_id):
        if node_id is not None:
            return "10.0.0.{}".format(str(node_id))
        else:
            return None

    @staticmethod
    def recvall(sock, n, timeout=None):
        try:
            # Helper function to recv n bytes or return None if EOF is hit
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
            #LOGGER.error("Timeout while receiving data, Timeout={}, Error={}".format(timeout, exc))
            raise socket.timeout(exc)
        finally:
            sock.setblocking(1)
            sock.settimeout(None)

    @staticmethod
    def send_packed(sock, msg, timeout=None):
        try:
            # Prefix each message with a 4-byte length (network byte order)
            msg = struct.pack('>I', len(msg)) + msg
            sock.settimeout(timeout)
            answer = sock.sendall(msg)
            return answer
        except socket.timeout as exc:
            #LOGGER.error("Timeout while sending data, Timeout={}, Error={}".format(timeout, exc))
            raise socket.timeout(exc)
        finally:
            sock.settimeout(None)

        return None

    def recv_packed(self, sock, timeout=None):
        try:
            # Read message length and unpack it into an integer
            raw_msglen = self.recvall(sock, 4, timeout)
            if not raw_msglen:
                return None
            msglen = struct.unpack('>I', raw_msglen)[0]
            # Read the message data
            return self.recvall(sock, msglen)
        except:
            raise

    def broadcast_service_status(self, broadcast_addresses, node_id, service_name, event, counter=None):
        try:
            client_broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            publish_options = {}
            publish_options['service_name'] = str(service_name)
            publish_options['event'] = event
            publish_options['counter'] = counter

            for broadcast_addr in broadcast_addresses:
                if node_id is not None:
                    publish_options['server_ip'] = self.translate_node_id_to_ip_addr(node_id)
                else:
                    publish_options['server_ip'] = None
                client_broadcast_socket.sendto(json.dumps(publish_options),
                                               (broadcast_addr, 6500))
        except Exception as e:
            raise

    def add_time_to_pause_account(self, time):
        self.pause_account_lock.acquire()
        self.pause_account += time
        self.pause_account_lock.release()

    def get_pause_account(self):
        try:
            self.pause_account_lock.acquire()
            act_pause_account = self.pause_account
            self.pause_account = 0.0
            return act_pause_account
        except Exception as exc:
            LOGGER.error("Error getting pause account={}".format(exc))
        finally:
            self.pause_account_lock.release()

    def recv_server_changes_from_broadcast(self):
        #LOGGER.info("Start listening for broadcast messages about server changes")
        while self.server_broadcast_event.is_set() is False:
            try:
                new_message, address = self.server_broadcast_socket.recvfrom(16384)
                new_message = json.loads(new_message)
                LOGGER.info("Broadcast message from {} = {}".format(address, new_message))
                self.current_server_lock.acquire()

                #LOGGER.info("Broadcast message={}".format(new_message))
                new_server_node_id = self.translate_ip_addr_to_node_id(new_message['server_ip'])
                current_server_node_id = self.translate_ip_addr_to_node_id(self.current_server)
                if new_message['event'] == "started" and \
                   new_server_node_id != current_server_node_id and \
                   new_message['counter'] > self.current_server_id:
                    self.current_server = new_message['server_ip']

                if new_message['event'] == "stopped" and \
                   new_server_node_id == current_server_node_id and \
                   new_message['counter'] == self.current_server_id:
                    self.current_server = None

                if new_message['event'] == "who_is" and self.current_server is not None:
                    #LOGGER.info("Broadcast message from {} (who_is)={}".format(address, new_message))
                    publish_options = {}
                    publish_options['service_name'] = "service"
                    publish_options['event'] = "who_is_answer"
                    publish_options['server_ip'] = self.current_server
                    publish_options['counter'] = self.current_server_id
                    
                    try:
                        who_is_answer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        who_is_answer_socket.sendto(json.dumps(publish_options), (address[0], self.BROADCAST_PORT))
                        who_is_answer_socket.close()
                    except socket.error as exc:
                        LOGGER.error('Failed to answer who_is (socket.error): ' + str(exc), exc_info=True)

                if new_message['event'] == "who_is_answer" and self.current_server is None:
                    self.current_server = new_message['server_ip']
                    self.current_server_id = new_message['counter']
                    self.wait_for_who_is_answer_event.set()

            except Exception as exc:
                LOGGER.error("Error while receiving broadcast message,\naddress={},\nmessage=\n{}\nError={}".format(address, new_message,exc))
            finally:
                self.current_server_lock.release()
                #except Exception as exc:
                #    LOGGER.error("Error while releasing the current lock, Error={}".format(exc))

        self.server_broadcast_socket.close()

    def log_output_in_file(self, iterate_id, act_server_address, results_connection_attempts, result_time_diff, sleeping_time):

        server_node_id = self.translate_ip_addr_to_node_id(act_server_address)

        if server_node_id is not None:
            hop_count = self.network_router.nodes_connection_hop_table[self.own_hostname][server_node_id]
        else:
            hop_count = -1

        test_results = {'server_ip': act_server_address,
                        'hop_counter': hop_count,
                        'connection_attempts': results_connection_attempts,
                        'time_diff': result_time_diff,
                        'sleeping_time': sleeping_time}

        with open('./client_results_output.log', 'a') as client_output_file:
            client_output_file.write("{}:{},".format(iterate_id, test_results))

    def send_message_to_server(self, message_id, prev_sleeping_time, message):
        try:
            #LOGGER.info("send_message_to_server: start sending")
            client_socket = None
            connected = False  # Flag that indicates, if the server connection is up and running
            connection_attempts = 0
            connection_attempts_max = 10

            while connection_attempts < connection_attempts_max:
                current_connection_server = self.current_server
                if current_connection_server is None:
                    if self.whois_broadcast_sent.is_set() is False:
                        self.broadcast_service_status(["10.0.0.255"], None, "service", "who_is")
                        self.whois_broadcast_sent.set()
                    
                    max_waiting_for_whois = 3000
                    while self.wait_for_who_is_answer_event.is_set() is False:
                        time.sleep(0.01)
                        max_waiting_for_whois -= 1
                        if max_waiting_for_whois == 0:
                            LOGGER.error("Got no answer from who_is request!")
                            break

                    time.sleep(0.1) # shortly wait for the other threads to leave the while loop
                    self.whois_broadcast_sent.clear()
                    self.wait_for_who_is_answer_event.clear()

                try:                    
                    if self.current_server is not None:
                        current_connection_server = self.current_server
                    else:
                        raise RuntimeError("No answer from broadcast -> next try...")
                    #LOGGER.info("Try to connect to host {}".format(self.current_server), exc_info=True)
                    client_socket = socket.socket()
                    client_socket.settimeout(self.global_connection_timeout)
                    client_socket.connect((current_connection_server, self.SERVER_PORT))
                    client_socket.settimeout(None)
                    connected = True
                    break
                except (socket.timeout, socket.error, RuntimeError) as exc:
                    LOGGER.error("Error while connecting to host {}, Error={}".format(current_connection_server, exc))
                    if client_socket is not None:
                        client_socket.close()
                    connection_attempts += 1
                    connected = False

            if connected is True:
                time_diff = None
                try:
                    #self.current_server_lock.acquire()                    
                    #LOGGER.info("Sending random message with length {} to server {}".format(len(message), self.current_server))
                    start_time = datetime.datetime.now()
                    self.send_packed(client_socket, message, self.global_connection_timeout)
                    answer = self.recv_packed(client_socket, self.global_connection_timeout)
                    finish_time = datetime.datetime.now()
                    #LOGGER.info("Answer from server=" + str(answer))
                    time_diff = finish_time - start_time

                    self.log_output_in_file(
                        message_id, current_connection_server,
                        connection_attempts, "{}".format(time_diff),
                        prev_sleeping_time)
                    #eturn current_connection_server, connection_attempts, "{}".format(time_diff)
                except (socket.timeout, socket.error) as exc:
                    LOGGER.error("Error while sending/receiving to/from host {}, Error={}".format(current_connection_server, exc))
                    self.log_output_in_file(
                        message_id, current_connection_server,
                        connection_attempts, str(exc),
                        prev_sleeping_time)

                    #return current_connection_server, connection_attempts, str(exc)
                #finally:
                    #self.current_server_lock.release()
                    #json.dumps(time_diff, default=DateTimeEncoder))
            else:
                self.current_server = None
                #self.current_server = '10.0.0.14'

                self.log_output_in_file(
                    message_id, current_connection_server,
                    connection_attempts, "reached max attempts",
                    prev_sleeping_time)
                #return current_connection_server, connection_attempts, "reached max attempts"
        except Exception as exc:
            LOGGER.error("\nError while sending message to host {}, Error={}".format(
                self.current_server, exc), exc_info=True)

            self.log_output_in_file(
                message_id, current_connection_server,
                connection_attempts, str(exc),
                prev_sleeping_time)
            #return current_connection_server, connection_attempts, str(exc)
        finally:
            if client_socket is not None:
                client_socket.close()

    def send_recursive(self, message_id, prev_sleeping_time, max_repetitions):
        message_id += 1

        if random.random() < self.pausing_probability:
            pause = self.get_pause_account()
            LOGGER.info("I'm going to sleep for {} seconds with a probability of {} now.".format(
                pause, self.pausing_probability))
            time.sleep(pause)

        sleeping_time_median = self.message_sending_time_slot / self.current_performance_set['requests_p_minute'] 
        sleeping_time = random.uniform(0.5 * sleeping_time_median, 1.5 * sleeping_time_median)

        if message_id < max_repetitions:
            threading.Timer(sleeping_time, self.send_recursive, [message_id, sleeping_time, max_repetitions]).start()

        unused_time = (60.0 - self.message_sending_time_slot) / self.current_performance_set['requests_p_minute']
        self.add_time_to_pause_account(unused_time)


        message = os.urandom(self.current_performance_set['message_size'])
        self.send_message_to_server(message_id, prev_sleeping_time, message)

        if message_id % 50 == 0:
            LOGGER.info("Current repetition: {}\nsleeping time median={}\nsleeping time={}".format(
                message_id, sleeping_time_median, sleeping_time))

        if message_id == max_repetitions:
            time.sleep(80) # wait for other threads to finish their activity
            with open('./client_results_output.log', 'a') as client_output_file:
                client_output_file.write("}")
            sys.exit(0)

    def run(self):
        while True:
            try:
                if self.running_performance_event.is_set() is True:
                    #LOGGER.info("run: starting performance test")
                    self.stop_running_performance_event.clear()
                    with open('./client_results_output.log', 'a') as client_output_file:
                        client_output_file.write("{")
                    time.sleep(self.current_performance_set['start_delay'])

                    max_repetitions = self.current_performance_set['repetitions']
                    self.send_recursive(0, 0, max_repetitions)
                    self.running_performance_event.clear()
                    # for i in range(0, max_repetitions):
                    #     #LOGGER.info("run: performance test iteration")
                    #     # if the operator started a new session and the client is still running
                    #     if self.stop_running_performance_event.is_set() is True:
                    #         LOGGER.info("got signal to stop current performance test", exc_info=True)
                    #         break
                    #     try:
                    #         message = os.urandom(self.current_performance_set['message_size'])
                    #         act_server_address, results_connection_attempts, result_time_diff = self.send_message_to_server(message)
                    #         #TODO: add current server IP to test results

                    #         sleeping_time = random.uniform(0.5 * time_sleep_median, 1.5 * time_sleep_median)

                    #         server_node_id = networking.translate_ip_addr_to_node_id(act_server_address)
                    #         hop_count = self.network_router.nodes_connection_hop_table[self.own_hostname][server_node_id]

                    #         self.current_performance_test_results[i] = {'server_ip': self.current_server,
                    #                                                     'hop_counter': hop_count,
                    #                                                     'connection_attempts': results_connection_attempts,
                    #                                                     'time_diff': result_time_diff,
                    #                                                     'sleeping_time': sleeping_time}
                    #     except Exception as exc:
                    #         LOGGER.error("Repetition Loop EXCEPTION="+str(exc), exc_info=True)
                          
                    #     time.sleep(sleeping_time)
                    #     if i % 50 == 0:
                    #         LOGGER.info("Current repetition: {}\nsleeping time median=\nsleeping time={}".format(
                    #             i, time_sleep_median, sleeping_time))

                    # self.running_performance_event.clear()
                    # LOGGER.info("performance_set={}".format(self.current_performance_set))
                    # LOGGER.info("performance_results={}".format(self.current_performance_test_results))
                    #sys.exit(0)
            except Exception as e:
                LOGGER.error("MAIN LOOP EXCEPTION="+str(e), exc_info=True)
            finally:
                time.sleep(0.001)

    # def recv_operator_info(self):
    #     #LOGGER.info("Start listening for operator's instructions to start")
    #     operator_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     operator_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    #     try:
    #         operator_socket.bind(('', self.OPERATOR_PORT))
    #     except socket.error as e:
    #         logging.error('Failed to bind operator socket (socket.error): ' + str(e), exc_info=True)
    #     except Exception as e:
    #         logging.error('Failed to bind operator socket: ' + str(e), exc_info=True)

    #     operator_socket.listen(128)

    #     while self.operator_info_event.is_set() is False:
    #         try:
    #             conn, addr = operator_socket.accept()
    #             self.stop_running_performance_event.set()

    #             #LOGGER.info("Connecton from operator, addr="+str(addr))
    #             # read json and put into object
    #             self.current_performance_set = networking.recv_packed(conn)
    #             LOGGER.info(self.current_performance_set)
    #             self.current_performance_set = json.loads(self.current_performance_set)                
    #             #LOGGER.info("Current performance set="+str(self.current_performance_set))

    #             self.running_performance_event.set()

    #             while self.running_performance_event.is_set() is True:
    #                 #LOGGER.info("wait for ")
    #                 time.sleep(0.001)

    #             if self.current_performance_test_results:
    #                 networking.send_packed(conn, json.dumps(self.current_performance_test_results))
    #             else:
    #                 networking.send_packed(conn, "ERROR")
    #             conn.close()
    #         except socket.error as e:
    #             logging.error('Failed to accept socket (socket.error): ' + str(e), exc_info=True)
    #         except Exception as e:
    #             logging.error('Failed to accept socket: ' + str(e), exc_info=True)

    #     operator_socket.close()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    LOGGER.info(sys.argv)
    with PerformanceClient(sys.argv[1:]) as performance_client:

        #performance_client.current_performance_set = {'hosts'        : list(range(1, 61)),
        #                                              'message_size' : 1460,
        #                                              'repetitions'  : 1000,
        #                                              'start_delay'  : 0,
        #                                              'repetitions_p_minute' : 60
        #                                              }

        LOGGER.info("Current performance set="+str(performance_client.current_performance_set))
        time.sleep(-time.time() % 60)
        performance_client.running_performance_event.set()

        performance_client.run()
