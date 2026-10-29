"""Qt desktop workbench. No machine communication happens in this module.

Everything editable lives in EditorSession; the scene is deliberately disposable.
Qt is optional, so CLI users aren't asked to install half a desktop.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import tempfile

from .design import DesignDocument, design_from_svg, generate_design_plan
from .editor import EditorSession, as_design, snap_coordinate
from .dst import export_dst, inspect_dst, read_dst_events
from .model import Op, Point, StitchSettings
from .preflight import inspect_plan
from .diagnostics import inspect_design
from .project import load_project, save_project

# Imported only by the desktop entry point. Headless conversion has no Qt dependency.
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QBrush)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDockWidget, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QAbstractItemView, QMenu,
    QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

PX = 4.0   # scene units per millimetre; view zoom is independent
PREVIEW_WINDOW = 3000  # bounded repaint even for extremely long stitch plans


class CanvasItem(QGraphicsPathItem):
    def __init__(self, object_id: str, path: QPainterPath, colour: str, on_move):
        super().__init__(path)
        self.object_id = object_id
        self._on_move = on_move
        self.setPen(QPen(QColor(colour), 1.9))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlags(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(10)

    def boundingRect(self):
        return super().boundingRect().adjusted(-5, -5, 5, 5)

    def shape(self):
        # Hairline paths are miserable to select, particularly on a laptop.
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path()).united(self.path())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        delta = self.pos()
        if abs(delta.x()) > 0.01 or abs(delta.y()) > 0.01:
            dx, dy, oid = delta.x() / PX, delta.y() / PX, self.object_id
            # Do not destroy this graphics item from inside its own release event.
            QTimer.singleShot(0, lambda: self._on_move(oid, dx, dy))


class NodeHandle(QGraphicsEllipseItem):
    """A draggable vertex. Commit after Qt finishes its mouse event."""

    def __init__(self, object_id, contour, vertex, point, on_move, on_insert, on_delete):
        super().__init__(-4.5, -4.5, 9, 9)
        self.object_id = object_id
        self.contour = contour
        self.vertex = vertex
        self._on_move = on_move
        self._on_insert = on_insert
        self._on_delete = on_delete
        self.setPos(point.x * PX, point.y * PX)
        self.setPen(QPen(QColor('#193f5e'), 1.5))
        self.setBrush(QBrush(QColor('#f8fcff')))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(35)
        self._original = self.pos()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if (self.pos() - self._original).manhattanLength() > 0.01:
            oid, contour, vertex = self.object_id, self.contour, self.vertex
            x, y = self.pos().x() / PX, self.pos().y() / PX
            QTimer.singleShot(0, lambda: self._on_move(oid, contour, vertex, x, y))

    def contextMenuEvent(self, event):
        menu = QMenu()
        insert = menu.addAction('Insert midpoint after this node')
        delete = menu.addAction('Delete this node')
        action = menu.exec(event.screenPos())
        oid, contour, vertex = self.object_id, self.contour, self.vertex
        if action == insert:
            QTimer.singleShot(0, lambda: self._on_insert(oid, contour, vertex))
        elif action == delete:
            QTimer.singleShot(0, lambda: self._on_delete(oid, contour, vertex))


class CurveHandle(QGraphicsEllipseItem):
    """A cubic anchor or handle. The source curve remains a curve."""

    def __init__(self, oid, path_index, segment_index, point_index, point, on_move):
        super().__init__(-4, -4, 8, 8)
        self._ident = (oid, path_index, segment_index, point_index)
        self._on_move = on_move
        self.setPos(point.x * PX, point.y * PX)
        self.setPen(QPen(QColor('#653b7f'), 1.5))
        self.setBrush(QBrush(QColor('#fff0d1') if point_index in (0, 3) else QColor('#ceb6e8')))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(36)
        self._original = self.pos()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if (self.pos() - self._original).manhattanLength() > 0.01:
            oid, path_index, segment_index, point_index = self._ident
            x, y = self.pos().x() / PX, self.pos().y() / PX
            QTimer.singleShot(0, lambda: self._on_move(
                oid, path_index, segment_index, point_index, x, y))


class HoopView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor('#dce2e7'))
        self.draw_callback = None
        self.hover_callback = None
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if self.draw_callback is not None and event.button() == Qt.MouseButton.LeftButton:
            p = self.mapToScene(event.position().toPoint())
            self.draw_callback(p.x() / PX, p.y() / PX)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.hover_callback is not None:
            p = self.mapToScene(event.position().toPoint())
            self.hover_callback(p.x() / PX, p.y() / PX)
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scale(1.15 if event.angleDelta().y() > 0 else 1 / 1.15,
                       1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)


class StudioWindow(QMainWindow):
    def __init__(self, path: str | Path | None = None):
        super().__init__()
        self.editor: EditorSession | None = None
        self.project_path: Path | None = None
        self.active_id: str | None = None
        self._refreshing = False
        self._plan = None
        self._preview_position = 0
        self._scene_items: dict[str, CanvasItem] = {}
        self._node_handles: list[NodeHandle | CurveHandle] = []
        self._curve_guides = []
        self._active_contour = 0
        self._contour_owner = None
        self._draw_points: list[Point] = []
        self._draw_hover: Point | None = None
        self._draw_preview = None
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._advance)
        self.setWindowTitle('TABARC Embroidery Studio')
        self.resize(1250, 800)
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._selection_from_scene)
        self.view = HoopView(self)
        self.view.setScene(self.scene)
        self.setCentralWidget(self.view)
        self._build_docks()
        self._build_actions()
        self.statusBar().showMessage('Open a .tbes project or an SVG to begin')
        if path is not None:
            self.open_path(Path(path))

    def _build_docks(self):
        left = QDockWidget('Objects · sewing order', self)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.objects = QListWidget()
        self.objects.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.objects.currentItemChanged.connect(self._selection_from_list)
        self.objects.itemChanged.connect(self._visibility_from_list)
        layout.addWidget(self.objects)
        row = QHBoxLayout()
        up = QPushButton('Move up')
        down = QPushButton('Move down')
        up.clicked.connect(lambda: self._reorder(-1))
        down.clicked.connect(lambda: self._reorder(1))
        row.addWidget(up)
        row.addWidget(down)
        layout.addLayout(row)
        left.setWidget(widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)

        right = QDockWidget('Object properties', self)
        panel = QWidget()
        form = QFormLayout(panel)
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._change_name)
        self.colour_button = QPushButton('Choose thread colour')
        self.colour_button.clicked.connect(self._pick_colour)
        self.visible_box = QCheckBox('Sew this object')
        self.visible_box.toggled.connect(self._change_visibility)
        self.kind_label = QLabel('—')
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(['running', 'tatami'])
        self.kind_combo.currentTextChanged.connect(self._change_kind)
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(['Off', '0.5 mm', '1 mm', '2 mm', '5 mm'])
        self.grid_combo.setCurrentText('1 mm')
        form.addRow('Name', self.name_edit)
        form.addRow('Stitch type', self.kind_label)
        form.addRow('Change stitch type', self.kind_combo)
        form.addRow('Snap to grid', self.grid_combo)
        self.contour_combo = QComboBox()
        self.contour_combo.currentIndexChanged.connect(self._choose_contour)
        form.addRow('Active contour', self.contour_combo)
        form.addRow('Thread', self.colour_button)
        form.addRow('', self.visible_box)
        self.fields = {}
        controls = (
            ('stitch_length_mm', 'Stitch length (mm)', 0.1, 12., 2),
            ('row_spacing_mm', 'Fill row spacing (mm)', 0.1, 5., 2),
            ('angle_deg', 'Fill angle (°)', -360., 360., 1),
            ('satin_spacing_mm', 'Satin spacing (mm)', 0.1, 5., 2),
            ('max_satin_width_mm', 'Satin maximum width (mm)', 0.5, 30., 1),
        )
        for key, label, minimum, maximum, decimals in controls:
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setSingleStep(0.1 if decimals == 2 else 1)
            spin.valueChanged.connect(lambda value, field=key: self._change_setting(field, value))
            form.addRow(label, spin)
            self.fields[key] = spin
        right.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right)

        bottom = QDockWidget('Stitch playback', self)
        controls_widget = QWidget()
        row = QHBoxLayout(controls_widget)
        self.play_button = QPushButton('Play')
        self.play_button.clicked.connect(self._toggle_play)
        self.preview_button = QPushButton('Generate preview')
        self.preview_button.clicked.connect(self.generate_preview)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.valueChanged.connect(self._seek)
        self.position_label = QLabel('No stitch plan')
        row.addWidget(self.preview_button)
        row.addWidget(self.play_button)
        row.addWidget(self.timeline, 1)
        row.addWidget(self.position_label)
        bottom.setWidget(controls_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, bottom)

        diagnostics_dock = QDockWidget('Design diagnostics', self)
        diagnostics_widget = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_widget)
        self.diagnostics_button = QPushButton('Inspect design')
        self.diagnostics_button.clicked.connect(self.inspect_objects)
        self.diagnostics_list = QListWidget()
        self.diagnostics_list.itemClicked.connect(self._select_diagnostic)
        diagnostics_layout.addWidget(self.diagnostics_button)
        diagnostics_layout.addWidget(self.diagnostics_list)
        diagnostics_dock.setWidget(diagnostics_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, diagnostics_dock)

    def _action(self, menu, title, handler, shortcut=None):
        action = QAction(title, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    def _build_actions(self):
        files = self.menuBar().addMenu('&File')
        self._action(files, 'Open .tbes / SVG…', self._open_dialog, 'Ctrl+O')
        self._action(files, 'Save', self.save, 'Ctrl+S')
        self._action(files, 'Save as…', self.save_as, 'Ctrl+Shift+S')
        files.addSeparator()
        self._action(files, 'Export DST…', self.export_dst, 'Ctrl+E')
        self._action(files, 'Exit', self.close)
        edit = self.menuBar().addMenu('&Edit')
        self._action(edit, 'Undo', self.undo, 'Ctrl+Z')
        self._action(edit, 'Redo', self.redo, 'Ctrl+Shift+Z')
        edit.addSeparator()
        self.draw_action = self._action(edit, 'Draw running path',
                                        self._set_draw_mode, 'D')
        self.draw_action.setCheckable(True)
        self._action(edit, 'Finish path', self.finish_path, 'Return')
        self._action(edit, 'Cancel path', self.cancel_path, 'Escape')
        self._action(edit, 'Remove last point', self.remove_draw_point, 'Backspace')
        edit.addSeparator()
        self.node_action = self._action(edit, 'Edit path nodes', self._set_node_mode, 'N')
        self.node_action.setCheckable(True)
        self._action(edit, 'Close selected contour', lambda: self._close_selected(True))
        self._action(edit, 'Open selected contour', lambda: self._close_selected(False))
        self._action(edit, 'Remove selected contour', self._remove_selected_contour)
        self._action(edit, 'Group selected contours as fill', self._group_selected)
        view = self.menuBar().addMenu('&View')
        self._action(view, 'Fit hoop', self._fit, 'Ctrl+0')
        self._action(view, 'Generate stitch preview', self.generate_preview, 'F5')
        self._action(view, 'Inspect design warnings', self.inspect_objects, 'F6')

    def _confirm_discard(self) -> bool:
        if (self.editor and self.editor.dirty) or self._draw_points:
            answer = QMessageBox.question(self, 'Unsaved changes',
                       'Discard the current unsaved changes?',
                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                       QMessageBox.StandardButton.No)
            return answer == QMessageBox.StandardButton.Yes
        return True

    def _open_dialog(self):
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Open embroidery design', '',
            'Embroidery project (*.tbes);;SVG artwork (*.svg)')
        if filename:
            self.open_path(Path(filename), check_dirty=False)

    def open_path(self, path: Path, *, check_dirty=True) -> bool:
        if check_dirty and not self._confirm_discard():
            return False
        try:
            data = path.read_bytes()
            if path.suffix.lower() == '.tbes':
                doc, source = load_project(data)
                project_path = path
            elif path.suffix.lower() == '.svg':
                from .svg_import import import_svg
                imported = import_svg(data)
                # Separate paths are individually selectable. Closed shapes stay
                # running until deliberately given a fill stitch type.
                assignments = {'objects': [
                    {'id': f'path-{i+1}', 'name': f'{path.stem} {i+1}',
                     'kind': 'running', 'stroke_indices': [i]}
                    for i in range(len(imported.strokes))]}
                doc, source = design_from_svg(data, assignments), data
                project_path = None
            else:
                raise ValueError('Open a .tbes project or supported SVG file')
            new_editor = EditorSession(as_design(doc), source)
            if project_path is None:
                new_editor.mark_unsaved()
        except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
            QMessageBox.critical(self, 'Cannot open design', str(exc))
            return False
        self.editor, self.project_path = new_editor, project_path
        self._draw_points.clear()
        self._draw_hover = None
        self.active_id = None
        self._refresh_scene(fit=True)
        self.statusBar().showMessage(f'Opened {path.name}')
        return True

    def _fit(self):
        if self.scene.items():
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _refresh_scene(self, *, fit=False):
        self._timer.stop()
        self.play_button.setText('Play')
        self._plan = None
        self.timeline.setRange(0, 0)
        self.position_label.setText('No stitch plan')
        self._refreshing = True
        self.scene.clear()
        self._draw_preview = None
        self._scene_items = {}
        self._node_handles = []
        self._curve_guides = []
        self.diagnostics_list.clear()  # Old warnings describe old geometry.
        self.objects.clear()
        if self.editor:
            doc = self.editor.design
            if self.active_id not in {obj.object_id for obj in doc.objects}:
                # Undo/grouping can remove the selected object. The list and
                # properties must never keep a dangling selection.
                self.active_id = None
            width, height = doc.width_mm * PX, doc.height_mm * PX
            self.scene.setSceneRect(-20, -20, width + 40, height + 40)
            self.scene.addRect(0, 0, width, height, QPen(QColor('#4b5966'), 2),
                               QBrush(QColor('#ffffff')))
            for mm in range(10, min(int(doc.width_mm), 1000), 10):
                self.scene.addLine(mm * PX, 0, mm * PX, height, QPen(QColor('#eff0f2')))
            for mm in range(10, min(int(doc.height_mm), 1000), 10):
                self.scene.addLine(0, mm * PX, width, mm * PX, QPen(QColor('#eff0f2')))
            for obj in doc.objects:
                line = QListWidgetItem(f'{obj.name}  ·  {obj.kind}')
                line.setData(Qt.ItemDataRole.UserRole, obj.object_id)
                line.setFlags(line.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                line.setCheckState(Qt.CheckState.Checked if obj.visible else Qt.CheckState.Unchecked)
                line.setForeground(QColor(obj.thread_hex))
                self.objects.addItem(line)
                if obj.kind in {'trim', 'stop', 'colour_change'}:
                    continue
                path = QPainterPath()
                for stroke in obj.strokes:
                    if not stroke.points:
                        continue
                    path.moveTo(stroke.points[0].x * PX, stroke.points[0].y * PX)
                    for p in stroke.points[1:]:
                        path.lineTo(p.x * PX, p.y * PX)
                    if stroke.closed:
                        path.closeSubpath()
                for curve in obj.curve_paths:
                    if curve.segments:
                        first = curve.segments[0]
                        path.moveTo(first.p0.x * PX, first.p0.y * PX)
                        for seg in curve.segments:
                            path.cubicTo(seg.p1.x * PX, seg.p1.y * PX,
                                         seg.p2.x * PX, seg.p2.y * PX,
                                         seg.p3.x * PX, seg.p3.y * PX)
                        if curve.closed:
                            path.closeSubpath()
                if not path.isEmpty():
                    item = CanvasItem(obj.object_id, path, obj.thread_hex, self._move_object)
                    item.setVisible(obj.visible)
                    self.scene.addItem(item)
                    self._scene_items[obj.object_id] = item
            self._select(self.active_id)
            self._redraw_path_preview()
            if fit:
                self._fit()
            if (hasattr(self, 'draw_action') and self.draw_action.isChecked()) or (
                    hasattr(self, 'node_action') and self.node_action.isChecked()):
                for item in self._scene_items.values():
                    item.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, False)
        self._refreshing = False
        self._refresh_properties()
        self._update_title()

    def _select(self, object_id: str | None):
        if object_id != self.active_id:
            self._active_contour = 0
            self._contour_owner = object_id
        self.active_id = object_id
        for i in range(self.objects.count()):
            item = self.objects.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == object_id:
                self.objects.setCurrentRow(i)
                break
        if object_id is None:
            self.objects.clearSelection()
            self.objects.setCurrentRow(-1)
        for oid, graphics in self._scene_items.items():
            graphics.setSelected(oid == object_id)
        self._redraw_nodes()

    def _selection_from_list(self, current, previous):
        if self._refreshing:
            return
        new_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if new_id != self.active_id:
            self._active_contour = 0
            self._contour_owner = new_id
        self.active_id = new_id
        self._refreshing = True
        for oid, graphics in self._scene_items.items():
            graphics.setSelected(oid == self.active_id)
        self._refreshing = False
        self._redraw_nodes()
        self._refresh_properties()

    def _selection_from_scene(self):
        if self._refreshing:
            return
        selected = [item for item in self.scene.selectedItems() if isinstance(item, CanvasItem)]
        self._refreshing = True
        self._select(selected[-1].object_id if selected else None)
        self._refreshing = False
        self._redraw_nodes()
        self._refresh_properties()

    def _refresh_properties(self):
        self._refreshing = True
        obj = self.editor.object(self.active_id) if self.editor and self.active_id else None
        if self._contour_owner != self.active_id:
            self._active_contour = 0
            self._contour_owner = self.active_id
        contours = len(obj.strokes) if obj and obj.kind in {'running', 'tatami'} else 0
        self.contour_combo.blockSignals(True)
        self.contour_combo.clear()
        for i in range(contours):
            self.contour_combo.addItem(f'Contour {i + 1}', i)
        self._active_contour = min(self._active_contour, max(0, contours - 1))
        if contours:
            self.contour_combo.setCurrentIndex(self._active_contour)
        self.contour_combo.setEnabled(contours > 1)
        self.contour_combo.blockSignals(False)
        self.name_edit.setText(obj.name if obj else '')
        self.kind_label.setText(obj.kind if obj else '—')
        self.kind_combo.setEnabled(bool(obj and obj.kind in {'running', 'tatami'}))
        if obj and obj.kind in {'running', 'tatami'}:
            self.kind_combo.setCurrentText(obj.kind)
        self.visible_box.setChecked(obj.visible if obj else False)
        self.colour_button.setText(obj.thread_hex if obj else 'Choose thread colour')
        if obj:
            self.colour_button.setStyleSheet(f'color: {obj.thread_hex}; font-weight: bold;')
        for key, field in self.fields.items():
            field.setValue(getattr(obj.settings, key) if obj else 0)
            field.setEnabled(bool(obj and obj.kind in {'running', 'satin', 'tatami'} and
                         key in ({'running': {'stitch_length_mm'},
                                  'satin': {'satin_spacing_mm', 'max_satin_width_mm'},
                                  'tatami': {'stitch_length_mm', 'row_spacing_mm', 'angle_deg'}}
                                 .get(obj.kind, set()))))
        for control in (self.name_edit, self.colour_button, self.visible_box):
            control.setEnabled(obj is not None)
        self._refreshing = False

    def _change(self, **changes):
        if not self._refreshing and self.editor and self.active_id:
            try:
                self.editor.change(self.active_id, **changes)
                self._refresh_scene()
            except ValueError as exc:
                QMessageBox.warning(self, 'Invalid setting', str(exc))
                self._refresh_properties()

    def _change_kind(self, kind):
        if self._refreshing or not self.editor or not self.active_id:
            return
        try:
            self.editor.set_stitch_kind(self.active_id, kind)
            self._refresh_scene()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot change stitch type', str(exc))
            self._refresh_properties()

    def _choose_contour(self, index):
        if self._refreshing or index < 0:
            return
        self._active_contour = index
        self._redraw_nodes()

    def _redraw_nodes(self):
        for handle in self._node_handles:
            self.scene.removeItem(handle)
        for guide in self._curve_guides:
            self.scene.removeItem(guide)
        self._node_handles.clear()
        self._curve_guides.clear()
        if not (self.editor and self.active_id and self.node_action.isChecked()):
            return
        obj = self.editor.object(self.active_id)
        if obj.kind in {'running', 'tatami'} and not obj.curve_paths:
            if self._active_contour >= len(obj.strokes):
                self._active_contour = 0
            stroke = obj.strokes[self._active_contour]
            for vertex, point in enumerate(stroke.points):
                handle = NodeHandle(obj.object_id, self._active_contour, vertex, point,
                                    self._move_node, self._insert_node, self._delete_node)
                self.scene.addItem(handle)
                self._node_handles.append(handle)
        elif obj.kind == 'reference' and obj.curve_paths:
            # Display the original control polygon; the curve itself is never
            # replaced by a rough polyline merely to make editing easier.
            for path_index, path in enumerate(obj.curve_paths):
                for segment_index, seg in enumerate(path.segments):
                    for a, b in ((seg.p0, seg.p1), (seg.p2, seg.p3)):
                        guide = self.scene.addLine(a.x * PX, a.y * PX, b.x * PX, b.y * PX,
                            QPen(QColor('#9b7cae'), 1, Qt.PenStyle.DashLine))
                        guide.setZValue(34)
                        self._curve_guides.append(guide)
                    for index, point in enumerate((seg.p0, seg.p1, seg.p2, seg.p3)):
                        if index == 0 and segment_index > 0 and path.segments[segment_index - 1].p3 == point:
                            continue  # one handle for a shared vertex
                        handle = CurveHandle(obj.object_id, path_index, segment_index,
                                             index, point, self._move_curve_point)
                        self.scene.addItem(handle)
                        self._node_handles.append(handle)
        else:
            self.statusBar().showMessage('This object has no editable nodes')

    def _move_curve_point(self, oid, path_index, segment_index, point_index, x, y):
        self.active_id = oid
        self._node_change('edit_curve_point', oid, path_index, segment_index,
                          point_index, Point(x, y), grid_mm=self._grid())

    def _remove_selected_contour(self):
        if self.editor and self.active_id:
            self._node_change('remove_contour', self.active_id, self._active_contour)

    def inspect_objects(self):
        self.diagnostics_list.clear()
        if not self.editor:
            return
        issues = inspect_design(self.editor.design)
        for issue in issues:
            entry = QListWidgetItem(f'{issue.severity} · {issue.object_id} · '
                                    f'{issue.code}: {issue.message}')
            entry.setData(Qt.ItemDataRole.UserRole, issue.object_id)
            self.diagnostics_list.addItem(entry)
        self.statusBar().showMessage(f'{len(issues)} design observations; '
                                     'check actual stitches before sewing')

    def _select_diagnostic(self, item):
        oid = item.data(Qt.ItemDataRole.UserRole)
        if self.editor and oid in {o.object_id for o in self.editor.design.objects}:
            self._select(oid)
            self._refresh_properties()

    def _set_node_mode(self, checked):
        if checked and self.draw_action.isChecked():
            self.draw_action.setChecked(False)
            self._set_draw_mode(False)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if checked else
                              QGraphicsView.DragMode.RubberBandDrag)
        for item in self._scene_items.values():
            item.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, not checked)
        self._redraw_nodes()
        self.statusBar().showMessage('Drag vertices; right-click a vertex for insert/delete'
                                     if checked else 'Selection mode')

    def _node_change(self, method, *args, **kwargs):
        if not self.editor:
            return
        try:
            getattr(self.editor, method)(*args, **kwargs)
            self._refresh_scene()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot edit contour', str(exc))
            self._refresh_scene()

    def _move_node(self, oid, contour, vertex, x, y):
        self.active_id = oid
        self._node_change('edit_node', oid, contour, vertex, Point(x, y), grid_mm=self._grid())

    def _insert_node(self, oid, contour, vertex):
        self.active_id = oid
        self._node_change('insert_node', oid, contour, vertex)

    def _delete_node(self, oid, contour, vertex):
        self.active_id = oid
        self._node_change('delete_node', oid, contour, vertex)

    def _close_selected(self, closed):
        if self.editor and self.active_id:
            self._node_change('close_contour', self.active_id, self._active_contour, closed=closed)

    def _group_selected(self):
        if not self.editor:
            return
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.objects.selectedItems()]
        if len(ids) < 2:
            QMessageBox.information(self, 'Select contours',
                                    'Ctrl-click two or more closed contour objects in the list.')
            return
        try:
            self.active_id = self.editor.group_fill_contours(ids)
            self._refresh_scene()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot group contours', str(exc))

    def _grid(self):
        label = self.grid_combo.currentText()
        return None if label == 'Off' else float(label.split()[0])

    def _set_draw_mode(self, checked):
        if checked and self.node_action.isChecked():
            self.node_action.setChecked(False)
            self._set_node_mode(False)
        self.view.draw_callback = self._draw_click if checked else None
        self.view.hover_callback = self._draw_hover_at if checked else None
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if checked else
                              QGraphicsView.DragMode.RubberBandDrag)
        for item in self._scene_items.values():
            item.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, not checked)
        self._redraw_nodes()
        if not checked:
            self.cancel_path()
        self.statusBar().showMessage('Click to add points; Enter finishes, Esc cancels'
                                     if checked else 'Selection mode')

    def _draw_click(self, x_mm, y_mm):
        if not self.editor:
            self.statusBar().showMessage('Open a project or SVG before drawing')
            return
        spacing = self._grid()
        if spacing is not None:
            x_mm = snap_coordinate(x_mm, spacing)
            y_mm = snap_coordinate(y_mm, spacing)
        if not 0 <= x_mm <= self.editor.design.width_mm or not 0 <= y_mm <= self.editor.design.height_mm:
            self.statusBar().showMessage('Point is outside the hoop')
            return
        point = Point(x_mm, y_mm)
        if self._draw_points and point == self._draw_points[-1]:
            return
        if len(self._draw_points) >= 5000:
            self.statusBar().showMessage('Path point limit reached')
            return
        self._draw_points.append(point)
        self._redraw_path_preview()
        self.statusBar().showMessage(f'{len(self._draw_points)} points · Enter to finish')

    def _draw_hover_at(self, x_mm, y_mm):
        if not self._draw_points:
            return
        spacing = self._grid()
        if spacing is not None:
            x_mm = snap_coordinate(x_mm, spacing)
            y_mm = snap_coordinate(y_mm, spacing)
        point = Point(x_mm, y_mm)
        if point != self._draw_hover:
            self._draw_hover = point
            self._redraw_path_preview()

    def _redraw_path_preview(self):
        if self._draw_preview is not None:
            self.scene.removeItem(self._draw_preview)
            self._draw_preview = None
        if not self._draw_points:
            return
        path = QPainterPath()
        path.moveTo(self._draw_points[0].x * PX, self._draw_points[0].y * PX)
        for point in self._draw_points[1:]:
            path.lineTo(point.x * PX, point.y * PX)
        if self._draw_hover is not None:
            path.lineTo(self._draw_hover.x * PX, self._draw_hover.y * PX)
        pen = QPen(QColor('#2563a8'), 2, Qt.PenStyle.DashLine)
        self._draw_preview = self.scene.addPath(path, pen)
        self._draw_preview.setZValue(30)

    def finish_path(self):
        if not self.editor or not self._draw_points:
            return False
        try:
            ident = self.editor.add_running_path(self._draw_points)
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot finish path', str(exc))
            return False
        self._draw_points.clear()
        self._draw_hover = None
        self.active_id = ident
        self._refresh_scene()
        self.statusBar().showMessage(f'Added {ident}; save the project to keep it')
        return True

    def cancel_path(self):
        self._draw_points.clear()
        self._draw_hover = None
        self._redraw_path_preview()

    def remove_draw_point(self):
        if self._draw_points:
            self._draw_points.pop()
            self._draw_hover = None
            self._redraw_path_preview()

    def _change_name(self):
        self._change(name=self.name_edit.text())

    def _pick_colour(self):
        if not self.editor or not self.active_id:
            return
        picked = QColorDialog.getColor(QColor(self.editor.object(self.active_id).thread_hex), self)
        if picked.isValid():
            self._change(thread_hex=picked.name().upper())

    def _change_visibility(self, state):
        self._change(visible=bool(state))

    def _visibility_from_list(self, item):
        if self._refreshing or not self.editor:
            return
        self.active_id = item.data(Qt.ItemDataRole.UserRole)
        self._change(visible=item.checkState() == Qt.CheckState.Checked)

    def _change_setting(self, key, value):
        if self._refreshing or not self.editor or not self.active_id:
            return
        obj = self.editor.object(self.active_id)
        self._change(settings=replace(obj.settings, **{key: value}))

    def _move_object(self, object_id, dx, dy):
        if not self.editor:
            return
        try:
            self.editor.move(object_id, dx, dy, grid_mm=self._grid())
            self.active_id = object_id
            self._refresh_scene()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot move object', str(exc))
            self._refresh_scene()

    def _reorder(self, offset):
        if not self.editor or not self.active_id:
            return
        index = next(i for i, o in enumerate(self.editor.design.objects) if o.object_id == self.active_id)
        destination = index + offset
        if 0 <= destination < len(self.editor.design.objects):
            self.editor.reorder(self.active_id, destination)
            self._refresh_scene()

    def undo(self):
        if self._draw_points:
            self.remove_draw_point()
            return
        if self.editor and self.editor.undo():
            self._refresh_scene()

    def redo(self):
        if self.editor and self.editor.redo():
            self._refresh_scene()

    def _update_title(self):
        name = self.project_path.name if self.project_path else 'Untitled'
        marker = ' *' if self.editor and self.editor.dirty else ''
        self.setWindowTitle(f'{name}{marker} — TABARC Embroidery Studio 0.10.0')

    def save(self):
        if not self.editor:
            return False
        if self.project_path is None:
            return self.save_as()
        try:
            data = save_project(self.editor.design, self.editor.source)
            # Replace only after a complete write. Interrupted saves should not
            # eat the last good project. That would be a fairly grim feature.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                        dir=self.project_path.parent, prefix='.tabarc-save-',
                        suffix='.tbes', delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.project_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self.editor.mark_saved()
            self._update_title()
            self.statusBar().showMessage(f'Saved {self.project_path.name}')
            return True
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, 'Save failed', str(exc))
            return False

    def save_as(self):
        if not self.editor:
            return False
        filename, _ = QFileDialog.getSaveFileName(self, 'Save editable design',
                 str(self.project_path or Path('design.tbes')), 'TABARC projects (*.tbes)')
        if not filename:
            return False
        candidate = Path(filename)
        if candidate.suffix.lower() != '.tbes':
            candidate = candidate.with_suffix('.tbes')
        previous = self.project_path
        self.project_path = candidate
        if not self.save():
            self.project_path = previous
            return False
        return True

    def _generate_plan(self):
        if not self.editor:
            raise ValueError('Open a design first')
        return generate_design_plan(self.editor.design)

    def generate_preview(self):
        self._timer.stop()
        self.play_button.setText('Play')
        try:
            self._plan = self._generate_plan()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot generate stitches', str(exc))
            self._plan = None
            return
        self.timeline.setRange(0, len(self._plan.events) - 1)
        self.timeline.setValue(len(self._plan.events) - 1)
        self._seek(self.timeline.value())

    def _seek(self, position):
        if not self._plan:
            return
        self._preview_position = position
        for item in list(self.scene.items()):
            if item.data(0) == 'stitch-preview':
                self.scene.removeItem(item)
        events = self._plan.events
        last = min(position + 1, len(events))
        start = max(0, last - PREVIEW_WINDOW)
        prev = events[start - 1].point_mm if start else None
        if prev is None:
            from .model import Point
            prev = Point(0, 0)
        palette = self._plan.thread_palette or ('#213f68',)
        colour_index = sum(e.opcode == Op.COLOUR_CHANGE for e in events[:start])
        paths = {}
        for event in events[start:last]:
            next_point = event.point_mm
            if event.opcode in (Op.STITCH, Op.JUMP):
                key = 'jump' if event.opcode == Op.JUMP else palette[min(colour_index, len(palette) - 1)]
                path = paths.setdefault(key, QPainterPath())
                path.moveTo(prev.x * PX, prev.y * PX)
                path.lineTo(next_point.x * PX, next_point.y * PX)
            elif event.opcode == Op.COLOUR_CHANGE:
                colour_index += 1
            prev = next_point
        for key, path in paths.items():
            item = self.scene.addPath(path, QPen(QColor('#e07842' if key == 'jump' else key),
                                               1.0 if key == 'jump' else 1.5))
            item.setZValue(20)
            item.setData(0, 'stitch-preview')
        if last:
            p = events[last - 1].point_mm
            dot = self.scene.addEllipse(p.x * PX - 3, p.y * PX - 3, 6, 6,
                                        QPen(QColor('#151515')), QBrush(QColor('#f5dd62')))
            dot.setZValue(25)
            dot.setData(0, 'stitch-preview')
        self.position_label.setText(f'{position + 1:,}/{len(events):,} events' +
                                    (' · windowed view' if start else ''))

    def _toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
            self.play_button.setText('Play')
        else:
            if self._plan is None:
                self.generate_preview()
            if self._plan:
                if self.timeline.value() == self.timeline.maximum():
                    self.timeline.setValue(0)
                self._timer.start()
                self.play_button.setText('Pause')

    def _advance(self):
        next_pos = min(self.timeline.maximum(), self.timeline.value() + 15)
        self.timeline.setValue(next_pos)
        if next_pos == self.timeline.maximum():
            self._timer.stop()
            self.play_button.setText('Play')

    def export_dst(self):
        if not self.editor:
            return
        try:
            plan = self._generate_plan()
            issues = inspect_plan(plan, self.editor.design.width_mm,
                                  self.editor.design.height_mm)
            errors = [x for x in issues if x.severity == 'ERROR']
            if errors:
                raise ValueError('Export blocked:\n' + '\n'.join(x.message for x in errors[:6]))
            data = export_dst(plan, label=(self.project_path.stem if self.project_path else 'TABARC'))
            report = inspect_dst(data)
            if (read_dst_events(data) != plan.events or
                    report.stitch_records != sum(e.opcode == Op.STITCH for e in plan.events)):
                raise ValueError('DST read-back differs from generated stitch sequence')
        except ValueError as exc:
            QMessageBox.warning(self, 'Export blocked', str(exc))
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Export machine file', '',
                                                   'Tajima DST (*.dst)')
        if filename:
            candidate = Path(filename)
            if candidate.suffix.lower() != '.dst':
                candidate = candidate.with_suffix('.dst')
            try:
                candidate.write_bytes(data)
                self.statusBar().showMessage(f'Exported {candidate.name}; verify before sewing')
            except OSError as exc:
                QMessageBox.critical(self, 'Export failed', str(exc))

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def main(argv: list[str] | None = None) -> int:
    import sys
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('TABARC Embroidery Studio')
    window = StudioWindow(argv[0] if argv else None)
    window.show()
    return app.exec()
