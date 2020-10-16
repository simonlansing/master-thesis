import logging
import signal
import socket
import sys
import threading
import time
import utils_network_functions as networking
from utils_network_routing import NetworkRouting

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

class RoutingTestingServer(object):

    def __init__(self):
        LOGGER.debug("routing testing server init")

        self.network_router = NetworkRouting(False, '../adjacency_list.json', 60, [])
        self.network_router.add_all_network_routes()

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        tcp_service_thread = threading.Thread(target=self.run_tcp_service_port,
                                              args=(self.tcp_socket,
                                                    5000, self.handle_tcp_packets,))
        tcp_service_thread.daemon = True
        tcp_service_thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug('routing testing server exit')
        self.tcp_socket.close()

        return self

    def handle_tcp_packets(self, conn):
        LOGGER.info('TCP connection on port 5000')
        message = networking.recv_packed(conn)
        
        networking.send_packed(conn, "OK")
        conn.close()

    def run_tcp_service_port(self, tcp_socket, port, handle_function):
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

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    with RoutingTestingServer() as routing_testing_server:
        routing_testing_server.run()
        