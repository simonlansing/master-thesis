import logging
import json
import re
import os
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np


LOGGER = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-6s: %(filename)s:%(lineno)s (%(threadName)s) %(funcName)s\n%(message)s', level=logging.DEBUG)
#sleeping_time_list, time_diff_list, connection_attempts_list, hop_counter_list, server_list
class FinalResult(object):
    def __init__(self, test_path):
        self.test_path = test_path

        self.config = {}
        regex_result = re.match(r"(.?)*test_time(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)-(?P<hour>\d+)-(?P<minute>\d+)-(?P<second>\d+)_rep(?P<repetition_counter>\d+)_sd(?P<start_delay>(\d+).(\d+))_ms(?P<message_size>\d+)_rpm(?P<repetitions_per_minute>\d+)_mt(?P<migration_time>\d+)_mtr(?P<migration_treshold>(\d+).(\d+))", self.test_path)

        if regex_result:
            self.config.update(regex_result.groupdict())

        self.sleeping_time_list = []
        self.time_diff_list = []
        self.connection_attempts_list = []
        self.hop_counter_list = []
        self.server_list = {}

        self.client_count = 0

        self.error_timed_out = 0
        self.error_max_attempts = 0
        self.error_conn_reset = 0
        self.error_unknown = 0

    def default(self, obj):
        return obj.__dict__

    def __repr__(self):
        return "{}".format(self.config)

class FinalServerResult(object):
    def __init__(self, test_path):
        self.test_path = test_path

        self.config = {}
        regex_result = re.match(r"(.?)*test_time(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)-(?P<hour>\d+)-(?P<minute>\d+)-(?P<second>\d+)_rep(?P<repetition_counter>\d+)_sd(?P<start_delay>(\d+).(\d+))_ms(?P<message_size>\d+)_rpm(?P<repetitions_per_minute>\d+)_mt(?P<migration_time>\d+)_mtr(?P<migration_treshold>(\d+).(\d+))", self.test_path)
        
        if regex_result:
            self.config.update(regex_result.groupdict())

        self.migrations_possible_count = 0
        self.migrations_done_count = 0
        self.migration_rejected_mig_tresh_count = 0
        self.migration_rejected_num1_count = 0
        self.migrations_error_count = 0

        self.migration_rejected_only_one_server = 0
    def default(self, obj):
        return obj.__dict__

