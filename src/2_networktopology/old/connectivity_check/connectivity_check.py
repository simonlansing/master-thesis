import sys
import subprocess
import re
import json

BROADCAST_WLAN0 = "10.0.0.255"
BROADCAST_WLAN1 = "10.0.1.255"
BROADCAST_WLAN2 = "10.0.2.255"


ping_results = {}
#get all interfaces (eth and wlan)
#ifs = netifaces.interfaces()
ifs = ['wlan0', 'wlan1', 'wlan2']

#send ping broadcast only on wlan interfaces
for i in ifs:
    send_broadcast = False

    if(i == "wlan0"):
        host = BROADCAST_WLAN0
        send_broadcast = True
    if(i == "wlan1"):
        host = BROADCAST_WLAN1
        send_broadcast = True
    if(i == "wlan2"):
        host = BROADCAST_WLAN2
        send_broadcast = True

    if(send_broadcast == True):            
        ping = subprocess.Popen(["ping", "-b", "-c", "2", host], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        out, error = ping.communicate()

        if(out):  
            print "out is available"
            interface_ping_result = {}
            
            re_line = re.compile("^(\d+) bytes from (\d+).(\d+).(\d+).(\d+): icmp_seq=(\d+) ttl=(\d+) time=(\d+).(\d+) ms", re.MULTILINE)
            
            for match in re_line.finditer(out):
                key = match.group(2) + '.' + match.group(3) + '.' + match.group(4) + '.' + match.group(5)
                value = float(match.group(8) + '.' + match.group(9))

                if key in interface_ping_result:
                    interface_ping_result[key][0] += 1
                    interface_ping_result[key][1] += value
                else:
                    interface_ping_result[key] = [1, value]

                #print match.group(1) + '/' + match.group(2) + '.' + match.group(3) + '.' + match.group(4) + '.' + match.group(5) + '/' + match.group(6) + '/' + match.group(7) + '/' + match.group(8) + '.' + match.group(9)
                #sys.stdout.flush()
        
            for key, value in interface_ping_result.iteritems():
                avg_value = value[1] / value[0]
                interface_ping_result[key] = round(avg_value, 2)

            interface_ip_address = subprocess.check_output("/sbin/ifconfig "+ i +" | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}'", shell=True)

            #for i in netifaces.ifaddresses(i)[netifaces.AF_INET][0]['addr']
            ping_results[interface_ip_address] = interface_ping_result

print ping_results
ip_address = subprocess.check_output("/sbin/ifconfig eth0 | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}'", shell=True)
print ip_address
connectivity_file = open('./con_' + str(ip_address), 'wb')

try:
    connectivity_file.write(str(json.dumps(ping_results)))
finally:
    connectivity_file.close();