#!/usr/bin/env python
r"""This is the main module for the service manager platform.

The main module just uses the given parameter, analyzes them and starts
the single service manager on a host. The service manager is build after the behavioral design patterns mediator. All functionalities from other classes are working together through the service manager core.

Example:
    This is global usage of the service manager platform in the MIOT-testbed. There has to be one host, who starts the first server, all other nodes wait for their beginning through a migration.

    first server node:

            $ sudo python ../main.py -s ../performance_service.py
                                     -r
                                     -u 6,9,15,19,22,43,48,52,55,56,57,58

    all other nodes:
            $ sudo python ../main.py -u 6,9,15,19,22,43,48,52,55,56,57,58

"""

__version__ = '1.0'
__author__ = 'Simon Lansing'

import logging.config
import os
from optparse import Option, OptionParser
import signal
import sys
from service_manager_core import ServiceManagerCore

PROG = os.path.basename(os.path.splitext(__file__)[0])
LOGGER = logging.getLogger(__name__)

class MultipleOption(Option):
    """A helper class for the extraction of optional parameters.

    Some parameters are given as a list with comma separated values,
    which have to be splitted and stored in a single list. The class is derived from the superclass optparse.Option.
    """

    ACTIONS = Option.ACTIONS + ("extend",)
    STORE_ACTIONS = Option.STORE_ACTIONS + ("extend",)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + ("extend",)
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + ("extend",)

    def take_action(self, action, dest, opt, value, values, parser):
        """overridden method to check the given options and split them."""

        if action == "extend":
            lvalue = value.split(',')
            values.ensure_value(dest, []).extend(lvalue)
        else:
            Option.take_action(
                self, action, dest, opt, value, values, parser)

def signal_handler(signal, frame):
    """listen on the user input to stop the process."""

    LOGGER.info("Ctrl+C pressed")
    sys.exit(0)

def parse_config_arguments():
    """parses all given parameters from the command line and adds help text."""

    description = """This is the program's main file that starts the service manager."""
    parser = OptionParser(option_class=MultipleOption,
                          usage="usage: %prog [options] [args]",
                          version="%s %s" % (PROG, __version__),
                          description=description)

    parser.add_option('-a', '--adjacency_list_file',
                      action='store',
                      type='string',
                      default='/mnt/master-thesis/src/1_servicemanager/adjacency_list.json',
                      dest='adjacency_list_file',
                      help="path to the file of the adjacency list"+ \
                           "(necessary for the rounting part and searching"+ \
                           "possible servers). Default is \"../adjacency_list.json\".")

    parser.add_option('-p', '--service_transporter_port',
                      action='store',
                      type='int',
                      default=6001,
                      dest='service_transporter_port',
                      help="port of the service transporter for the communication"+ \
                           "and file transfer between servers. Default is 6001.")

    parser.add_option('-s', '--service_file',
                      action='store',
                      type='string',
                      default='./service.py',
                      dest='service_file',
                      help="path to the file of the service. Default is \"../service.py\".")

    parser.add_option('-r', '--run_service',
                      action='store_true',
                      default=False,
                      dest='run_service',
                      help="flag to run the service on startup of the server. Default is False.")

    parser.add_option('-t', '--testing',
                      action='store_true',
                      default=False,
                      dest='testing',
                      help="flag to deactivate testbed-specific functionalities"+ \
                           "and simulate incoming client connections. Default is False.")

    parser.add_option('-m', '--migration',
                      action='store_false',
                      default=True,
                      dest='migration',
                      help="flag to deactivate the migration function. Could be"+ \
                           "useful for specific services and tests. Default is True.")

    parser.add_option('-u', '--unreachable_hosts',
                      action='extend',
                      type='string',
                      dest='unreachable_hosts',
                      metavar='[<num>,...]',
                      help="comma separated list of unreachable"+ \
                           "hosts in the network. Default is [].")

    parser.add_option('-v', '--server_hosts',
                      action='extend',
                      type='string',
                      dest='server_hosts',
                      metavar='[<num>,...]',
                      help="comma separated list of possible server"+ \
                           "hosts in the network. Default is [].")

    parser.add_option('-c', '--connection_check_time',
                      action='store',
                      type='int',
                      default=30,
                      dest='connection_check_time',
                      help="time interval in seconds, which defines how often"+ \
                           "the server checks the recent connections for a better"+ \
                           "server. After checking a migration will be started"+ \
                           "to the new best server. Default is 10 [seconds].")

    parser.add_option('-d', '--cpu_ram_check_time',
                      action='store',
                      type='int',
                      default=1,
                      dest='cpu_ram_check_time',
                      help="time interval in seconds, which defines how often"+ \
                           "the server checks its CPU and RAM load. Default is 1 [second].")

    parser.add_option('-e', '--cpu_threshold',
                      action='store',
                      type='float',
                      default=20.0,
                      dest='cpu_threshold',
                      help="threshold for the percentage value of CPU usage."+ \
                           "If the average value in the interval of [connection_check_time]"+ \
                           "is higher than this threshold, a migration will"+ \
                           "be started. Default is 20.0 [percent].")

    parser.add_option('-f', '--ram_threshold',
                      action='store',
                      type='float',
                      default=15.0,
                      dest='ram_threshold',
                      help="threshold for the percentage value of RAM usage."+ \
                           "If the average value in the interval of [connection_check_time]"+ \
                           "is higher than this threshold, a migration will"+ \
                           "be started. Default is 15.0 [percent].")

    parser.add_option('-g', '--migration_threshold',
                      action='store',
                      type='float',
                      default=2.0,
                      dest='migration_threshold',
                      help="percentage threshold value for the migration between two servers."+ \
                           "If the percentage ETX difference between a new server and the running server"+ \
                           "is is lower than this threshold, a migration will"+ \
                           "not be started. Default is 1.0 [percent].")

    options, unrecognized_args = parser.parse_args()

    return options, unrecognized_args

def main():
    """ the main entry method for the complete service manager platform.

    This method extracts the options from the command line, transform the
    options for the given host environment, if necessary, and starts the
    platform.
    """

    logging.config.fileConfig("/mnt/master-thesis/src/1_servicemanager/logging.conf", disable_existing_loggers=False)
    signal.signal(signal.SIGINT, signal_handler)

    options, unrecognized_args = parse_config_arguments()

    LOGGER.debug("unrecognized arguments:"+ str(unrecognized_args))
    LOGGER.debug("options:" + str(options))

    if options.unreachable_hosts is None:
        options.unreachable_hosts = []

    server_hosts_transformed = []
    if options.server_hosts is not None:
        for server_host in options.server_hosts:
            if isinstance(server_host, (str, unicode)):
                server_host = int(server_host)
                server_hosts_transformed.append(server_host)
            elif isinstance(server_host, int):
                server_hosts_transformed.append(server_host)
        options.server_hosts = server_hosts_transformed

    if not os.path.exists(options.adjacency_list_file):
        sys.exit("Error in options: Cannot find adjacency list file"+ \
                 "\nUse option --help for more information.")

    if not os.path.exists(options.service_file) and options.run_service is True:
        sys.exit("Error in options: The \"run_service\" flag has been set, but"+ \
                 "the service file couldn\'t be found!\nUse option --help for more information.")

    with ServiceManagerCore(options) as service_manager_core:
        service_manager_core.run()

if __name__ == "__main__":
    main()
