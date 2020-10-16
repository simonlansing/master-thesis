import logging
import socket
import sys

logger = logging.getLogger(__name__)

def handle_port_5000(conn):
    logger.info('connection on port 5000')
    conn.sendall("You're using port 5000")
    conn.close()

def handle_port_5001(conn):
    logger.info('connection on port 5001')
    conn.sendall("You're using port 5001")
    conn.close()

def handle_port_5002(conn):
    logger.info('connection on port 5002')
    conn.sendall("You're using port 5002")
    conn.close()

#port, socket_type, callback_function on port
SERVICE_CONFIG = [[5000, socket.SOCK_STREAM, handle_port_5000],
                  [5001, socket.SOCK_STREAM, handle_port_5001],
                  [5002, socket.SOCK_STREAM, handle_port_5002]]
