# -*- coding: utf-8 -*-

from calvin.runtime.south.plugins.async import async
from calvin.utilities.calvinlogger import get_logger
from calvin.utilities.calvin_callback import CalvinCB
from calvin.utilities.attribute_resolver import AttributeResolver
from copy import deepcopy

_log = get_logger(__name__)


class HealthMonitor(object):
    def __init__(self, node):
        self.node = node
        self.value_range = {'min': 0.0, 'max': 1.0}
        self.threshold = 0.75
        self.healthy = None
        self.cell = node.cell if node.cell else "1"

        print "self.cell is " + self.cell

    def set_health(self, health_value, cb=None):
        """
        Sets the health of a node. health_value should be a float between 0 (worst) and 1 (best).
        This value is then stored either as "good" or "bad" according to the threshold.
        If the health value is "bad", an actor migration is triggered.
        """
        actor_ids = self.node.am.get_actors_with_imei("abcd1234")

        print "actor ids in set_health: " + str(actor_ids)

        if not self._correct_health_value(health_value, cb):
            return

        # TODO: #TN: Add hysteresis interval to avoid oscillations?
        if float(health_value) < self.threshold:
            new_healthy = "no"
        else:
            new_healthy = "yes"

        if new_healthy != self.healthy:
            # Only update health if necessary
            self._update_health(deepcopy(self.healthy), new_healthy, cb)
        else:
            # No update necessary
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=True)

        self._migrate_if_unhealthy()

    def set_cell(self, new_cell, cb=None):

        # TODO: #TN: Add correctness check of cell value!

        if new_cell != self.cell:
            # Only update cell if necessary
            self._update_cell(deepcopy(self.cell), new_cell, cb)
        else:
            # No update necessary
            if cb:
                async.DelayedCall(0, cb, value=new_cell, status=True)

    def _update_health(self, old_health, new_health, cb):
        self._update(old_health, new_health, self.cell, self.cell, cb)

    def _update_cell(self, old_cell, new_cell, cb):
        self._update(self.healthy, self.healthy, old_cell, new_cell, cb)

    def _update(self, old_health, new_health, old_cell, new_cell, cb):
        """
        Updates node values.
        """
        self.healthy = new_health
        self.cell = new_cell

        self._remove_yes_index(old_health, old_cell)

        self._add_yes_index(new_health, new_cell)

        new_value = {"healthy": new_health, "cell": new_cell}
        self.node.storage.set(prefix="nodeHealth", key=self.node.id, value=new_value, cb=CalvinCB(self._set_storage_cb))

        if cb:
            async.DelayedCall(0, cb, value=new_value, status=True)

    def _remove_yes_index(self, old_health, old_cell):
        """
        Removes old indexes.
        """
        print "In remove_yes_index with old health,cell: " + str(old_health) + "," + str(old_cell)
        if old_health == "yes":
            old_data = AttributeResolver(self._format_attribute(old_health, old_cell))
            for old_index in old_data.get_indexed_public():
                self.node.storage.remove_index(index=old_index, value=self.node.id, root_prefix_level=2,
                                               cb=CalvinCB(self._remove_index_storage_cb))
        else:
            print "Old health is not yes, nothing done in remove yes index"

    def _add_yes_index(self, new_health, new_cell):
        """
        Adds new indexes.
        """
        print "In add_yes_index with new health,cell: " + str(new_health) + "," + str(new_cell)
        if new_health == "yes":
            new_data = AttributeResolver(self._format_attribute(new_health, new_cell))
            for new_index in new_data.get_indexed_public():
                self.node.storage.add_index(index=new_index, value=self.node.id, root_prefix_level=2,
                                            cb=CalvinCB(self._add_index_storage_cb))
        else:
            print "New value is not yes, nothing done in add yes index"

    def _add_index_storage_cb(self, value):
        print "Got to add index cb with result " + str(value)

    def _remove_index_storage_cb(self, value):
        print "Got to remove index cb with result " + str(value)

    def _set_storage_cb(self, key, value):
        _log.critical("\nVM: node health set to " + str(self.healthy))
        print "Got to set storage cb with result " + str(value)
        self.node.control.log_health_new(self.healthy)
        print "VM: send new health-value to log"

    def _migrate_if_unhealthy(self):
        # TODO: Add some increase in nbr of actors migrated each time runtime is unhealthy?
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

    @staticmethod
    def _format_attribute(healthy_value, cell_value):
        return {"indexed_public": {"health": {"healthy": healthy_value, "cell": cell_value}}}
