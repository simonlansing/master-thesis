#!/usr/bin/python
import logging
import signal
import sys
#import fcntl
import struct
#import array
import subprocess
#import netifaces

LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(name)s (%(threadName)s) - %(message)s', level=logging.DEBUG)

def signal_handler(signal, frame):
    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

class IPerfService(object):
    def __init__(self):
        self.startup_wlan_interfaces()

        cmd = "hostname | egrep -o [1-9]+[0-9]*"
        hostname_call = subprocess.Popen(cmd, shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.own_hostname = int(hostname_call.communicate()[0].strip())

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

    def run(self):
        try:
            proc = subprocess.call(['/usr/bin/iperf3', '-s'],
                                   stdout=open('iperf_server_results%i.log' % self.own_hostname, 'wb'),
                                   stderr=open('iperf_server_err%i.log' % self.own_hostname, 'wb'))
        except Exception as e:
            LOGGER.error('Failed to start iperf service: ' + str(e), exc_info=True)
        return

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    with IPerfService() as iperf_service:
        iperf_service.run()