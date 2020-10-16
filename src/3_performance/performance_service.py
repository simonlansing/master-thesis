import imp
import logging
import logging.config
import signal
import socket
import struct
import sys
import threading
import time

LOGGER = logging.getLogger(__name__)
logging.config.fileConfig("/mnt/master-thesis/src/1_servicemanager/logging.conf", disable_existing_loggers=False)

def signal_handler(signal, frame):
    LOGGER.info("got stop signal from service handler")
    sys.exit(0)

class PerformanceService(object):

    def __init__(self):
        LOGGER.debug("performance service init")
        self.global_connection_timeout = 60.0

        self.stop_service_event = threading.Event()

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        self.client_threads = []
        tcp_service_thread = threading.Thread(target=self.run_tcp_service_port,
                                              args=(self.tcp_socket,
                                                    5000, self.handle_tcp_packets,))
        tcp_service_thread.daemon = True
        tcp_service_thread.start()


        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        udp_service_thread = threading.Thread(target=self.run_udp_service_port,
                                              args=(self.udp_socket,
                                                    5001, self.handle_udp_packets,))
        udp_service_thread.daemon = True
        udp_service_thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug('performance service exit')
        self.stop_service_event.set()        
        self.tcp_socket.close()

        for thread in self.client_threads:
            LOGGER.info("wait for thread")
            thread.join()

        LOGGER.debug('performance service stops now')
        return self

    def recvall(self, sock, n, timeout=None):
        try:
            # Helper function to recv n bytes or return None if EOF is hit
            data = ''
            while len(data) < n:
                sock.settimeout(timeout)
                packet = sock.recv(n - len(data))
                if not packet:
                    return None
                data += packet
            return data
        except socket.timeout as exc:
            #LOGGER.error("Timeout while receiving data, Timeout={}, Error={}".format(timeout, exc))
            raise socket.timeout(exc)
        finally:
            sock.settimeout(None)

    def send_packed(self, sock, msg, timeout=None):
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

    def handle_udp_packets(self, udp_socket, msg, addr):
        LOGGER.info('UDP connection on port 5001')
        udp_socket.sendto("OK", addr)

    def run_udp_service_port(self, udp_socket, port, handle_function):
        #LOGGER.debug('service handler run_service_port: ' + str(port))

        try:
            udp_socket.bind(('', port))
            #backlog is set to default value. defined in /proc/sys/net/core/somaxconn
        except socket.error as e:
            LOGGER.error('Failed to bind service sockets (socket.error): ' + str(e))
        except Exception as e:
            LOGGER.error('Failed to bind service sockets: ' + str(e))

        while self.stop_service_event.is_set() is False:
            try:
                msg, addr = udp_socket.recvfrom(1024)
                LOGGER.info('Message from ' + addr + '=' + str(msg))
                connected_client_thread = threading.Thread(target=handle_function, args=(udp_socket, msg, addr,))
                connected_client_thread.start()

                self.client_threads.append(connected_client_thread)
            except socket.error as e:
                LOGGER.error('Failed to get message (socket.error): ' + str(e))
            except Exception as e:
                LOGGER.error('Failed to get message: ' + str(e))
        return


    def handle_tcp_packets(self, conn):
        #LOGGER.info('TCP connection on port 5000')
        try:
            message = self.recv_packed(conn, self.global_connection_timeout)

            self.send_packed(conn, "OK", self.global_connection_timeout)
        except socket.timeout as exc:
            LOGGER.error("Timeout while handle tcp data, Error={}".format(exc))
        finally:
            conn.close()

    def run_tcp_service_port(self, tcp_socket, port, handle_function):
        #LOGGER.debug('service handler run_service_port: ' + str(port))

        try:
            tcp_socket.bind(('', port))
            #backlog is set to default value. defined in /proc/sys/net/core/somaxconn
            tcp_socket.listen(128)
        except socket.error as e:
            LOGGER.error('Failed to bind service sockets (socket.error): ' + str(e))
            sys.exit(1)
        except Exception as e:
            LOGGER.error('Failed to bind service sockets: ' + str(e))
            sys.exit(1)

        while self.stop_service_event.is_set() is False:
            try:
                conn, addr = tcp_socket.accept()
                #LOGGER.info('Connected with ' + addr[0] + ':' + str(addr[1]))
                connected_client_thread = threading.Thread(target=handle_function, args=(conn,))
                connected_client_thread.start()
                
                self.client_threads.append(connected_client_thread)
            except socket.error as e:
                LOGGER.error('Failed to accept socket (socket.error): %s %s', str(e), addr)
            except Exception as e:
                LOGGER.error('Failed to accept socket: ' + str(e))
        return

    def run(self):
        while True:
            time.sleep(0.001)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    with PerformanceService() as performance_service:
        performance_service.run()
        