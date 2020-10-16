import logging
import socket
import time
import threading
from SocketServer import TCPServer, StreamRequestHandler

class Service(object):
    def __init__(self):
        self.SERVICE_CONFIG = [[5000, socket.SOCK_STREAM, self.handle_port_5000],
                               [5001, socket.SOCK_STREAM, self.handle_port_5001],
                               [5002, socket.SOCK_STREAM, self.handle_port_5002]]

        self.service_ports_settings = [{} for x in range(len(self.SERVICE_CONFIG))]

        for i, config in enumerate(self.SERVICE_CONFIG):
            new_port_setting = {
                'client_count' : 0,
                'socket' : socket.socket(socket.AF_INET, config[1]),
                'thread' : threading.Thread(target=self.run_service_port, args=(i,))
            }
            new_port_setting['socket'].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            new_port_setting['thread'].daemon = True
            self.service_ports_settings[i] = new_port_setting
            self.service_ports_settings[i]['thread'].start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logging.debug('service handler exit')
        
        for i, config in enumerate(self.service_ports_settings):
            self.service_ports_settings[i]['socket'].close()

        return self

    def handle_port_5000(self, conn):
        logging.info('connection on port 5000')
        conn.sendall("You're using port 5000")
        conn.close()

    def handle_port_5001(self, conn):
        logging.info('connection on port 5001')
        conn.sendall("You're using port 5001")
        conn.close()

    def handle_port_5002(self, conn):
        logging.info('connection on port 5002')
        conn.sendall("You're using port 5002")
        conn.close()

    def run_service_port(self, config_id):
        logging.debug('service handler run_service_port: ' + str(config_id))

        try:
            self.service_ports_settings[config_id]['socket'].bind(('', self.SERVICE_CONFIG[config_id][0]))
        except socket.error as e:
            logging.error('Failed to bind service sockets (socket.error): ' + str(e), exc_info=True)
            #thread.interrupt_main()
        except Exception as e:
            logging.error('Failed to bind service sockets: ' + str(e), exc_info=True)
            #thread.interrupt_main()

        #backlog is set to default value. defined in /proc/sys/net/core/somaxconn
        self.service_ports_settings[config_id]['socket'].listen(128)

        while True:
            try:
                conn, addr = self.service_ports_settings[config_id]['socket'].accept()
                self.service_ports_settings[config_id]['client_count'] += 1
                #self.cb_connection_counter_changed(addr)
                logging.info('Connected with ' + addr[0] + ':' + str(addr[1]))
                self.connected_client_thread = threading.Thread(target=self.SERVICE_CONFIG[config_id][2], args=(conn,))
                self.connected_client_thread.start()
            except socket.error as e:
                logging.error('Failed to accept socket (socket.error): ' + str(e), exc_info=True)
            except Exception as e:
                logging.error('Failed to accept socket: ' + str(e), exc_info=True)

        return


if __name__ == "__main__":
    with Service() as service:
        while True:
            time.sleep(0.001)