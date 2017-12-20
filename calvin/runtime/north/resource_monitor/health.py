# -*- coding: utf-8 -*-

from calvin.runtime.south.plugins.async import async
from calvin.utilities.calvinlogger import get_logger
from calvin.utilities.calvin_callback import CalvinCB
from calvin.utilities.attribute_resolver import AttributeResolver
from copy import deepcopy
import json

_log = get_logger(__name__)


class HealthMonitor(object):
    def __init__(self, node):
        self.node = node
        self._value_range = {'min': 0.0, 'max': 1.0}
        self._threshold = 0.75
        self._healthy = None
        self._cells = []
        self._type = None
        self._imei_cells = {}

        self._load_initial_attributes()
        self._set_initial_health()

    def _load_initial_attributes(self):
        node_attributes = self.node.attributes.get_indexed_public_with_keys()
        if node_attributes:
            if 'health.cell' in node_attributes.keys():
                cells_to_add = json.loads(node_attributes['health.cell'])
                if isinstance(cells_to_add, list):
                    for cell_to_add in cells_to_add:
                        self._cells.append(str(cell_to_add))
                else:
                    self._cells.append(str(cells_to_add))
            if 'health.type' in node_attributes.keys():
                self._type = node_attributes['health.type']

    def _set_initial_health(self):
        self.set_health(self._value_range['max'])

    def set_imei_cells(self, imei_cell_list, cb=None):
        # TODO: #TN: Add correctness check of imei_cell_list!

        for imei_cell in imei_cell_list:
            imei = imei_cell['imei']
            cell = imei_cell['cell']
            self._imei_cells[imei] = cell

        print "Stored IMEIs with corresponding cell ids: " + str(self._imei_cells)

        if cb:
            async.DelayedCall(0, cb, value="OK", status=True)

        self._migrate_foreign_cells()

    def set_health(self, health_value, cb=None):
        """
        Sets the health of a node. health_value should be a float between 0 (worst) and 1 (best).
        This value is then stored either as "good" or "bad" according to the threshold.
        If the health value is "bad", an actor migration is triggered.
        """

        if not self._correct_health_value(health_value, cb):
            return

        # TODO: #TN: Add hysteresis interval to avoid oscillations?
        if float(health_value) < self._threshold:
            new_healthy = "no"
        else:
            new_healthy = "yes"

        if new_healthy != self._healthy:
            # Only update health if necessary
            self._update_health(deepcopy(self._healthy), new_healthy, cb)
        else:
            # No update necessary
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=True)

        self.node.control.log_health_new(self._healthy)
        print "VM: send new health-value to log"
        self._migrate_if_unhealthy()

    def _update_health(self, old_health, new_health, cb):
        """
        Updates node values.
        """
        self._healthy = new_health

        if self._cells:
            for cell in self._cells:
                self._remove_yes_index(old_health, cell)
                self._add_yes_index(new_health, cell)
        else:
            self._remove_yes_index(old_health)
            self._add_yes_index(new_health)

        new_value = {"healthy": new_health, "cell": self._cells}
        self.node.storage.set(prefix="nodeHealth", key=self.node.id, value=new_value, cb=CalvinCB(self._set_storage_cb))

        if cb:
            async.DelayedCall(0, cb, value=new_value, status=True)

    def _remove_yes_index(self, old_health, old_cell=None):
        """
        Removes old indexes.
        """
        print "In remove_yes_index with old health,cell: " + str(old_health) + "," + str(old_cell)
        if old_health == "yes":
            old_data = AttributeResolver(self._format_attribute(old_health, old_cell))
            for old_index in old_data.get_indexed_public():
                print "old index is " + str(old_index)
                self.node.storage.remove_index(index=old_index, value=self.node.id, root_prefix_level=2,
                                               cb=CalvinCB(self._remove_index_storage_cb))
        else:
            print "Old health is not yes, nothing done in remove yes index"

    def _add_yes_index(self, new_health, new_cell=None):
        """
        Adds new indexes.
        """
        print "In add_yes_index with new health,cell: " + str(new_health) + "," + str(new_cell)
        if new_health == "yes":
            new_data = AttributeResolver(self._format_attribute(new_health, new_cell))
            for new_index in new_data.get_indexed_public():
                print "new index is " + str(new_index)
                self.node.storage.add_index(index=new_index, value=self.node.id, root_prefix_level=2,
                                            cb=CalvinCB(self._add_index_storage_cb))
        else:
            print "New value is not yes, nothing done in add yes index"

    def _add_index_storage_cb(self, value):
        print "Got to add index cb with result " + str(value)

    def _remove_index_storage_cb(self, value):
        print "Got to remove index cb with result " + str(value)

    def _set_storage_cb(self, key, value):
        _log.critical("\nVM: node health set to " + str(self._healthy))
        print "Got to set storage cb with result " + str(value)

    def _migrate_if_unhealthy(self):
        # TODO: Add some increase in nbr of actors migrated each time runtime is unhealthy?
        if self._healthy == "no":
            print "Migration triggered!"
            if self._cells:
                # TODO: Specify random cell instead of first in list?
                self.node.am.health_triggered_migration(self._cells[0])
            else:
                self.node.am.health_triggered_migration()

    def _migrate_foreign_cells(self):
        foreign_imei_cells = [{'imei': imei, 'cell': cell}
                              for imei, cell in self._imei_cells.iteritems() if self._is_foreign(cell)]

        if foreign_imei_cells:
            print "Foreign cells: " + str(foreign_imei_cells)
            self.node.am.cell_triggered_migration(foreign_imei_cells)
        else:
            print "No actors to migrate from latest cell changes"

    def _is_foreign(self, cell):
        if self._type == "dc":
            return True
        else:
            return cell not in self._cells

    def _correct_health_value(self, health_value, cb):
        if not self._is_float(health_value):
            _log.critical("#TN: Invalid health type: %s" % str(type(health_value)))
            if cb:
                async.DelayedCall(0, cb, value=health_value, status=False)
            return False

        if float(health_value) < self._value_range['min'] or float(health_value) > self._value_range['max']:
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

    def _format_attribute(self, healthy_value, cell_value):
        if self._type and cell_value:
            return {"indexed_public": {"health": {"type": self._type, "healthy": healthy_value, "cell": cell_value}}}
        elif cell_value:
            return {"indexed_public": {"health": {"healthy": healthy_value, "cell": cell_value}}}
        elif self._type:
            return {"indexed_public": {"health": {"type": self._type, "healthy": healthy_value}}}

    def stop(self):
        self.node.storage.delete(prefix="nodeHealth", key=self.node.id, cb=None)
        if self._cells:
            for cell in self._cells:
                self._remove_yes_index(self._healthy, cell)
        else:
            self._remove_yes_index(self._healthy)
