# -*- coding: utf-8 -*-

from calvin.runtime.south.plugins.async import async
from calvin.utilities.calvinlogger import get_logger
from calvin.utilities.calvin_callback import CalvinCB
from copy import deepcopy

_log = get_logger(__name__)


class HealthMonitor(object):
    def __init__(self, node):
        self.node = node
        self.value_range = {'min': 0.0, 'max': 1.0}
        self.threshold = 0.75
        self.healthy = None
        self.first_access = True
        self.perceived_healthy = None

    def set_health(self, health_value, cb=None):
        """
        Sets the health of a node. health_value should be a float between 0 (worst) and 1 (best).
        This value is then stored either as "good" or "bad" according to the threshold.
        If the health value is "bad", an actor migration is triggered.
        """

        if not self._correct_health_value(health_value, cb):
            return

        if float(health_value) < self.threshold:
            new_healthy = "no"
        else:
            new_healthy = "yes"

        if new_healthy != self.healthy or self.first_access:
            # Only update health if necessary
            self._update_health("nodeHealth", deepcopy(self.healthy), new_healthy, cb)
        else:
            # No update necessary
            async.DelayedCall(0, cb, value=health_value, status=True)

        self._migrate_if_unhealthy()

    def _update_health(self, prefix, old_value, new_value, cb=None):
        """
        Updates node health.
        Parameters:
        prefix: String used in storage for attribute, e.g. nodeCpuAvail.
        value: new value to set.
        cb: callback to receive response. Signature: cb(value, True/False)
        """
        if not self.node.storage.started:
            print "Storage not started!"
            async.DelayedCall(0, cb, value=new_value, status=False)
            return
        else:
            print "Storage has started, continue"

        self.healthy = new_value

        if not self.first_access:
            print "Is not first access, removing old yes index if it exists"
            self._remove_yes_index(old_value)
        else:
            self.first_access = False

        self._add_yes_index(new_value)

        self.node.storage.set(prefix=prefix, key=self.node.id, value=new_value, cb=CalvinCB(self._set_storage_cb))

        if cb:
            async.DelayedCall(0, cb, value=new_value, status=True)

    def _remove_yes_index(self, old_value):
        """
        Removes old indexes.
        """
        print "old value in remove_index is " + old_value

        # erase indexes related to old value
        if old_value is not None:
            if old_value == "yes":
                print "Old value is " + str(old_value)
                old_index = "/node/attribute/health/" + str(old_value)
                print "old index was " + old_index
                self.node.storage.remove_index(index=old_index, value=self.node.id, root_prefix_level=2,
                                          cb=CalvinCB(self._remove_index_storage_cb))
            else:
                print "Nothing done in remove yes index"

    def _add_yes_index(self, new_value):

        # TODO: #TN: use get_indexed_public() in AttributeResolver to set index instead

        if new_value is not None:
            if new_value == "yes":
                print "New value is " + str(new_value)
                new_index = "/node/attribute/health/" + str(new_value)
                print "new index is " + new_index
                self.node.storage.add_index(index=new_index, value=self.node.id, root_prefix_level=2,
                                       cb=CalvinCB(self._add_index_storage_cb))
            else:
                print "Nothing done in add yes index"

    def _add_index_storage_cb(self, value):
        print "Got to add index cb with result " + str(value)
        self.perceived_healthy = self.healthy

    def _remove_index_storage_cb(self, value):
        print "Got to remove index cb with result " + str(value)
        self.perceived_healthy = self.healthy

    def _set_storage_cb(self, key, value):
        _log.critical("\nVM: node health set to " + str(self.healthy))
        print "Got to set storage cb with result " + str(value)
        self.node.control.log_health_new(self.healthy)
        print "VM: send new health-value to log"

    def _migrate_if_unhealthy(self):
        if self.healthy == "no":
            print "Migration triggered!"
            self.node.am.health_triggered_migration()

    def _correct_health_value(self, health_value, cb):
        if not self._is_float(health_value):
            _log.critical("#TN: Invalid health type: %s" % str(type(health_value)))
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=False)
            return False

        if float(health_value) < self.value_range['min'] or float(health_value) > self.value_range['max']:
            _log.critical("#TN: Invalid health value: %s" % str(health_value))
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=False)
            return False

        return True

    @staticmethod
    def _is_float(value):
        try:
            float(value)
            return True
        except ValueError:
            return False
