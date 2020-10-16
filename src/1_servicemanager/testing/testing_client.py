#!/usr/bin/python

import socket
import sys
import time

#while True:
#    s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#    s.bind(('',6500))
#    m=s.recvfrom(1024)
#    print m[0]

def test_service_ports(host, port_number):
    client_socket = socket.socket()
    client_socket.connect((host, port_number))

    print '{} {}'.format("testing service on port ", port_number)

    client_socket.send('blabla')
    answer = client_socket.recv(1024)
    print(answer)

    client_socket.close()


while True:
    test_service_ports('192.168.0.140', 5000)
    time.sleep(3.5)
    test_service_ports('192.168.0.140', 5001)
    time.sleep(3.5)
    test_service_ports('192.168.0.140', 5002)
    time.sleep(3.5)