class FinalEvaluation(object):
    def __init__(self):
        LOGGER.debug('evaluation init')

        self.final_result_list = []
        self.final_server_result_list = []
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        LOGGER.debug('evaluation exit')
        return self

    def extract_test_result(self, iteration, test_iteration_results):
        sleeping_time = float(test_iteration_results['sleeping_time'])
        connection_attempts = int(test_iteration_results['connection_attempts'])
        hop_counter = int(test_iteration_results['hop_counter'])
        time_difference = None
        error_timed_out = 0
        error_max_attempts = 0
        error_conn_reset = 0
        error_unknown = 0
        try:
            if test_iteration_results['time_diff'] == "timed out":
                error_timed_out = 1
            elif test_iteration_results['time_diff'] == "reached max attempts":
                error_max_attempts = 1
            elif test_iteration_results['time_diff'] == "[Errno 104] Connection reset by peer":
                error_conn_reset = 1
            else:
                time_difference = float(test_iteration_results['time_diff'].split(':')[2])
        except IndexError as exc:
            LOGGER.error("IndexError in iteration %s: %s", iteration, test_iteration_results['time_diff'])
            error_unknown = 1

        server = test_iteration_results['server_ip']

        return sleeping_time, time_difference, connection_attempts, hop_counter, server, \
            error_timed_out, error_max_attempts, error_conn_reset, error_unknown

    def open_client_test_file(self, file_path, final_results, node_number, remove_results_same_host):
        test_results = None
        try:
            #LOGGER.info(file_path)
            with open(file_path, 'r') as test_file:
                #LOGGER.info(test_file.read())
                test_results = eval(test_file.read())
                for key, values in test_results.items():
                    sleeping_time, time_difference, connection_attempts, hop_counter, server, error_timed_out, error_max_attempts, error_conn_reset, error_unknown = \
                        self.extract_test_result(key, values)

                    if remove_results_same_host is True and node_number == server.split('.')[3]:
                        LOGGER.info("node_number and server are equal: {}->{}".format(node_number, server))
                    else:
                        #LOGGER.info("added entry: {}->{}".format(node_number, server))
                        final_results.sleeping_time_list.append(sleeping_time)
                        if time_difference is not None:
                            final_results.time_diff_list.append(time_difference)
                        final_results.connection_attempts_list.append(connection_attempts)
                        final_results.hop_counter_list.append(hop_counter)

                        if server in final_results.server_list:
                            final_results.server_list[server] += 1
                        else:
                            final_results.server_list[server] = 1

                        final_results.error_timed_out += error_timed_out
                        final_results.error_max_attempts += error_max_attempts
                        final_results.error_conn_reset += error_conn_reset
                        final_results.error_unknown += error_unknown
        except Exception as exc:
            LOGGER.error(exc)
            sys.exit(0)

        return final_results

    def import_client_test_files(self, test_path_list, remove_results_same_host):
        for test_path in test_path_list:
            #LOGGER.info(test_path)
            #sys.exit(0)
            final_results = FinalResult(test_path)
            client_count = 0
            for subdir, _, files in os.walk(test_path):
                for file in files:
                    file_path = os.path.join(subdir, file)
                    if 'client_results_output.log' in file_path:
                        client_count += 1
                        node_number = subdir.split('\h')[1]
                        #LOGGER.info("logfile found from host {}".format(node_number))
                        final_results = self.open_client_test_file(
                            file_path, final_results,
                            node_number, remove_results_same_host)
                        final_results.client_count = client_count

            self.final_result_list.append(final_results)

    def open_server_test_file(self, file_path, final_results, node_number, remove_results_same_host):
        test_results = None
        try:
            #LOGGER.info(file_path)
            with open(file_path, 'r') as server_log_file:
                #LOGGER.info(test_file.read())
                server_log = server_log_file.read()
                
                regex_migrations_possible = "check_recent_connections_for_best_server: check_recent_connections_for_best_server enter"

                regex_migrations_done = "send_service: service status code by other server: 200"
                regex_migrations_done2 = "send_service: service status code by other server: OKAY"

                regex_migration_rejected_mig_tresh = "check_recent_connections_for_best_server: The new server wouldn't be really better as a server. Migration rejected."

                regex_migration_rejected_num1 = "check_recent_connections_for_best_server: No node as best server found!"

                regex_migration_error_timed = "run: Service could not be migrated: timed out"
                regex_migration_error_conflict = "run: Service could not be migrated: CONFLICT"

                regex_migration_rejected_only_one_server = r"check_recent_connections_for_best_server: Best Nodes: \[\([0-9]*, [0-9]*.[0-9]*\)\].*"

                regex_migration_rejected_num1_correction = r"migration_checker\.py:21[0-9] \(Thread-\d*\) check_recent_connections_for_best_server: Me=\(([0-9]*), [0-9]*.[0-9]*\), Other=\((\1), [0-9]*.[0-9]*\)"



                #regex_test_already_over = r"migration_checker\.py:21[0-9] \(Thread-\d*\) check_recent_connections_for_best_server: Me=\([0-9]*, [0-9]*.[0-9]*\), Other=\([0-9]*, 0\.0\)"



                migrations_possible = [m.start() for m in re.finditer(regex_migrations_possible, server_log)]
                migrations_done = [m.start() for m in re.finditer(regex_migrations_done, server_log)]
                migrations_done2 = [m.start() for m in re.finditer(regex_migrations_done2, server_log)]
                migration_rejected_mig_tresh = [m.start() for m in re.finditer(regex_migration_rejected_mig_tresh, server_log)]
                migration_rejected_num1 = [m.start() for m in re.finditer(regex_migration_rejected_num1, server_log)]
                migration_rejected_num1_correction = [m.start() for m in re.finditer(regex_migration_rejected_num1_correction, server_log)]
                migration_errors = [m.start() for m in re.finditer(regex_migration_error_timed, server_log)]
                migration_conflict = [m.start() for m in re.finditer(regex_migration_error_conflict, server_log)]
                #test_already_over = [m.start() for m in re.finditer(regex_test_already_over, server_log)]

                migration_rejected_only_one_server = [m.start() for m in re.finditer(regex_migration_rejected_only_one_server, server_log)]
                #if len(test_already_over) > 0:
                #    LOGGER.info("%s, %s  %s", len(test_already_over), test_already_over, file_path)

                if len(migrations_done) > 0 and len(migrations_done2) > 0:
                    LOGGER.info("There cant be two server versions")
                    sys.exit(0)

                final_results.migrations_done_count += len(migrations_done) + len(migrations_done2) + len(migration_conflict)
                final_results.migration_rejected_mig_tresh_count += len(migration_rejected_mig_tresh) - len(migration_rejected_num1_correction)

                final_results.migration_rejected_num1_count += len(migration_rejected_num1) + len(migration_rejected_num1_correction)
                final_results.migrations_error_count += len(migration_errors)

                final_results.migrations_possible_count = final_results.migrations_done_count + final_results.migration_rejected_mig_tresh_count+final_results.migration_rejected_num1_count+final_results.migrations_error_count

                final_results.migration_rejected_only_one_server += len(migration_rejected_only_one_server)


                return final_results

        except Exception as exc:
            LOGGER.error(exc, exc_info=True)
            sys.exit(0)

        return final_results

    def import_server_test_files(self, test_path_list):
        for test_path in test_path_list:
            #LOGGER.info(test_path)
            #sys.exit(0)
            final_results = FinalServerResult(test_path)

            for subdir, dirs, files in os.walk(test_path):
                for file in files:
                    file_path = os.path.join(subdir, file)
                    if 'performance_server.log' in file_path:
                        node_number = subdir.split('\h')[1]
                        #LOGGER.info("logfile found from host {}".format(node_number))
                        final_results = self.open_server_test_file(
                            file_path, final_results,
                            node_number, remove_results_same_host)

            # LOGGER.info("1=%s", final_results.migrations_possible_count)
            # LOGGER.info("2=%s", final_results.migrations_done_count)
            # LOGGER.info("3=%s", final_results.migration_rejected_mig_tresh_count)
            # LOGGER.info("4=%s", final_results.migration_rejected_num1_count)
            # LOGGER.info("5=%s", final_results.migrations_error_count)
            # LOGGER.info("6=%s", final_results.migration_rejected_only_one_server)

            self.final_server_result_list.append(final_results)
    def mean(self, data):
        """Return the sample arithmetic mean of data."""
        n = len(data)
        if n < 1:
            raise ValueError('mean requires at least one data point')
        return sum(data)/n # in Python 2 use sum(data)/float(n)

    def _ss(self, data):
        """Return sum of square deviations of sequence data."""
        c = self.mean(data)
        ss = sum((x-c)**2 for x in data)
        return ss

    def pstdev(self, data):
        """Calculates the population standard deviation."""
        n = len(data)
        if n < 2:
            raise ValueError('variance requires at least two data points')
        ss = self._ss(data)
        pvar = ss/n # the population variance
        return pvar**0.5

    def stdev(self, data):
        """Calculates the population standard deviation."""
        n = len(data)
        if n < 2:
            raise ValueError('variance requires at least two data points')
        ss = self._ss(data)
        var = ss/(n-1) # the population variance
        return var**0.5

    def calculate_statistics_of_sorted_list(self, final_results, normalize):
        try:
            sorted_list = []
            outliers_counter = 5

            #transform the values from seconds to milliseconds
            for val in final_results.time_diff_list:
                sorted_list.append(val * 1000)


            #normalize sorted list by package size
            message_size = int(final_results.config['message_size'])
            print(message_size, type(message_size))

            if message_size != 1460 and normalize:
                print(">>>>>>NORMALIZE<<<<<<")
                normalization_factor = 1460 / message_size
                sorted_list = [x * normalization_factor for x in sorted_list]

            final_results.median = np.median(sorted_list)
            final_results.upper_quartile = np.percentile(sorted_list, 75)
            final_results.lower_quartile = np.percentile(sorted_list, 25)
            final_results.range_val = sorted_list[-1] - sorted_list[0]

            final_results.iqr = final_results.upper_quartile - final_results.lower_quartile
            final_results.iqr3_0 = 3.0 * final_results.iqr

            final_results.counter_minor_outlier = 0
            final_results.counter_extreme_outlier = 0

            final_results.rtt_mean = self.mean(sorted_list)
            final_results.rtt_pstdev = self.pstdev(sorted_list)
            final_results.rtt_stdev = self.stdev(sorted_list)

            final_results.reconnection_mean = self.mean(final_results.connection_attempts_list)
            final_results.reconnection_stdev = self.stdev(final_results.connection_attempts_list)
            final_results.hop_mean = self.mean(final_results.hop_counter_list)
            final_results.hop_stdev = self.stdev(final_results.hop_counter_list)

            list_boxplot = plt.boxplot(sorted_list)
            boxplot_values = [item.get_ydata()[1] for item in list_boxplot['whiskers']]
            final_results.lower_whisker = boxplot_values[0]
            final_results.upper_whisker = boxplot_values[1]


            list_of_fliers = [item.get_ydata() for item in list_boxplot['fliers']][0]
            #LOGGER.info("listoffliers={}".format(list_of_fliers))
            #LOGGER.info("count={}".format(len(list_of_fliers)))

            list_of_minor_outliers = []
            list_of_extreme_outliers = []
            for value in list_of_fliers:
                if value >= final_results.upper_whisker and value < final_results.iqr3_0:
                    final_results.counter_minor_outlier += 1
                    list_of_minor_outliers.append(value)
                elif value >= final_results.iqr3_0:
                    final_results.counter_extreme_outlier += 1
                    list_of_extreme_outliers.append(value)

            # final_results.means_minor_outliers = []
            # if len(list_of_minor_outliers) > 0:
            #     for value in range(int((len(list_of_minor_outliers)/1000)) + 1):
            #         pos_min = value*1000
            #         pos_max = value*1000+1000
            #         mean = self.mean(list_of_minor_outliers[pos_min:pos_max])
            #         final_results.means_minor_outliers.append(mean)

            # final_results.means_extreme_outliers = []
            # if len(list_of_extreme_outliers) > 0:
            #     for value in range(int((len(list_of_extreme_outliers)/1000)) + 1):
            #         pos_min = value*1000
            #         pos_max = value*1000+1000
            #         mean = self.mean(list_of_extreme_outliers[pos_min:pos_max])
            #         final_results.means_extreme_outliers.append(mean)

            final_results.means_all_outliers = []
            combination_value = len(list_of_fliers) / outliers_counter
            print("combination value=", combination_value)
            print("len_all_outliers=", len(list_of_fliers))
            print("len=", len(sorted_list))
            for value in range(int((len(list_of_fliers)/combination_value))):
                pos_min = value*combination_value
                pos_max = value*combination_value+combination_value
                print("pos_min=", pos_min, " pos_max=", pos_max)

                mean = self.mean(list_of_fliers[pos_min:pos_max])
                final_results.means_all_outliers.append(mean)

            outliers_means_str = '  '
            for outliers_means in final_results.means_all_outliers:
                outliers_means_str += "(0, {}) ".format(outliers_means)

            final_results.minimum_val = sorted_list[0]
            final_results.maximum_val = sorted_list[-1]
            final_results.total_count = len(sorted_list)

            LOGGER.info("servers={}".format(final_results.server_list))

            # LOGGER.info(
            #     "{}\n".format(final_results.test_path) + 
            #     "median={}\n".format(final_results.median) +
            #     "upper quartile={}\n".format(final_results.upper_quartile) +
            #     "lower quartile={}\n".format(final_results.lower_quartile) +
            #     "upper whisker={}\n".format(final_results.upper_whisker)+
            #     "lower whisker={}\n\n".format(final_results.lower_whisker)+
            #     "IQR={}\n".format(final_results.iqr) +
            #     "IQR3.0={}\n".format(final_results.iqr3_0) +
            #     "minor_outliers (1.5xIQR to 3.0xIQR)={}\n".format(final_results.counter_minor_outlier) +
            #     "extreme_outliers (> 3.0xIQR)={}\n".format(final_results.counter_extreme_outlier) +
            #     "means_minor_outliers ={}\n".format(final_results.means_minor_outliers) +
            #     "means_extreme_outliers ={}\n\n".format(final_results.means_extreme_outliers) +
            #     "means_all_outliers ={}\n\n".format(outliers_means_str) +
            #     "minimum={}\n".format(final_results.minimum_val) + 
            #     "maximum={}\n".format(final_results.maximum_val) +
            #     "range={}\n".format(final_results.range_val) +
            #     "total_count={}\n".format(final_results.total_count) +
            #     "fatal_errors={}\n\n".format(final_results.error_unknown) + 
            #     "mean={}\n".format(final_results.mean) +
            #     "pstdev={}\n".format(final_results.pstdev) +
            #     "stdev={}\n".format(final_results.stdev) +
            #     "servers={}".format(final_results.server_list)
            # )
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)
            #LOGGER.info(sorted_list)
            #LOGGER.info(final_results.test_path)
            sys.exit(0)

        return final_results

    def show_boxplot(self):
        try:
            all_lists = []
            x_axis_naming = []
            for final_result in self.final_result_list:
                all_lists.append(final_result.time_diff_list)

            time_diff_boxplots = plt.boxplot(all_lists)#, showfliers=False)#showmeans=True)
            plt.setp(time_diff_boxplots['boxes'], color='black')
            plt.setp(time_diff_boxplots['whiskers'], color='black')
            plt.setp(time_diff_boxplots['fliers'], color='red', marker='+')
            
            plt.show()
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)

    def dump_evaluation_results_into_csvfile(self, filename, index, final_results):
        if index == 0:
            with open(filename, 'w') as result_output_file:
                result_output_file.write(
                    "clients_count;repetition;message_size;repetitions_per_minute;migration_time;migration_treshold;"+\
                    "error_timed_out;error_timed_out_percentage;"+\
                    "error_max_attempts;error_max_attempts_percentage;"+\
                    "error_conn_reset;error_conn_reset_percentage;"+\
                    "error_unknown;error_unknown_percentage;"+\
                    "rtt_mean;rtt_stdev;"+\
                    "reconnection_mean;reconnection_stdev;"+\
                    "hop_mean;hop_stdev;"+\
                    "med;uq;lq;uw;lw;om\n")

        with open(filename, 'a') as result_output_file:
            outliers_means_str = ''
            for outliers_means in final_results.means_all_outliers:
                outliers_means_str += "(0, {}) ".format(outliers_means)


            max_repetitions = final_results.client_count * int(final_results.config['repetition_counter'])

            error_timed_out_percentage = (final_results.error_timed_out / max_repetitions) * 100
            error_max_attempts_percentage = (final_results.error_max_attempts / max_repetitions) * 100
            error_conn_reset_percentage = (final_results.error_conn_reset / max_repetitions) * 100
            error_unknown_percentage = (final_results.error_unknown / max_repetitions) * 100

            result_output_file.write("{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{}\n".format(
                final_results.client_count,
                final_results.config['repetition_counter'],
                final_results.config['message_size'],
                final_results.config['repetitions_per_minute'],
                final_results.config['migration_time'],
                final_results.config['migration_treshold'],
                final_results.error_timed_out,
                error_timed_out_percentage,
                final_results.error_max_attempts,
                error_max_attempts_percentage,
                final_results.error_conn_reset,
                error_conn_reset_percentage,
                final_results.error_unknown,
                error_unknown_percentage,
                final_results.rtt_mean,
                final_results.rtt_stdev,
                final_results.reconnection_mean,
                final_results.reconnection_stdev,
                final_results.hop_mean,
                final_results.hop_stdev,
                final_results.median,
                final_results.upper_quartile,
                final_results.lower_quartile,
                final_results.upper_whisker,
                final_results.lower_whisker,
                outliers_means_str))

    def dump_evaluation_server_results_into_csvfile(self, filename, index, final_results):
        if index == 0:
            with open(filename, 'w') as result_output_file:
                result_output_file.write("repetition;message_size;repetitions_per_minute;migration_time;migration_treshold;"+\
                    "migrations_possible;"+\
                    "migrations_done;migrations_done_percentage;"+\
                    "migration_rejected_mig_tresh;migration_rejected_mig_tresh_percentage;"+\
                    "migration_rejected_num1;migration_rejected_num1_percentage;"+\
                    "migrations_error;migrations_error_percentage\n")

        migrations_done_percentage = (final_results.migrations_done_count / final_results.migrations_possible_count) * 100
        migration_rejected_mig_tresh_percentage = (final_results.migration_rejected_mig_tresh_count / final_results.migrations_possible_count) * 100
        migration_rejected_num1_percentage = (final_results.migration_rejected_num1_count / final_results.migrations_possible_count) * 100
        migrations_error_percentage = (final_results.migrations_error_count / final_results.migrations_possible_count) * 100

        with open(filename, 'a') as result_output_file:
            result_output_file.write("{};{};{};{};{};{};{};{};{};{};{};{};{};{}\n".format(
                final_results.config['repetition_counter'],
                final_results.config['message_size'],
                final_results.config['repetitions_per_minute'],
                final_results.config['migration_time'],
                final_results.config['migration_treshold'],
                final_results.migrations_possible_count,
                final_results.migrations_done_count, migrations_done_percentage,
                final_results.migration_rejected_mig_tresh_count, migration_rejected_mig_tresh_percentage,
                final_results.migration_rejected_num1_count, migration_rejected_num1_percentage,
                final_results.migrations_error_count, migrations_error_percentage))

    def calculate_evaluation_results(self, output_file_name, index, final_results):
        try:
            final_results.sleeping_time_list.sort()
            final_results.time_diff_list.sort()
            final_results.connection_attempts_list.sort()
            final_results.hop_counter_list.sort()
            #LOGGER.info(final_results.connection_attempts_list)
            if "testcase5" in output_file_name or "testcase6" in output_file_name:
                normalize = False
            else:
                normalize = True
            final_results = self.calculate_statistics_of_sorted_list(final_results, normalize)

            #LOGGER.info("server_list={}".format(final_results.server_list))

            #LOGGER.info(final_results.time_diff_list)
            self.dump_evaluation_results_into_csvfile(output_file_name, index, final_results)
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)
            sys.exit(0)

    def calculate_evaluation_server_results(self, output_file_name, index, final_results):
        try:
            self.dump_evaluation_server_results_into_csvfile(output_file_name, index, final_results)
        except Exception as exc:
            LOGGER.error(exc, exc_info=True)

