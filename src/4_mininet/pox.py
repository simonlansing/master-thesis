from mininet.node import Controller
from os import environ

POXDIR = environ[ 'HOME' ] + '/pox'

                        #'openflow.of_01 --port=%s '
                        # forwarding.l2_learning
#                        'openflow.discovery'
#                        'host_tracker'
#                        'openflow.spanning_tree --no-flood --hold-down'



                        # 'forwarding.l2_multi'
                        # 'openflow.discovery'
                        # 'openflow.spanning_tree'

class POX(Controller):
    def __init__(self, name, cdir=POXDIR,
                 command='python pox.py',
                 cargs=('openflow.of_01 --port=%s '
                        'openflow.discovery'
                        'openflow.spanning_tree'),
                 **kwargs):
        Controller.__init__(self, name, cdir=cdir,
                            command=command,
                            cargs=cargs, **kwargs)

controllers = {'pox': POX}
