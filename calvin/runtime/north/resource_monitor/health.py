# -*- coding: utf-8 -*-

from calvin.runtime.south.plugins.async import async
from calvin.runtime.north.resource_monitor.helper import ResourceMonitorHelper
from calvin.utilities.calvinlogger import get_logger

_log = get_logger(__name__)


class HealthMonitor(object):
    def __init__(self, node):
        self.node_id = node.id
        self.storage = node.storage
        self.actor_manager = node.am
        self.control = node.control
        self.helper = ResourceMonitorHelper(self.node_id, self.storage)
        self.value_range = {'min': 0.0, 'max': 1.0}
        self.threshold = 0.75

        self._set_initial_health()

    def _set_initial_health(self):
        self.set_health(self.value_range['max'])


    def set_health(self, health_value, cb=None):
        """
        Sets the health of a node. health_value should be a float between 0 (worst) and 1 (best).
        This value is then stored either as "good" or "bad" according to the threshold.
        If the health value is "bad", an actor migration is triggered.
        """
        if not self._is_float(health_value):
            _log.critical("#TN: Invalid health type: %s" % str(type(health_value)))
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=False)
            return

        if float(health_value) < self.value_range['min'] or float(health_value) > self.value_range['max']:
            _log.critical("#TN: Invalid health value: %s" % str(health_value))
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=False)
            return

        if float(health_value) < self.threshold:
            health_status = "bad"
        else:
            health_status = "good"

        self.helper.set("nodeHealth", "health", health_status, cb)

        _log.critical("\nVM: node health set to " + str(health_status))

        self.control.log_health_new(health_status)
        print "VM: send new health-value to log"

        if health_status == "bad":
            self.actor_manager.health_triggered_migration()

    def stop(self):
        """
        Stops monitoring, cleaning storage
        """
        self.helper.set("nodeHealth", "health", value=None, cb=None)
        self.storage.delete(prefix="nodeHealth", key=self.node_id, cb=None)

    def _is_float(self, value):
        try:
            float(value)
            return True
        except ValueError:
            return False