def get_config(number):
    output_file_prefix = '../../Text/tables/'

    testcase1_prefix_path = '../../Results/final_tests/testcase_1_throughput_wo_loss/'
    testcase2_prefix_path = '../../Results/final_tests/testcase_2_throughput_wo_loss/'
    testcase3_prefix_path = '../../Results/final_tests/testcase_3_throughput_wo_loss/'
    testcase4_prefix_path = '../../Results/final_tests/testcase_4_throughput_wo_loss/'
    testcase5_prefix_path = '../../Results/final_tests/testcase_5_etx_w_loss_in_seperate_net/'
    testcase6_prefix_path = '../../Results/final_tests/testcase_6_etx_w_loss_in_seperate_net/'

    testcase_number = number + 1
    output_file_clients = None
    output_file_servers = None
    test_path_list = None


    fixed_measuring_row = testcase2_prefix_path+'test_time2016-10-05-22-06-06_rep2000_sd0.0_ms1460_rpm10_mt30_mtr2.0'
    if testcase_number == 1:
        output_file_clients = output_file_prefix+'testcase1_client_results.csv'
        output_file_servers = output_file_prefix+'testcase1_server_results.csv'
        test_path_list = [
            fixed_measuring_row,
            #testcase1_prefix_path+'test_time2017-01-13-14-47-33_rep2000_sd0.0_ms1460_rpm10_mt30_mtr2.0',
            testcase1_prefix_path+'test_time2016-10-07-12-28-26_rep2000_sd0.0_ms1460_rpm30_mt30_mtr2.0',
            testcase1_prefix_path+'test_time2016-10-05-16-13-45_rep2000_sd0.0_ms1460_rpm60_mt30_mtr2.0',
            testcase1_prefix_path+'test_time2017-01-11-15-14-32_rep10000_sd0.0_ms1460_rpm120_mt30_mtr2.0_new',
            testcase1_prefix_path+'test_time2017-01-11-09-15-27_rep10000_sd0.0_ms1460_rpm180_mt30_mtr2.0_new',
            testcase1_prefix_path+'test_time2017-01-10-16-56-13_rep10000_sd0.0_ms1460_rpm240_mt30_mtr2.0_new',
            testcase1_prefix_path+'test_time2017-01-10-13-55-50_rep10000_sd0.0_ms1460_rpm300_mt30_mtr2.0_new'
        ]

    if testcase_number == 2:
        output_file_clients = output_file_prefix+'testcase2_client_results.csv'
        output_file_servers = output_file_prefix+'testcase2_server_results.csv'
        test_path_list = [
            testcase2_prefix_path+'test_time2016-10-05-17-59-01_rep2000_sd0.0_ms1460_rpm10_mt10_mtr2.0',
            fixed_measuring_row,
            testcase2_prefix_path+'test_time2016-10-06-08-34-44_rep2000_sd0.0_ms1460_rpm10_mt60_mtr2.0',
            testcase2_prefix_path+'test_time2016-10-07-14-53-52_rep2000_sd0.0_ms1460_rpm10_mt180_mtr2.0',
            testcase2_prefix_path+'test_time2016-10-06-14-55-23_rep2000_sd0.0_ms1460_rpm10_mt300_mtr2.0'
        ]

    if testcase_number == 3:
        output_file_clients = output_file_prefix+'testcase3_client_results.csv'
        output_file_servers = output_file_prefix+'testcase3_server_results.csv'
        test_path_list = [
            fixed_measuring_row,
            testcase3_prefix_path+'test_time2016-10-08-15-34-20_rep2000_sd0.0_ms7300_rpm10_mt30_mtr2.0',
            testcase3_prefix_path+'test_time2016-10-07-18-49-30_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0',
            testcase3_prefix_path+'test_time2016-10-08-20-01-29_rep2000_sd0.0_ms29200_rpm10_mt30_mtr2.0',
            testcase3_prefix_path+'test_time2016-10-09-15-12-00_rep2000_sd0.0_ms43800_rpm10_mt30_mtr2.0',
        ]

    if testcase_number == 4:
        output_file_clients = output_file_prefix+'testcase4_client_results.csv'
        output_file_servers = output_file_prefix+'testcase4_server_results.csv'
        test_path_list = [
            #testcase4_prefix_path+'test_time2016-10-XX-XX-XX-XX_rep2000_sd0.0_ms146000_rpm0.1_mt30_mtr2.0',
            testcase4_prefix_path+'test_time2016-10-10-14-40-46_rep2000_sd0.0_ms14600_rpm1_mt30_mtr2.0',
            fixed_measuring_row,
            testcase4_prefix_path+'test_time2016-10-10-13-50-20_rep2000_sd0.0_ms146_rpm100_mt30_mtr2.0',
            #testcase4_prefix_path+'test_time2016-10-10-13-03-28_rep2000_sd0.0_ms49_rpm300_mt30_mtr2.0',
            testcase4_prefix_path+'test_time2016-10-26-18-14-10_rep10000_sd0.0_ms49_rpm300_mt30_mtr2.0_new'
        ]

    if testcase_number == 5:
        output_file_clients = output_file_prefix+'testcase5_client_results.csv'
        output_file_servers = output_file_prefix+'testcase5_server_results.csv'
        test_path_list = [
            testcase5_prefix_path+'test_time2016-10-28-12-34-35_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario1',
            testcase5_prefix_path+'test_time2016-11-04-14-30-04_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario6',
            testcase5_prefix_path+'test_time2016-10-22-17-47-23_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario2',
            testcase5_prefix_path+'test_time2016-10-20-18-03-22_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario3',
            testcase5_prefix_path+'test_time2016-10-22-21-56-49_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario4',
            testcase5_prefix_path+'test_time2016-10-25-15-39-45_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario5'
        ]

    if testcase_number == 6:
        output_file_clients = output_file_prefix+'testcase6_client_results.csv'
        output_file_servers = output_file_prefix+'testcase6_server_results.csv'
        test_path_list = [
            testcase6_prefix_path+'test_time2016-10-26-11-56-11_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario1',
            testcase6_prefix_path+'test_time2016-10-22-13-18-12_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario2',
            testcase6_prefix_path+'test_time2016-10-21-11-40-39_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario3',
            testcase6_prefix_path+'test_time2016-10-21-18-46-40_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario4',
            testcase6_prefix_path+'test_time2016-10-26-02-05-40_rep2000_sd0.0_ms14600_rpm10_mt30_mtr2.0_scenario5'
        ]

    return output_file_clients, output_file_servers, test_path_list

if __name__ == "__main__":

    try:
        for config_index in range(6):
            output_file_clients, output_file_servers, test_path_list = get_config(config_index)
            #LOGGER.info(test_path_list)

            remove_results_same_host = False

            if output_file_clients is None or output_file_servers is None or test_path_list is None:
                continue

            with FinalEvaluation() as final_evaluation:
                    final_evaluation.import_client_test_files(test_path_list, remove_results_same_host)

                    for result_index, result in enumerate(final_evaluation.final_result_list):
                        print(result)
                        final_evaluation.calculate_evaluation_results(
                            output_file_clients, result_index, result)

                    final_evaluation.import_server_test_files(test_path_list)
                    for result_index, result in enumerate(final_evaluation.final_server_result_list):
                        final_evaluation.calculate_evaluation_server_results(
                            output_file_servers, result_index, result)


                    #final_evaluation.show_boxplot()
    except Exception as exc:
        LOGGER.error(exc, exc_info=True)
        sys.exit(0)