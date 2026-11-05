import logging
from copy import copy
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QUndoCommand
from .canvas.flowgraph import FlowgraphScene
from .canvas.block import Block
from ...core.base import Element

log = logging.getLogger(f"grc.application.{__name__}")


# Movement, rotation, enable/disable/bypass, bus ports,
# change params, toggle type.
# Basically anything that's not cut/paste or new/delete
class ChangeStateAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene):
        QUndoCommand.__init__(self)
        log.debug("init ChangeState")
        self.old_states = []
        self.old_params = []
        self.new_states = []
        self.new_params = []
        self.scene = scene
        self.g_blocks = scene.selected_blocks()
        for g_block in self.g_blocks:
            self.old_states.append(copy(g_block.core.states))
            self.new_states.append(copy(g_block.core.states))
            self.old_params.append(copy(g_block.core.params))
            self.new_params.append(copy(g_block.core.params))

    def redo(self):
        for i in range(len(self.g_blocks)):
            self.g_blocks[i].set_states(self.new_states[i])
            self.g_blocks[i].core.params = (self.new_params[i])
        self.scene.update()

    def undo(self):
        for i in range(len(self.g_blocks)):
            self.g_blocks[i].set_states(self.old_states[i])
            self.g_blocks[i].params = (self.old_params[i])
        self.scene.update()


class RotateAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, delta_angle: int):
        QUndoCommand.__init__(self)
        log.debug("init RotateAction")
        self.setText('Rotate')
        self.g_blocks = scene.selected_blocks()
        self.scene = scene
        self.delta_angle = delta_angle

    def redo(self):
        self.scene.rotate_selected(self.delta_angle)

    def undo(self):
        self.scene.rotate_selected(-self.delta_angle)


class MoveAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, diff: QPointF):
        QUndoCommand.__init__(self)
        log.debug("init MoveAction")
        self.setText('Move')
        self.g_blocks = scene.selected_blocks()
        self.scene = scene
        self.x = diff.x()
        self.y = diff.y()
        for block in self.g_blocks:
            block.core.states["coordinate"] = (block.x(), block.y())
        self.first = True

    # redo() is called when the MoveAction is first created.
    # At this point, the item is already at the correct position.
    # Therefore, do nothing.
    def redo(self):
        if self.first:
            self.first = False
            return
        for g_block in self.g_blocks:
            g_block.move(self.x, self.y)
        self.scene.update()

    def undo(self):
        for g_block in self.g_blocks:
            g_block.move(-self.x, -self.y)
        self.scene.update()


class AlignAction(QUndoCommand):
    """Align the selected blocks to a common edge or centre line."""

    EDGES = ("top", "middle", "bottom", "left", "center", "right")

    def __init__(self, scene: FlowgraphScene, g_blocks, edge):
        QUndoCommand.__init__(self)
        log.debug(f"init AlignAction ({edge})")
        self.setText(f"Align {edge}")
        self.scene = scene
        self.g_blocks = list(g_blocks)
        self.old_pos = [(b.x(), b.y()) for b in self.g_blocks]
        self.new_pos = [self._target(b, edge) for b in self.g_blocks]

    def _target(self, block, edge):
        blocks = self.g_blocks
        x, y = block.x(), block.y()
        if edge == "top":
            y = min(b.y() for b in blocks)
        elif edge == "bottom":
            y = max(b.y() + b.height for b in blocks) - block.height
        elif edge == "middle":
            mid = sum(b.y() + b.height / 2 for b in blocks) / len(blocks)
            y = mid - block.height / 2
        elif edge == "left":
            x = min(b.x() for b in blocks)
        elif edge == "right":
            x = max(b.x() + b.width for b in blocks) - block.width
        elif edge == "center":
            mid = sum(b.x() + b.width / 2 for b in blocks) / len(blocks)
            x = mid - block.width / 2
        return (x, y)

    def has_effect(self):
        return any(abs(o[0] - n[0]) > 0.5 or abs(o[1] - n[1]) > 0.5
                   for o, n in zip(self.old_pos, self.new_pos))

    def _apply(self, positions):
        for g_block, (x, y) in zip(self.g_blocks, positions):
            g_block.setPos(x, y)
            g_block.core.states["coordinate"] = (g_block.x(), g_block.y())
        self.scene.update()

    def redo(self):
        self._apply(self.new_pos)

    def undo(self):
        self._apply(self.old_pos)


class EnableAction(ChangeStateAction):
    def __init__(self, scene: FlowgraphScene):
        ChangeStateAction.__init__(self, scene)
        log.debug("init EnableAction")
        self.setText('Enable')
        for i in range(len(self.g_blocks)):
            self.new_states[i]['state'] = 'enabled'


