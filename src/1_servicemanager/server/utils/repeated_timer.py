"""This module contains the RepeatedTimer class.

The repeated timer allows to call a callback function after every given number
of seconds. It is even possible to add arguments to the callback function.
"""

import logging
import threading

LOGGER = logging.getLogger(__name__)

class RepeatedTimer(object):
    """A class for calling repeated events after given seconds of time.

    The RepeatedTimer calls a callback function every given seconds, until an
    external function stops the timer. After the stop signal, the timer can't
    be started again. In this case, the whole timer object must be deleted and
    created again.

    Attributes:
        stopped_event (threading.Event): An event flag to stop the repeated
            timer.
        seconds (:obj:`int`): The seconds between two calls of the callback
            function.
        cb_function (:obj: function): The function, which should be called.
        args (:obj:`list` of object): The arguments for the callback function.

    """
    def __init__(self, seconds, cb_function, *args):
        """The initialization function of the class RepatedTimer.

        The function initializes the RepeadedTimer instance.

        Args:
            seconds (:obj:`int`): The seconds between two calls of the callback
                function. 
            cb_function (:obj: function): The function, which should be called.
            args (:obj:`list` of object): The arguments for the callback
                function.
        """

        self.stopped_event = threading.Event()
        self.seconds = seconds
        self.cb_function = cb_function
        self.args = args

        self.repeated_thread = None

    def start(self):
        """The method to start the repeated timer.

        This functions initializes the repeated timer in a new thread and
        runs it.
        """

        if self.repeated_thread is None:
            self.repeated_thread = threading.Thread(
                target=self.run,
                args=(self.cb_function, self.seconds, self.args, ))
            self.repeated_thread.start()

    def is_alive(self):
        """Method to check the status of the RepeadedTimer.

        If the repeated timer thread has been started, this function will return the active status of the timer.

        Returns:
            The thread status of the timer, if it has been started, otherwise None.
        """

        if self.repeated_thread:
            return self.repeated_thread.is_alive()
        return None

    def join(self):
        """Method to join the thread of the RepeatedTimer."""

        if self.repeated_thread:
            self.repeated_thread.join()

    def run(self, cb_function, seconds, args):
        """Main core method of the RepeatedTimer thread.

            The thread of the repeated timer waits the given seconds. After this time period, the callback function will be called with the given args. It the Event stopped_event is set from outside, the function will stop the process and destroys the thread.

            Args: 
                cb_function (:obj: function): The function, which should be
                    called.
                seconds (:obj:`int`): The seconds between two calls of the
                    callback function.
                args (:obj:`list` of object): The arguments for the callback
                    function.
        """

        LOGGER.debug("Starting repeated timer, cb_function=%s, seconds=%s,"+
                     "args=%s", cb_function, seconds, args)

        while not self.stopped_event.wait(seconds):
            try:
                if args:
                    cb_function(args)
                else:
                    cb_function()
            except Exception as exc:
                LOGGER.info(str(exc), exc_info=True)
        LOGGER.info("This RepeatedTimer is stopping now, cb_function_name=%s",
                    cb_function.__name__)
        self.stopped_event.clear()

        del self.repeated_thread
        self.repeated_thread = None

    def cancel(self):
        """Method to cancel and stop the active RepeatedTimer."""
        self.stopped_event.set()