class DisableAction(ChangeStateAction):
    def __init__(self, scene: FlowgraphScene):
        ChangeStateAction.__init__(self, scene)
        log.debug("init DisableAction")
        self.setText('Disable')
        for i in range(len(self.g_blocks)):
            self.new_states[i]['state'] = 'disabled'


class BypassAction(ChangeStateAction):
    def __init__(self, scene: FlowgraphScene):
        ChangeStateAction.__init__(self, scene)
        log.debug("init BypassAction")
        self.setText('Bypass')
        for i in range(len(self.g_blocks)):
            self.new_states[i]['state'] = 'bypassed'


# Change properties
# This can only be performed on one block at a time
class BlockPropsChangeAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, c_block: Block):
        QUndoCommand.__init__(self)
        log.debug("init BlockPropsChangeAction")
        self.setText(f'{c_block.name} block: Change properties')
        self.scene = scene
        self.c_block = c_block
        self.old_data = copy(c_block.old_data)
        self.new_data = copy(c_block.export_data())
        self.first = True

    def redo(self):
        if self.first:
            self.first = False
            return
        try:
            name = self.new_data['name']
        except KeyError:
            name = self.new_data['parameters']['id']

        self.c_block.import_data(name, self.new_data['states'], self.new_data['parameters'])
        self.c_block.rewrite()
        self.c_block.validate()
        self.c_block.gui.create_shapes_and_labels()
        self.scene.update()

    def undo(self):
        try:
            name = self.old_data['name']
        except KeyError:
            name = self.old_data['parameters']['id']

        self.c_block.import_data(name, self.old_data['states'], self.old_data['parameters'])
        self.c_block.rewrite()
        self.c_block.validate()
        self.c_block.gui.create_shapes_and_labels()
        self.scene.update()


class BussifyAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, direction: str):  # direction is either "sink" or "source"
        QUndoCommand.__init__(self)
        log.debug("init BussifyAction")
        self.setText(f'Toggle bus {direction}')
        self.scene = scene
        self.direction = direction
        self.g_blocks = scene.selected_blocks()

    def bussify(self):
        for g_block in self.g_blocks:
            g_block.core.bussify(self.direction)
        self.scene.update()

    def redo(self):
        self.bussify()

    def undo(self):
        self.bussify()


# Blocks and connections
class NewElementAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, element: Element):
        QUndoCommand.__init__(self)
        log.debug("init NewElementAction")
        self.setText('New')
        self.scene = scene
        self.element = element
        self.first = True

    def redo(self):
        if self.first:
            self.first = False
            return

        if self.element.is_block:
            self.scene.core.blocks.append(self.element)
        elif self.element.is_connection:
            self.scene.core.connections.add(self.element)

        self.scene.addItem(self.element.gui)
        self.scene.update()

    def undo(self):
        self.scene.remove_element(self.element.gui)
        self.scene.update()


class AutoconnectAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene, port_pairs):
        QUndoCommand.__init__(self)
        log.debug("init AutoconnectAction")
        self.setText('Autoconnect')
        self.scene = scene
        self.port_pairs = port_pairs
        self.connections = None

    def redo(self):
        if self.connections is None:
            self.connections = []
            for source, sink in self.port_pairs:
                try:
                    self.connections.append(self.scene.core.connect(source, sink))
                except Exception as e:
                    log.warning(f"Autoconnect: could not connect {source} to {sink}: {e}")
        else:
            for con in self.connections:
                self.scene.core.connections.add(con)
        for con in self.connections:
            self.scene.addItem(con.gui)
        self.scene.update()

    def undo(self):
        for con in self.connections:
            self.scene.remove_element(con.gui)
        self.scene.update()


class DeleteElementAction(QUndoCommand):
    def __init__(self, scene: FlowgraphScene):
        QUndoCommand.__init__(self)
        log.debug("init DeleteElementAction")
        self.setText('Delete')
        self.scene = scene
        self.g_connections = scene.selected_connections()
        g_blocks = scene.selected_blocks()
        self.g_blocks = []
        for block in g_blocks:
            if not (block.core is scene.core.options_block):
                self.g_blocks = self.g_blocks + [block]
                for conn in block.core.connections():
                    self.g_connections = self.g_connections + [conn.gui]

    def redo(self):
        for con in self.g_connections:
            self.scene.remove_element(con)
        for block in self.g_blocks:
            self.scene.remove_element(block)
        self.scene.update()

    def undo(self):
        for block in self.g_blocks:
            self.scene.core.blocks.append(block.core)
            self.scene.addItem(block)
        for con in self.g_connections:
            self.scene.core.connections.add(con.core)
            self.scene.addItem(con)
        self.scene.update()
