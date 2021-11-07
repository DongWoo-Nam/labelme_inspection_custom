# -*- coding: utf-8 -*-

import functools
import math
import os
import os.path as osp
import re
import webbrowser
import time
import sys
import datetime

from PyQt5.QtWidgets import QMessageBox

import imgviz
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets

from labelme import __appname__
from labelme import PY2
from labelme import QT5

from labelme import utils
from labelme.config import get_config
from labelme.label_file import LabelFile
from labelme.label_file import LabelFileError
from labelme.logger import logger
from labelme.shape import Shape
from labelme.widgets import BrightnessContrastDialog
from labelme.widgets import Canvas
from labelme.widgets import LabelDialog
from labelme.widgets import LabelListWidget
from labelme.widgets import LabelListWidgetItem
from labelme.widgets import ToolBar
from labelme.widgets import UniqueLabelQListWidget
from labelme.widgets import ZoomWidget

from labelme import ObjectStorageHandler as osh  # by hw1230

# added by khlee - 작업자별로 config파일을 다르게 설정
CONFFILE = None
if getattr(sys, 'frozen', False):  # pyinstaller로 빌드하면 path가 꼬임. 이렇게 걸어주면 빌드 했을 때, 실행시킨 경로를 얻을 수 있음
    APPLICATION_EXE_DIR = os.path.dirname(sys.executable)
    APPLICATION_DATA_DIR = sys._MEIPASS
    if os.path.isfile(APPLICATION_EXE_DIR + '/config.yaml'):
        CONFFILE = APPLICATION_EXE_DIR + '/config.yaml'
else:
    APPLICATION_EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    APPLICATION_DATA_DIR = APPLICATION_EXE_DIR



# added by hw1230
# conf = get_config()
conf = get_config(CONFFILE) # added by khlee
local_depository = conf["save_driver"].upper() + r":\\labelme\\"  # 저장 경로 드라이버를 수정 할 수 있도록 변경 by dwnam 211104
# local_depository = os.path.expanduser('~') + os.path.sep + "Documents" + os.path.sep + "labelme" + os.path.sep
down_bucket_name_list = []
down_directory_list = []
for i in range(1, 3):
    down_bucket_name_list.append(conf["down" + str(i) + "_bucket_name"])
    down_directory_list.append(conf["down" + str(i) + "_directory"])

img_bucket_name = conf["img_bucket_name"]
img_directory = conf["img_directory"]
up_bucket_name = conf["up_bucket_name"]
up_directory = conf["up_directory"]
upnok_bucket_name = conf["upnok_bucket_name"]
upnok_directory = conf["upnok_directory"]

down_access_key = conf["down_access_key"]
down_access_token = conf["down_access_token"]
up_access_key = conf["up_access_key"]
up_access_token = conf["up_access_token"]

local_directory_name = ['init_data', 'rework_data']
tab_title = ['초기 검수 데이터', '재검수 데이터']
result_title = ['승인 목록', '반려 목록']

# FIXME
# - [medium] Set max zoom value to something big enough for FitWidth/Window

# TODO(unknown):
# - [high] Add polygon movement with arrow keys
# - [high] Deselect shape when clicking and already selected(?)
# - [low,maybe] Preview images on file dialogs.
# - Zoom is too "steppy".

LABEL_COLORMAP = imgviz.label_colormap(value=200)


class MainWindow(QtWidgets.QMainWindow):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

    def __init__(
            self,
            config=None,
            filename=None,
            output=None,
            output_file=None,
            output_dir=None,
    ):
        if output is not None:
            logger.warning(
                "argument output is deprecated, use output_file instead"
            )
            if output_file is None:
                output_file = output

        # see labelme/config/default_config.yaml for valid configuration
        if config is None:
            config = get_config()
        self._config = config

        self.login_id = ""  # by hw1230

        # set default shape colors
        Shape.line_color = QtGui.QColor(*self._config["shape"]["line_color"])
        Shape.fill_color = QtGui.QColor(*self._config["shape"]["fill_color"])
        Shape.select_line_color = QtGui.QColor(
            *self._config["shape"]["select_line_color"]
        )
        Shape.select_fill_color = QtGui.QColor(
            *self._config["shape"]["select_fill_color"]
        )
        Shape.vertex_fill_color = QtGui.QColor(
            *self._config["shape"]["vertex_fill_color"]
        )
        Shape.hvertex_fill_color = QtGui.QColor(
            *self._config["shape"]["hvertex_fill_color"]
        )

        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__ + " (검수자용)")

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False

        # Main widgets and related state.
        self.labelDialog = LabelDialog(
            parent=self,
            labels=self._config["labels"],
            sort_labels=self._config["sort_labels"],
            show_text_field=self._config["show_label_text_field"],
            completion=self._config["label_completion"],
            fit_to_content=self._config["fit_to_content"],
            flags=self._config["label_flags"],
        )

        self.labelList = LabelListWidget()
        self.lastOpenDir = None

        #''' by hw1230
        self.flag_dock = self.flag_widget = None
        self.flag_dock = QtWidgets.QDockWidget(self.tr("Flags"), self)
        # self.flag_dock.setObjectName("Flags")                       # Annotation changed by dwnam
        self.flag_widget = QtWidgets.QListWidget()
        if config["flags"]:
            self.loadFlags({k: False for k in config["flags"]})
        # self.flag_dock.setWidget(self.flag_widget)                  # Annotation changed by dwnam
        self.flag_widget.itemChanged.connect(self.setDirty)
        #'''

        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        self.labelList.itemChanged.connect(self.labelItemChanged)
        self.labelList.itemDropped.connect(self.labelOrderChanged)
        self.shape_dock = QtWidgets.QDockWidget(
            self.tr("Polygon Labels"), self
        )
        self.shape_dock.setObjectName("Labels")
        self.shape_dock.setWidget(self.labelList)

        #''' by hw1230
        self.uniqLabelList = UniqueLabelQListWidget()
        self.uniqLabelList.setToolTip(
            self.tr(
                "Select label to start annotating for it. "
                "Press 'Esc' to deselect."
            )
        )
        if self._config["labels"]:
            for label in self._config["labels"]:
                item = self.uniqLabelList.createItemFromLabel(label)
                self.uniqLabelList.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.uniqLabelList.setItemLabel(item, label, rgb)
        self.label_dock = QtWidgets.QDockWidget(self.tr(u"Label List"), self)
        # self.label_dock.setObjectName(u"Label List")                # Annotation changed by dwnam
        # self.label_dock.setWidget(self.uniqLabelList)               # Annotation changed by dwnam
        #'''

        # GUI added by hw1230
        self.id = QtWidgets.QLineEdit()
        self.loginBtn = QtWidgets.QPushButton("조회", self)
        self.loginBtn.clicked.connect(self.login)
        self.loginLayout = QtWidgets.QHBoxLayout()
        self.loginLayout.setContentsMargins(0, 0, 0, 0)
        self.loginLayout.setSpacing(0)
        self.loginLayout.addWidget(self.id)
        self.loginLayout.addWidget(self.loginBtn)

        # self.fileSearch = QtWidgets.QLineEdit()
        # self.fileSearch.setPlaceholderText(self.tr("Search Filename"))
        # self.fileSearch.textChanged.connect(self.fileSearchChanged)
        self.okBtnList = []
        self.rejectBtnList = []
        self.btnLayoutList = []
        self.fileListWidgetList = []
        self.fileListLayoutList = []
        self.okListWidgetList = []
        self.rejectListWidgetList = []
        self.resultLabelList = []
        for i in range(0, 2):
            self.okBtnList.append(QtWidgets.QPushButton("승인", self))
            self.okBtnList[i].clicked.connect(self.ok)
            self.rejectBtnList.append(QtWidgets.QPushButton("반려", self))
            self.rejectBtnList[i].clicked.connect(self.reject)

            self.btnLayoutList.append(QtWidgets.QHBoxLayout())
            self.btnLayoutList[i].setContentsMargins(0, 0, 0, 0)
            self.btnLayoutList[i].setSpacing(0)
            self.btnLayoutList[i].addWidget(self.okBtnList[i])
            self.btnLayoutList[i].addWidget(self.rejectBtnList[i])

            self.fileListWidgetList.append(QtWidgets.QListWidget())
            self.fileListWidgetList[i].setMinimumHeight(int(float(self.height()) * 0.9))
            self.fileListWidgetList[i].itemSelectionChanged.connect(
                self.fileSelectionChanged
            )

            self.okListWidgetList.append(QtWidgets.QListWidget())
            self.rejectListWidgetList.append(QtWidgets.QListWidget())

            self.fileListLayoutList.append(QtWidgets.QVBoxLayout())
            self.fileListLayoutList[i].setContentsMargins(0, 0, 0, 0)
            self.fileListLayoutList[i].setSpacing(0)
            self.fileListLayoutList[i].addWidget(self.fileListWidgetList[i])
            self.fileListLayoutList[i].addLayout(self.btnLayoutList[i])
            self.resultLabelList.append([])
            self.resultLabelList[i].append(QtWidgets.QLabel(result_title[0] + " (0건)", self))
            self.fileListLayoutList[i].addWidget(self.resultLabelList[i][0])
            self.fileListLayoutList[i].addWidget(self.okListWidgetList[i])
            self.resultLabelList[i].append(QtWidgets.QLabel(result_title[1] + " (0건)", self))
            self.fileListLayoutList[i].addWidget(self.resultLabelList[i][1])
            self.fileListLayoutList[i].addWidget(self.rejectListWidgetList[i])

        # GUI added by hw1230
        # self.doneListWidget = QtWidgets.QListWidget()
        # doneListLayout = QtWidgets.QVBoxLayout()
        # doneListLayout.setContentsMargins(0, 0, 0, 0)
        # doneListLayout.setSpacing(0)
        # doneListLayout.addWidget(self.doneListWidget)
        # self.done_dock = QtWidgets.QDockWidget(self.tr(u"작업 완료 목록"), self)
        # self.done_dock.setObjectName(u"Done")
        # dlw = QtWidgets.QWidget()
        # dlw.setLayout(doneListLayout)
        # self.done_dock.setWidget(dlw)

        self.tabs = QtWidgets.QTabWidget()
        t1 = QtWidgets.QWidget()
        t1.setLayout(self.fileListLayoutList[0])
        self.tabs.addTab(t1, tab_title[0])
        t2 = QtWidgets.QWidget()
        t2.setLayout(self.fileListLayoutList[1])
        self.tabs.addTab(t2, tab_title[1])
        self.tabs.currentChanged.connect(self.tabChanged)

        outerLayout = QtWidgets.QVBoxLayout()
        outerLayout.setContentsMargins(0, 0, 0, 0)
        outerLayout.setSpacing(0)
        outerLayout.addLayout(self.loginLayout)  # by hw1230
        outerLayout.addWidget(self.tabs)

        self.file_dock = QtWidgets.QDockWidget(self.tr(u"검수 대상 목록"), self)
        self.file_dock.setObjectName(u"Files")
        flw = QtWidgets.QWidget()  # 헷갈려서 변수명 변경 fileListWidget -> flw. by hw1230
        flw.setLayout(outerLayout)
        self.file_dock.setWidget(flw)

        self.zoomWidget = ZoomWidget()
        self.setAcceptDrops(True)

        self.canvas = self.labelList.canvas = Canvas(
            epsilon=self._config["epsilon"],
            double_click=self._config["canvas"]["double_click"],
            num_backups=self._config["canvas"]["num_backups"],
        )
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidget(self.canvas)
        scrollArea.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scrollArea.verticalScrollBar(),
            Qt.Horizontal: scrollArea.horizontalScrollBar(),
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scrollArea)

        features = QtWidgets.QDockWidget.DockWidgetFeatures()
        for dock in ["shape_dock", "file_dock"]:  # "done_dock" added by hw1230
            if self._config[dock]["closable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetClosable
            if self._config[dock]["floatable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetFloatable
            if self._config[dock]["movable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetMovable
            getattr(self, dock).setFeatures(features)
            if self._config[dock]["show"] is False:
                getattr(self, dock).setVisible(False)

        # self.addDockWidget(Qt.RightDockWidgetArea, self.flag_dock)
        # self.addDockWidget(Qt.RightDockWidgetArea, self.label_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.shape_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)
        # self.addDockWidget(Qt.RightDockWidgetArea, self.done_dock)  # by hw1230

        # Actions
        action = functools.partial(utils.newAction, self)
        shortcuts = self._config["shortcuts"]
        quit = action(
            self.tr("&Quit"),
            self.close,
            shortcuts["quit"],
            "quit",
            self.tr("Quit application"),
        )
        open_ = action(
            self.tr("&Open"),
            self.openFile,
            shortcuts["open"],
            "open",
            self.tr("Open image or label file"),
        )
        opendir = action(
            self.tr("&Open Dir"),
            self.openDirDialog,
            shortcuts["open_dir"],
            "open",
            self.tr(u"Open Dir"),
        )
        openNextImg = action(
            self.tr("&Next Image"),
            self.openNextImg,
            shortcuts["open_next"],
            "next",
            self.tr(u"Open next (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        openPrevImg = action(
            self.tr("&Prev Image"),
            self.openPrevImg,
            shortcuts["open_prev"],
            "prev",
            self.tr(u"Open prev (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        save = action(
            self.tr("&Save"),
            self.saveFile,
            shortcuts["save"],
            "save",
            self.tr("Save labels to file"),
            enabled=False,
        )
        saveAs = action(
            self.tr("&Save As"),
            self.saveFileAs,
            shortcuts["save_as"],
            "save-as",
            self.tr("Save labels to a different file"),
            enabled=False,
        )

        deleteFile = action(
            self.tr("&Delete File"),
            self.deleteFile,
            shortcuts["delete_file"],
            "delete",
            self.tr("Delete current label file"),
            enabled=False,
        )

        changeOutputDir = action(
            self.tr("&Change Output Dir"),
            slot=self.changeOutputDirDialog,
            shortcut=shortcuts["save_to"],
            icon="open",
            tip=self.tr(u"Change where annotations are loaded/saved"),
        )

        saveAuto = action(
            text=self.tr("Save &Automatically"),
            slot=lambda x: self.actions.saveAuto.setChecked(x),
            icon="save",
            tip=self.tr("Save automatically"),
            checkable=True,
            enabled=True,
        )
        saveAuto.setChecked(self._config["auto_save"])

        saveWithImageData = action(
            text="Save With Image Data",
            slot=self.enableSaveImageWithData,
            tip="Save image data in label file",
            # checkable=True,
            # checked=self._config["store_data"],
        )

        close = action(
            "&Close",
            self.closeFile,
            shortcuts["close"],
            "close",
            "Close current file",
        )

        toggle_keep_prev_mode = action(
            self.tr("Keep Previous Annotation"),
            self.toggleKeepPrevMode,
            shortcuts["toggle_keep_prev_mode"],
            None,
            self.tr('Toggle "keep pevious annotation" mode'),
            checkable=True,
        )
        toggle_keep_prev_mode.setChecked(self._config["keep_prev"])

        createMode = action(
            self.tr("Create Polygons"),
            lambda: self.toggleDrawMode(False, createMode="polygon"),
            shortcuts["create_polygon"],
            "objects",
            self.tr("Start drawing polygons"),
            enabled=False,
        )
        createRectangleMode = action(
            self.tr("Create Rectangle"),
            lambda: self.toggleDrawMode(False, createMode="rectangle"),
            shortcuts["create_rectangle"],
            "objects",
            self.tr("Start drawing rectangles"),
            enabled=False,
        )
        # createCircleMode = action(
        #     self.tr("Create Circle"),
        #     lambda: self.toggleDrawMode(False, createMode="circle"),
        #     shortcuts["create_circle"],
        #     "objects",
        #     self.tr("Start drawing circles"),
        #     enabled=False,
        # )
        # createLineMode = action(
        #     self.tr("Create Line"),
        #     lambda: self.toggleDrawMode(False, createMode="line"),
        #     shortcuts["create_line"],
        #     "objects",
        #     self.tr("Start drawing lines"),
        #     enabled=False,
        # )
        # createPointMode = action(
        #     self.tr("Create Point"),
        #     lambda: self.toggleDrawMode(False, createMode="point"),
        #     shortcuts["create_point"],
        #     "objects",
        #     self.tr("Start drawing points"),
        #     enabled=False,
        # )
        # createLineStripMode = action(
        #     self.tr("Create LineStrip"),
        #     lambda: self.toggleDrawMode(False, createMode="linestrip"),
        #     shortcuts["create_linestrip"],
        #     "objects",
        #     self.tr("Start drawing linestrip. Ctrl+LeftClick ends creation."),
        #     enabled=False,
        # )
        editMode = action(
            self.tr("Edit Polygons"),
            self.setEditMode,
            shortcuts["edit_polygon"],
            "edit",
            self.tr("Move and edit the selected polygons"),
            enabled=False,
        )

        delete = action(
            self.tr("Delete Polygons"),
            self.deleteSelectedShape,
            shortcuts["delete_polygon"],
            "cancel",
            self.tr("Delete the selected polygons"),
            enabled=False,
        )
        copy = action(
            self.tr("Duplicate Polygons"),
            self.copySelectedShape,
            shortcuts["duplicate_polygon"],
            "copy",
            self.tr("Create a duplicate of the selected polygons"),
            enabled=False,
        )
        undoLastPoint = action(
            self.tr("Undo last point"),
            self.canvas.undoLastPoint,
            shortcuts["undo_last_point"],
            "undo",
            self.tr("Undo last drawn point"),
            enabled=False,
        )
        addPointToEdge = action(
            text=self.tr("Add Point to Edge"),
            slot=self.canvas.addPointToEdge,
            shortcut=shortcuts["add_point_to_edge"],
            icon="edit",
            tip=self.tr("Add point to the nearest edge"),
            enabled=False,
        )
        removePoint = action(
            text="Remove Selected Point",
            slot=self.removeSelectedPoint,
            icon="edit",
            tip="Remove selected point from polygon",
            enabled=False,
        )

        undo = action(
            self.tr("Undo"),
            self.undoShapeEdit,
            shortcuts["undo"],
            "undo",
            self.tr("Undo last add and edit of shape"),
            enabled=False,
        )

        hideAll = action(
            self.tr("&Hide\nPolygons"),
            functools.partial(self.togglePolygons, False),
            icon="eye",
            tip=self.tr("Hide all polygons"),
            enabled=False,
        )
        showAll = action(
            self.tr("&Show\nPolygons"),
            functools.partial(self.togglePolygons, True),
            icon="eye",
            tip=self.tr("Show all polygons"),
            enabled=False,
        )

        help = action(
            self.tr("&Tutorial"),
            self.tutorial,
            icon="help",
            tip=self.tr("Show tutorial page"),
        )

        # by hw1230
        autoAnnotation = action(
            self.tr("autoAnnotation"),
            self.autoAnnotation,
            icon="done",
            tip=self.tr("Make annotation automatically"),
            enabled=False,
        )

        zoom = QtWidgets.QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            self.tr(
                "Zoom in or out of the image. Also accessible with "
                "{} and {} from the canvas."
            ).format(
                utils.fmtShortcut(
                    "{},{}".format(shortcuts["zoom_in"], shortcuts["zoom_out"])
                ),
                utils.fmtShortcut(self.tr("Ctrl+Wheel")),
            )
        )
        self.zoomWidget.setEnabled(False)

        zoomIn = action(
            self.tr("Zoom &In"),
            functools.partial(self.addZoom, 1.1),
            shortcuts["zoom_in"],
            "zoom-in",
            self.tr("Increase zoom level"),
            enabled=False,
        )
        zoomOut = action(
            self.tr("&Zoom Out"),
            functools.partial(self.addZoom, 0.9),
            shortcuts["zoom_out"],
            "zoom-out",
            self.tr("Decrease zoom level"),
            enabled=False,
        )
        zoomOrg = action(
            self.tr("&Original size"),
            functools.partial(self.setZoom, 100),
            shortcuts["zoom_to_original"],
            "zoom",
            self.tr("Zoom to original size"),
            enabled=False,
        )
        fitWindow = action(
            self.tr("&Fit Window"),
            self.setFitWindow,
            shortcuts["fit_window"],
            "fit-window",
            self.tr("Zoom follows window size"),
            checkable=True,
            enabled=False,
        )
        fitWidth = action(
            self.tr("Fit &Width"),
            self.setFitWidth,
            shortcuts["fit_width"],
            "fit-width",
            self.tr("Zoom follows window width"),
            checkable=True,
            enabled=False,
        )
        brightnessContrast = action(
            "&Brightness Contrast",
            self.brightnessContrast,
            None,
            "color",
            "Adjust brightness and contrast",
            enabled=False,
        )
        # Group zoom controls into a list for easier toggling.
        zoomActions = (
            self.zoomWidget,
            zoomIn,
            zoomOut,
            zoomOrg,
            fitWindow,
            fitWidth,
        )
        self.zoomMode = self.FIT_WINDOW
        fitWindow.setChecked(Qt.Checked)
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action(
            self.tr("&Edit Label"),
            self.editLabel,
            shortcuts["edit_label"],
            "edit",
            self.tr("Modify the label of the selected polygon"),
            enabled=False,
        )

        fill_drawing = action(
            self.tr("Fill Drawing Polygon"),
            self.canvas.setFillDrawing,
            None,
            "color",
            self.tr("Fill polygon while drawing"),
            checkable=True,
            enabled=True,
        )
        fill_drawing.trigger()

        # Lavel list context menu.
        labelMenu = QtWidgets.QMenu()
        utils.addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu
        )

        # Store actions for further handling.
        self.actions = utils.struct(
            saveAuto=saveAuto,
            saveWithImageData=saveWithImageData,
            changeOutputDir=changeOutputDir,
            save=save,
            saveAs=saveAs,
            open=open_,
            close=close,
            deleteFile=deleteFile,
            toggleKeepPrevMode=toggle_keep_prev_mode,
            delete=delete,
            edit=edit,
            copy=copy,
            undoLastPoint=undoLastPoint,
            undo=undo,
            addPointToEdge=addPointToEdge,
            removePoint=removePoint,
            createMode=createMode,
            editMode=editMode,
            createRectangleMode=createRectangleMode,
            # createCircleMode=createCircleMode,
            # createLineMode=createLineMode,
            # createPointMode=createPointMode,
            # createLineStripMode=createLineStripMode,
            zoom=zoom,
            zoomIn=zoomIn,
            zoomOut=zoomOut,
            zoomOrg=zoomOrg,
            fitWindow=fitWindow,
            fitWidth=fitWidth,
            brightnessContrast=brightnessContrast,
            zoomActions=zoomActions,
            openNextImg=openNextImg,
            openPrevImg=openPrevImg,
            autoAnnotation=autoAnnotation,  # by hw1230
            fileMenuActions=(open_, opendir, save, saveAs, close, quit),
            tool=(),
            # XXX: need to add some actions here to activate the shortcut
            editMenu=(
                edit,
                copy,
                delete,
                None,
                undo,
                # undoLastPoint,
                # None,
                # addPointToEdge,
                # None,
                # toggle_keep_prev_mode,
            ),
            # menu shown at right click
            menu=(
                createMode,
                createRectangleMode,
                # createCircleMode,
                # createLineMode,
                # createPointMode,
                # createLineStripMode,
                editMode,
                edit,
                copy,
                delete,
                undo,
                # undoLastPoint,
                addPointToEdge,
                removePoint,
            ),
            onLoadActive=(
                close,
                createMode,
                createRectangleMode,
                # createCircleMode,
                # createLineMode,
                # createPointMode,
                # createLineStripMode,
                editMode,
                brightnessContrast,
            ),
            onShapesPresent=(saveAs, hideAll, showAll),
        )

        self.canvas.edgeSelected.connect(self.canvasShapeEdgeSelected)
        self.canvas.vertexSelected.connect(self.actions.removePoint.setEnabled)

        self.menus = utils.struct(
            file=self.menu(self.tr("&File")),
            edit=self.menu(self.tr("&Edit")),
            view=self.menu(self.tr("&View")),
            # help=self.menu(self.tr("&Help")),
            recentFiles=QtWidgets.QMenu(self.tr("Open &Recent")),
            labelList=labelMenu,
        )

        utils.addActions(
            self.menus.file,
            (
                # open_,
                openNextImg,
                openPrevImg,
                # opendir,
                # self.menus.recentFiles,
                # save,
                # saveAs,
                # saveAuto,
                # changeOutputDir,
                # saveWithImageData,
                # close,
                # deleteFile,
                None,
                quit,
            ),
        )
        # utils.addActions(self.menus.help, (help,))
        utils.addActions(
            self.menus.view,
            (
                # deleted by hw1230
                # self.flag_dock.toggleViewAction(),
                # self.label_dock.toggleViewAction(),
                self.shape_dock.toggleViewAction(),
                self.file_dock.toggleViewAction(),
                # self.done_dock.toggleViewAction(),  # by hw1230
                None,
                fill_drawing,
                None,
                hideAll,
                showAll,
                None,
                zoomIn,
                zoomOut,
                zoomOrg,
                None,
                fitWindow,
                fitWidth,
                None,
                brightnessContrast,
            ),
        )

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        utils.addActions(self.canvas.menus[0], self.actions.menu)
        utils.addActions(
            self.canvas.menus[1],
            (
                action("&Copy here", self.copyShape),
                action("&Move here", self.moveShape),
            ),
        )

        self.tools = self.toolbar("Tools")
        # Menu buttons on Left
        self.actions.tool = (
            # open_,
            # opendir,
            openNextImg,
            openPrevImg,
            # save,
            # deleteFile,
            None,
            createMode,
            createRectangleMode,  # rectangle 버튼 추가 210908 by dwnam
            editMode,
            copy,
            delete,
            undo,
            brightnessContrast,
            None,
            zoom,
            fitWidth,
            # autoAnnotation  # by hw1230
        )

        self.statusBar().showMessage(self.tr("%s started.") % __appname__)
        self.statusBar().show()

        if output_file is not None and self._config["auto_save"]:
            logger.warn(
                "If `auto_save` argument is True, `output_file` argument "
                "is ignored and output filename is automatically "
                "set as IMAGE_BASENAME.json."
            )
        self.output_file = output_file
        self.output_dir = output_dir

        # other_data = {"endpoint": {"bucket": down_bucket_name, "path": ""}, "reject": {"date": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "message": ""}}
        # Application state.
        self.image = QtGui.QImage()
        self.imagePath = None
        self.recentFiles = []
        self.maxRecent = 7
        self.otherData = None  # other_data
        self.zoom_level = 100
        self.fit_window = False
        self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
        self.brightnessContrast_values = {}
        self.scroll_values = {
            Qt.Horizontal: {},
            Qt.Vertical: {},
        }  # key=filename, value=scroll_value

        if filename is not None and osp.isdir(filename):
            self.importDirImages(filename, load=False)
        else:
            self.filename = filename

        if config["file_search"]:
            self.fileSearch.setText(config["file_search"])
            self.fileSearchChanged()

        # XXX: Could be completely declarative.
        # Restore application settings.
        self.settings = QtCore.QSettings("labelme", "labelme")
        # FIXME: QSettings.value can return None on PyQt4
        self.recentFiles = self.settings.value("recentFiles", []) or []
        size = self.settings.value("window/size", QtCore.QSize(600, 500))
        position = self.settings.value("window/position", QtCore.QPoint(0, 0))
        self.resize(size)
        self.move(position)
        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(
            self.settings.value("window/state", QtCore.QByteArray())
        )

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time,
        # make sure it runs in the background.
        if self.filename is not None:
            self.queueEvent(functools.partial(self.loadFile, self.filename))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

        # self.firstStart = True
        # if self.firstStart:
        #    QWhatsThis.enterWhatsThisMode()

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            utils.addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName("%sToolBar" % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            utils.addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar

    # Support Functions

    def noShapes(self):
        return not len(self.labelList)

    def populateModeActions(self):
        tool, menu = self.actions.tool, self.actions.menu
        self.tools.clear()
        utils.addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        utils.addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (
            self.actions.createMode,
            self.actions.createRectangleMode,
            # self.actions.createCircleMode,
            # self.actions.createLineMode,
            # self.actions.createPointMode,
            # self.actions.createLineStripMode,
            self.actions.editMode,
        )
        utils.addActions(self.menus.edit, actions + self.actions.editMenu)

    def setDirty(self):
        # Even if we autosave the file, we keep the ability to undo
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)

        if self._config["auto_save"] or self.actions.saveAuto.isChecked():
            label_file = osp.splitext(self.imagePath)[0] + ".json"
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = osp.join(self.output_dir, label_file_without_path)
            self.saveLabels(label_file)
            return
        self.dirty = True
        self.actions.save.setEnabled(True)
        title = __appname__ + " (검수자용)"
        if self.filename is not None:
            title = "{} - {}*".format(title, self.filename)
        self.setWindowTitle(title)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        # self.actions.createCircleMode.setEnabled(True)
        # self.actions.createLineMode.setEnabled(True)
        # self.actions.createPointMode.setEnabled(True)
        # self.actions.createLineStripMode.setEnabled(True)
        title = __appname__ + " (검수자용)"
        if self.filename is not None:
            title = "{} - {}".format(title, self.filename)
        self.setWindowTitle(title)

        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def canvasShapeEdgeSelected(self, selected, shape):
        self.actions.addPointToEdge.setEnabled(
            selected and shape and shape.canAddPoint()
        )

    def queueEvent(self, function):
        QtCore.QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.labelList.clear()
        self.filename = None
        self.imagePath = None
        self.imageData = None
        self.labelFile = None
        self.otherData = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filename):
        if filename in self.recentFiles:
            self.recentFiles.remove(filename)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filename)

    # Callbacks

    def undoShapeEdit(self):
        ia = self.canvas.restoreShape()
        if ia:  # by hw1230
            self.actions.autoAnnotation.setEnabled(True)
        self.labelList.clear()
        self.loadShapes(self.canvas.shapes)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)

    def tutorial(self):
        url = "https://github.com/wkentaro/labelme/tree/master/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def toggleDrawingSensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self.actions.editMode.setEnabled(not drawing)
        self.actions.undoLastPoint.setEnabled(drawing)
        self.actions.undo.setEnabled(not drawing)
        self.actions.delete.setEnabled(not drawing)

    def toggleDrawMode(self, edit=True, createMode="polygon"):
        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode
        if edit:
            self.actions.createMode.setEnabled(True)
            self.actions.createRectangleMode.setEnabled(True)
            # self.actions.createCircleMode.setEnabled(True)
            # self.actions.createLineMode.setEnabled(True)
            # self.actions.createPointMode.setEnabled(True)
            # self.actions.createLineStripMode.setEnabled(True)
        else:
            if createMode == "polygon":
                self.actions.createMode.setEnabled(False)
                self.actions.createRectangleMode.setEnabled(True)
                # self.actions.createCircleMode.setEnabled(True)
                # self.actions.createLineMode.setEnabled(True)
                # self.actions.createPointMode.setEnabled(True)
                # self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "rectangle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(False)
                # self.actions.createCircleMode.setEnabled(True)
                # self.actions.createLineMode.setEnabled(True)
                # self.actions.createPointMode.setEnabled(True)
                # self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "line":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                # self.actions.createCircleMode.setEnabled(True)
                # self.actions.createLineMode.setEnabled(False)
                # self.actions.createPointMode.setEnabled(True)
                # self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "point":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                # self.actions.createCircleMode.setEnabled(True)
                # self.actions.createLineMode.setEnabled(True)
                # self.actions.createPointMode.setEnabled(False)
                # self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "circle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                # self.actions.createCircleMode.setEnabled(False)
                # self.actions.createLineMode.setEnabled(True)
                # self.actions.createPointMode.setEnabled(True)
                # self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "linestrip":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                # self.actions.createCircleMode.setEnabled(True)
                # self.actions.createLineMode.setEnabled(True)
                # self.actions.createPointMode.setEnabled(True)
                # self.actions.createLineStripMode.setEnabled(False)
            else:
                raise ValueError("Unsupported createMode: %s" % createMode)
        self.actions.editMode.setEnabled(not edit)

    def setEditMode(self):
        self.toggleDrawMode(True)

    def updateFileMenu(self):
        current = self.filename

        def exists(filename):
            return osp.exists(str(filename))

        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f != current and exists(f)]
        for i, f in enumerate(files):
            icon = utils.newIcon("labels")
            action = QtWidgets.QAction(
                icon, "&%d %s" % (i + 1, QtCore.QFileInfo(f).fileName()), self
            )
            action.triggered.connect(functools.partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def validateLabel(self, label):
        # no validation
        if self._config["validate_label"] is None:
            return True

        for i in range(self.uniqLabelList.count()):
            label_i = self.uniqLabelList.item(i).data(Qt.UserRole)
            if self._config["validate_label"] in ["exact"]:
                if label_i == label:
                    return True
        return False

    def editLabel(self, item=None):
        if item and not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem type")

        if not self.canvas.editing():
            return
        if not item:
            item = self.currentItem()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return
        text, flags, group_id = self.labelDialog.popUp(
            text=shape.label,
            flags=shape.flags,
            group_id=shape.group_id,
        )
        if text is None:
            return
        if not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return
        shape.label = text
        shape.flags = flags
        shape.group_id = group_id
        if shape.group_id is None:
            item.setText(shape.label)
        else:
            item.setText("{} ({})".format(shape.label, shape.group_id))
        self.setDirty()
        if not self.uniqLabelList.findItemsByLabel(shape.label):
            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.UserRole, shape.label)
            self.uniqLabelList.addItem(item)

    def fileSearchChanged(self):
        self.importDirImages(
            self.lastOpenDir,
            pattern=self.fileSearch.text(),
            load=False,
        )

    def fileSelectionChanged(self):
        items = self.fileListWidgetList[self.tabs.currentIndex()].selectedItems()
        if not items:
            return
        item = items[0]

        if not self.mayContinue():
            return

        # currIndex = self.imageList.index(str(item.text()))
        currIndex = self.imageList.index(str(item.data(99)))  # by hw1230
        if currIndex < len(self.imageList):
            filename = self.imageList[currIndex]
            if filename:
                self.loadFile(self.tabs.currentIndex(), filename)

    # React to canvas signals.
    def shapeSelectionChanged(self, selected_shapes):
        self._noSelectionSlot = True
        for shape in self.canvas.selectedShapes:
            shape.selected = False
        self.labelList.clearSelection()
        self.canvas.selectedShapes = selected_shapes
        for shape in self.canvas.selectedShapes:
            shape.selected = True
            item = self.labelList.findItemByShape(shape)
            self.labelList.selectItem(item)
            self.labelList.scrollToItem(item)
        self._noSelectionSlot = False
        n_selected = len(selected_shapes)
        self.actions.delete.setEnabled(n_selected)
        self.actions.copy.setEnabled(n_selected)
        self.actions.edit.setEnabled(n_selected == 1)

    def addLabel(self, shape):
        if shape.group_id is None:
            text = shape.label
        else:
            text = "{} ({})".format(shape.label, shape.group_id)
        label_list_item = LabelListWidgetItem(text, shape)
        self.labelList.addItem(label_list_item)
        if not self.uniqLabelList.findItemsByLabel(shape.label):
            item = self.uniqLabelList.createItemFromLabel(shape.label)
            self.uniqLabelList.addItem(item)
            rgb = self._get_rgb_by_label(shape.label)
            self.uniqLabelList.setItemLabel(item, shape.label, rgb)
        self.labelDialog.addLabelHistory(shape.label)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

        rgb = self._get_rgb_by_label(shape.label)

        r, g, b = rgb
        label_list_item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                text, r, g, b
            )
        )
        shape.line_color = QtGui.QColor(r, g, b)
        shape.vertex_fill_color = QtGui.QColor(r, g, b)
        shape.hvertex_fill_color = QtGui.QColor(255, 255, 255)
        shape.fill_color = QtGui.QColor(r, g, b, 128)
        shape.select_line_color = QtGui.QColor(255, 255, 255)
        shape.select_fill_color = QtGui.QColor(r, g, b, 155)

    def _get_rgb_by_label(self, label):
        if self._config["shape_color"] == "auto":
            item = self.uniqLabelList.findItemsByLabel(label)[0]
            label_id = self.uniqLabelList.indexFromItem(item).row() + 1
            label_id += self._config["shift_auto_shape_color"]
            return LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)]
        elif (
                self._config["shape_color"] == "manual"
                and self._config["label_colors"]
                and label in self._config["label_colors"]
        ):
            return self._config["label_colors"][label]
        elif self._config["default_shape_color"]:
            return self._config["default_shape_color"]

    def remLabels(self, shapes):
        for shape in shapes:
            item = self.labelList.findItemByShape(shape)
            self.labelList.removeItem(item)

    def loadShapes(self, shapes, replace=True):
        self._noSelectionSlot = True
        for shape in shapes:
            self.addLabel(shape)
        self.labelList.clearSelection()
        self._noSelectionSlot = False
        self.canvas.loadShapes(shapes, replace=replace)

    def loadLabels(self, shapes, replace=True):  # replace added by hw1230
        s = []
        for shape in shapes:
            label = shape["label"]
            points = shape["points"]
            shape_type = shape["shape_type"]
            flags = shape["flags"]
            group_id = shape["group_id"]
            other_data = shape["other_data"]

            if not points:
                # skip point-empty shape
                continue

            shape = Shape(
                label=label,
                shape_type=shape_type,
                group_id=group_id,
            )
            for x, y in points:
                shape.addPoint(QtCore.QPointF(x, y))
            shape.close()

            default_flags = {}
            if self._config["label_flags"]:
                for pattern, keys in self._config["label_flags"].items():
                    if re.match(pattern, label):
                        for key in keys:
                            default_flags[key] = False
            shape.flags = default_flags
            shape.flags.update(flags)
            shape.other_data = other_data

            s.append(shape)
        self.loadShapes(s, replace)  # replace added by hw1230

    def loadFlags(self, flags):
        self.flag_widget.clear()
        for key, flag in flags.items():
            item = QtWidgets.QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flag else Qt.Unchecked)
            self.flag_widget.addItem(item)

    def saveLabels(self, filename):
        lf = LabelFile()

        def format_shape(s):
            data = s.other_data.copy()
            data.update(
                dict(
                    label=s.label.encode("utf-8") if PY2 else s.label,
                    points=[(p.x(), p.y()) for p in s.points],
                    group_id=s.group_id,
                    shape_type=s.shape_type,
                    flags=s.flags,
                )
            )
            return data

        shapes = [format_shape(item.shape()) for item in self.labelList]
        flags = {}
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
            imageData = self.imageData if self._config["store_data"] else None  # None 이미지 해시 값 기본으로 안넣기 위해서는 None으로
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            lf.save(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData= imageData,
                imageHeight=self.image.height(),
                imageWidth=self.image.width(),
                otherData=self.otherData,
                flags=flags,
            )
            self.labelFile = lf
            items = self.fileListWidgetList[self.tabs.currentIndex()].findItems(
                self.imagePath, Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.errorMessage(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    def copySelectedShape(self):
        added_shapes = self.canvas.copySelectedShapes()
        self.labelList.clearSelection()
        for shape in added_shapes:
            self.addLabel(shape)
        self.setDirty()

    def labelSelectionChanged(self):
        if self._noSelectionSlot:
            return
        if self.canvas.editing():
            selected_shapes = []
            for item in self.labelList.selectedItems():
                selected_shapes.append(item.shape())
            if selected_shapes:
                self.canvas.selectShapes(selected_shapes)
            else:
                self.canvas.deSelectShape()

    def labelItemChanged(self, item):
        shape = item.shape()
        self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    def labelOrderChanged(self):
        self.setDirty()
        self.canvas.loadShapes([item.shape() for item in self.labelList])

    # Callback functions:

    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        assert len(self.canvas.shapesBackups) == len(self.canvas.isAutoBackup)
        items = self.uniqLabelList.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        if self._config["display_label_popup"] or not text:
            previous_text = self.labelDialog.edit.text()
            text, flags, group_id = self.labelDialog.popUp(text)
            if not text:
                self.labelDialog.edit.setText(previous_text)

        if text and not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            text = ""
        if text:
            self.labelList.clearSelection()
            shape = self.canvas.setLastLabel(text, flags)
            shape.group_id = group_id
            self.addLabel(shape)
            self.actions.editMode.setEnabled(True)
            self.actions.undoLastPoint.setEnabled(False)
            self.actions.undo.setEnabled(True)
            self.setDirty()
        else:
            self.canvas.undoLastLine()
            self.canvas.shapesBackups.pop()
            self.canvas.isAutoBackup.pop()

    def scrollRequest(self, delta, orientation):
        units = -delta * 0.1  # natural scroll
        bar = self.scrollBars[orientation]
        value = bar.value() + bar.singleStep() * units
        self.setScroll(orientation, value)

    def setScroll(self, orientation, value):
        self.scrollBars[orientation].setValue(value)
        self.scroll_values[orientation][self.filename] = value

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)
        self.zoom_values[self.filename] = (self.zoomMode, value)

    def addZoom(self, increment=1.1):
        zoom_value = self.zoomWidget.value() * increment
        if increment > 1:
            zoom_value = math.ceil(zoom_value)
        else:
            zoom_value = math.floor(zoom_value)
        self.setZoom(zoom_value)

    def zoomRequest(self, delta, pos):
        canvas_width_old = self.canvas.width()
        units = 1.1
        if delta < 0:
            units = 0.9
        self.addZoom(units)

        canvas_width_new = self.canvas.width()
        if canvas_width_old != canvas_width_new:
            canvas_scale_factor = canvas_width_new / canvas_width_old

            x_shift = round(pos.x() * canvas_scale_factor) - pos.x()
            y_shift = round(pos.y() * canvas_scale_factor) - pos.y()

            self.setScroll(
                Qt.Horizontal,
                self.scrollBars[Qt.Horizontal].value() + x_shift,
            )
            self.setScroll(
                Qt.Vertical,
                self.scrollBars[Qt.Vertical].value() + y_shift,
            )

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def onNewBrightnessContrast(self, qimage):
        self.canvas.loadPixmap(
            QtGui.QPixmap.fromImage(qimage), clear_shapes=False
        )

    def brightnessContrast(self, value):
        dialog = BrightnessContrastDialog(
            utils.img_data_to_pil(self.imageData),
            self.onNewBrightnessContrast,
            parent=self,
        )
        brightness, contrast = self.brightnessContrast_values.get(
            self.filename, (None, None)
        )
        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)
        dialog.exec_()

        brightness = dialog.slider_brightness.value()
        contrast = dialog.slider_contrast.value()
        self.brightnessContrast_values[self.filename] = (brightness, contrast)

    def togglePolygons(self, value):
        for item in self.labelList:
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, tabIndex, filename=None):
        """Load the specified file, or the last opened file if None."""
        # changing fileListWidget loads file
        if filename in self.imageList and (
                self.fileListWidgetList[tabIndex].currentRow() != self.imageList.index(filename)
        ):
            self.fileListWidgetList[tabIndex].setCurrentRow(self.imageList.index(filename))
            self.fileListWidgetList[tabIndex].repaint()
            return

        self.resetState()
        self.canvas.setEnabled(False)
        if filename is None:
            filename = self.settings.value("filename", "")
        filename = str(filename)
        if not QtCore.QFile.exists(filename):
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % filename,
            )
            return False
        # assumes same name, but json extension
        self.status(self.tr("Loading %s...") % osp.basename(str(filename)))
        label_file = osp.splitext(filename)[0] + ".json"
        if self.output_dir:
            label_file_without_path = osp.basename(label_file)
            label_file = osp.join(self.output_dir, label_file_without_path)
        if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
                label_file
        ):
            try:
                self.labelFile = LabelFile(label_file)
            except LabelFileError as e:
                self.errorMessage(
                    self.tr("Error opening file"),
                    self.tr(
                        "<p><b>%s</b></p>"
                        "<p>Make sure <i>%s</i> is a valid label file."
                    )
                    % (e, label_file),
                )
                self.status(self.tr("Error reading %s") % label_file)
                return False
            self.imageData = self.labelFile.imageData
            self.imagePath = osp.join(
                osp.dirname(label_file),
                self.labelFile.imagePath,
            )
            self.otherData = self.labelFile.otherData
        else:
            self.imageData = LabelFile.load_image_file(filename)
            if self.imageData:
                self.imagePath = filename
            self.labelFile = None
            self.canvas.shapesBackups.append([])  # by hw1230
            self.canvas.isAutoBackup.append(False)
        self.actions.autoAnnotation.setEnabled(True)  # by hw1230

        image = QtGui.QImage.fromData(self.imageData)

        if image.isNull():
            formats = [
                "*.{}".format(fmt.data().decode())
                for fmt in QtGui.QImageReader.supportedImageFormats()
            ]
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr(
                    "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                    "Supported image formats: {1}</p>"
                ).format(filename, ",".join(formats)),
            )
            self.status(self.tr("Error reading %s") % filename)
            return False
        self.image = image
        self.filename = filename
        if self._config["keep_prev"]:
            prev_shapes = self.canvas.shapes
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
        flags = {k: False for k in self._config["flags"] or []}
        if self.labelFile:
            self.loadLabels(self.labelFile.shapes)
            if self.labelFile.flags is not None:
                flags.update(self.labelFile.flags)
        self.loadFlags(flags)
        if self._config["keep_prev"] and self.noShapes():
            self.loadShapes(prev_shapes, replace=False)
            self.setDirty()
        else:
            self.setClean()
        self.canvas.setEnabled(True)
        # set zoom values
        is_initial_load = not self.zoom_values
        if self.filename in self.zoom_values:
            self.zoomMode = self.zoom_values[self.filename][0]
            self.setZoom(self.zoom_values[self.filename][1])
        elif is_initial_load or not self._config["keep_prev_scale"]:
            self.adjustScale(initial=True)
        # set scroll values
        for orientation in self.scroll_values:
            if self.filename in self.scroll_values[orientation]:
                self.setScroll(
                    orientation, self.scroll_values[orientation][self.filename]
                )
        # set brightness constrast values
        dialog = BrightnessContrastDialog(
            utils.img_data_to_pil(self.imageData),
            self.onNewBrightnessContrast,
            parent=self,
        )
        brightness, contrast = self.brightnessContrast_values.get(
            self.filename, (None, None)
        )
        if self._config["keep_prev_brightness"] and self.recentFiles:
            brightness, _ = self.brightnessContrast_values.get(
                self.recentFiles[0], (None, None)
            )
        if self._config["keep_prev_contrast"] and self.recentFiles:
            _, contrast = self.brightnessContrast_values.get(
                self.recentFiles[0], (None, None)
            )
        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)
        self.brightnessContrast_values[self.filename] = (brightness, contrast)
        if brightness is not None or contrast is not None:
            dialog.onNewValue(None)
        self.paintCanvas()
        self.addRecentFile(self.filename)
        self.toggleActions(True)
        self.canvas.setFocus()
        self.status(self.tr("Loaded %s") % osp.basename(str(filename)))
        return True

    def resizeEvent(self, event):
        if (
                self.canvas
                and not self.image.isNull()
                and self.zoomMode != self.MANUAL_ZOOM
        ):
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.setMinimumHeight(self.canvas.pixmap.height() * self.zoomWidget.value() * 0.01 + 30)
        self.canvas.setMinimumWidth(self.canvas.pixmap.width() * self.zoomWidget.value() * 0.01 + 30)
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        value = int(100 * value)
        self.zoomWidget.setValue(value)
        self.zoom_values[self.filename] = (self.zoomMode, value)

    def scaleFitWindow(self):
        """Figure out the size of the pixmap to fit the main widget."""
        e = 32.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def enableSaveImageWithData(self, enabled):
        self._config["store_data"] = enabled
        self.actions.saveWithImageData.setChecked(enabled)

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        self.settings.setValue(
            "filename", self.filename if self.filename else ""
        )
        self.settings.setValue("window/size", self.size())
        self.settings.setValue("window/position", self.pos())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("recentFiles", self.recentFiles)
        # ask the use for where to save the labels
        # self.settings.setValue('window/geometry', self.saveGeometry())

    def dragEnterEvent(self, event):
        extensions = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        if event.mimeData().hasUrls():
            items = [i.toLocalFile() for i in event.mimeData().urls()]
            if any([i.lower().endswith(tuple(extensions)) for i in items]):
                event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.mayContinue():
            event.ignore()
            return
        items = [i.toLocalFile() for i in event.mimeData().urls()]
        self.importDroppedImageFiles(items)

    # User Dialogs #

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(self.tabs.currentIndex(), filename)

    def openPrevImg(self, _value=False):
        keep_prev = self._config["keep_prev"]
        if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            self._config["keep_prev"] = True

        if not self.mayContinue():
            return

        if len(self.imageList) <= 0:
            return

        if self.filename is None:
            return

        currIndex = self.imageList.index(self.filename)
        if currIndex - 1 >= 0:
            filename = self.imageList[currIndex - 1]
            if filename:
                self.loadFile(self.tabs.currentIndex(), filename)

        self._config["keep_prev"] = keep_prev

    def openNextImg(self, _value=False, load=True):
        keep_prev = self._config["keep_prev"]
        if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            self._config["keep_prev"] = True

        if not self.mayContinue():
            return
        if len(self.imageList) <= 0:
            return

        filename = None
        if self.filename is None:
            filename = self.imageList[0]
        else:
            currIndex = self.imageList.index(self.filename)
            if currIndex + 1 < len(self.imageList):
                filename = self.imageList[currIndex + 1]
            else:
                filename = self.imageList[-1]
        self.filename = filename

        if self.filename and load:
            self.loadFile(self.tabs.currentIndex(), self.filename)
        self._config["keep_prev"] = keep_prev

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = osp.dirname(str(self.filename)) if self.filename else "."
        formats = [
            "*.{}".format(fmt.data().decode())
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("Image & Label files (%s)") % " ".join(
            formats + ["*%s" % LabelFile.suffix]
        )
        filename = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("%s - Choose Image or Label file") % __appname__,
            path,
            filters,
        )
        if QT5:
            filename, _ = filename
        filename = str(filename)
        if filename:
            self.loadFile(self.tabs.currentIndex(), filename)

    def changeOutputDirDialog(self, _value=False):
        default_output_dir = self.output_dir
        if default_output_dir is None and self.filename:
            default_output_dir = osp.dirname(self.filename)
        if default_output_dir is None:
            default_output_dir = self.currentPath()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s - Save/Load Annotations in Directory") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.ShowDirsOnly
            | QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self.output_dir = output_dir

        self.statusBar().showMessage(
            self.tr("%s . Annotations will be saved/loaded in %s")
            % ("Change Annotations Dir", self.output_dir)
        )
        self.statusBar().show()

        current_filename = self.filename
        self.importDirImages(self.lastOpenDir, load=False)

        if current_filename in self.imageList:
            # retain currently selected file
            self.fileListWidgetList[self.tabs.currentIndex()].setCurrentRow(
                self.imageList.index(current_filename)
            )
            self.fileListWidgetList[self.tabs.currentIndex()].repaint()

    def saveFile(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        if not self.mayContinue():
            return
        '''
        if self.labelFile:
            # DL20180323 - overwrite when in directory
            self._saveFile(self.labelFile.filename)
        elif self.output_file:
            self._saveFile(self.output_file)
            self.close()
        else:
            self._saveFile(self.saveFileDialog())
        '''

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = self.tr("%s - Choose File") % __appname__
        filters = self.tr("Label files (*%s)") % LabelFile.suffix
        if self.output_dir:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.output_dir, filters
            )
        else:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.currentPath(), filters
            )
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        basename = osp.basename(osp.splitext(self.filename)[0])
        if self.output_dir:
            default_labelfile_name = osp.join(
                self.output_dir, basename + LabelFile.suffix
            )
        else:
            default_labelfile_name = osp.join(
                self.currentPath(), basename + LabelFile.suffix
            )
        filename = dlg.getSaveFileName(
            self,
            self.tr("Choose File"),
            default_labelfile_name,
            self.tr("Label files (*%s)") % LabelFile.suffix,
        )
        if isinstance(filename, tuple):
            filename, _ = filename
        return filename

    def _saveFile(self, filename):
        if filename and self.saveLabels(filename):
            self.addRecentFile(filename)
            self.setClean()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def getLabelFile(self):
        if self.filename.lower().endswith(".json"):
            label_file = self.filename
        else:
            label_file = osp.splitext(self.filename)[0] + ".json"

        return label_file

    def deleteFile(self):
        mb = QtWidgets.QMessageBox
        msg = self.tr(
            "You are about to permanently delete this label file, "
            "proceed anyway?"
        )
        answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
        if answer != mb.Yes:
            return

        label_file = self.getLabelFile()
        if osp.exists(label_file):
            os.remove(label_file)
            logger.info("Label file is removed: {}".format(label_file))

            item = self.fileListWidgetList[self.tabs.currentIndex()].currentItem()
            item.setCheckState(Qt.Unchecked)

            self.resetState()

    # Message Dialogs. #
    def hasLabels(self):
        if self.noShapes():
            self.errorMessage(
                "No objects labeled",
                "You must label at least one object to save the file.",
            )
            return False
        return True

    def hasLabelFile(self):
        if self.filename is None:
            return False

        label_file = self.getLabelFile()
        return osp.exists(label_file)

    def mayContinue(self):
        if not self.dirty:
            return True

        # by hw1230
        # print(self.filename.split('.')[0] + ".json")
        self._saveFile(self.filename.split('.')[0] + ".json")
        return True
        '''
        mb = QtWidgets.QMessageBox
        msg = self.tr('Save annotations to "{}" before closing?').format(
            self.filename
        )
        answer = mb.question(
            self,
            self.tr("Save annotations?"),
            msg,
            mb.Save | mb.Discard | mb.Cancel,
            mb.Save,
        )
        if answer == mb.Discard:
            return True
        elif answer == mb.Save:
            self.saveFile()
            return True
        else:  # answer == mb.Cancel
            return False
        '''

    def errorMessage(self, title, message):
        return QtWidgets.QMessageBox.critical(
            self, title, "<p><b>%s</b></p>%s" % (title, message)
        )

    def currentPath(self):
        return osp.dirname(str(self.filename)) if self.filename else "."

    def toggleKeepPrevMode(self):
        self._config["keep_prev"] = not self._config["keep_prev"]

    def removeSelectedPoint(self):
        self.canvas.removeSelectedPoint()
        if not self.canvas.hShape.points:
            self.canvas.deleteShape(self.canvas.hShape)
            self.remLabels([self.canvas.hShape])
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def deleteSelectedShape(self):
        yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
        msg = self.tr(
            "You are about to permanently delete {} polygons, "
            "proceed anyway?"
        ).format(len(self.canvas.selectedShapes))
        if yes == QtWidgets.QMessageBox.warning(
                self, self.tr("Attention"), msg, yes | no, yes
        ):
            self.remLabels(self.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.labelList.clearSelection()
        for shape in self.canvas.selectedShapes:
            self.addLabel(shape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else "."
        if self.lastOpenDir and osp.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = (
                osp.dirname(self.filename) if self.filename else "."
            )

        targetDirPath = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("%s - Open Directory") % __appname__,
                defaultOpenDirPath,
                QtWidgets.QFileDialog.ShowDirsOnly
                | QtWidgets.QFileDialog.DontResolveSymlinks,
            )
        )
        self.importDirImages(targetDirPath)
        self.okBtnList[self.tabs.currentIndex()].setEnabled(False)  # by hw1230
        self.rejectBtnList[self.tabs.currentIndex()].setEnabled(False)

    @property
    def imageList(self):
        lst = []
        for i in range(self.fileListWidgetList[self.tabs.currentIndex()].count()):
            item = self.fileListWidgetList[self.tabs.currentIndex()].item(i)
            # lst.append(item.text())
            lst.append(item.data(99))  # by hw1230
        return lst

    def importDroppedImageFiles(self, imageFiles):
        extensions = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]

        self.filename = None
        for file in imageFiles:
            if file in self.imageList or not file.lower().endswith(
                    tuple(extensions)
            ):
                continue
            label_file = osp.splitext(file)[0] + ".json"
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = osp.join(self.output_dir, label_file_without_path)
            item = QtWidgets.QListWidgetItem(file)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
                    label_file
            ):
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.fileListWidgetList[self.tabs.currentIndex()].addItem(item)

        if len(self.imageList) > 1:
            self.actions.openNextImg.setEnabled(True)
            self.actions.openPrevImg.setEnabled(True)

        self.openNextImg()

    def importDirImages(self, tabIndex, dirpath, pattern=None, load=True):
        if not self.mayContinue() or not dirpath:
            return
        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)

        self.lastOpenDir = dirpath
        self.filename = None

        for filename in self.scanAllImages(dirpath):
            if pattern and pattern not in filename:
                continue

            # by hw1230
            ss = filename.split('.')
            if os.path.isfile(ss[0] + "_" + ss[1] + ".bak"):
                continue

            if filename.find(self.login_id) == -1 :
                continue

            label_file = osp.splitext(filename)[0] + ".json"
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = osp.join(self.output_dir, label_file_without_path)
            # item = QtWidgets.QListWidgetItem(filename)
            fn = filename.split(os.path.sep)  # by hw1230
            item = QtWidgets.QListWidgetItem(fn[-1])  # by hw1230
            item.setData(99, filename)  # by hw1230
            # item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # by hw1230
            # item.setCheckState(Qt.Unchecked)

            self.fileListWidgetList[tabIndex].addItem(item)
        self.openNextImg(load=load)

    def scanAllImages(self, folderPath):
        extensions = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        images = []
        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = osp.join(root, file)
                    images.append(relativePath)
        images.sort(key=lambda x: x.lower())
        return images

    def changeTabTitle(self):
        for i in range(0, 2):
            self.tabs.setTabText(i, tab_title[i] + " ({:,}건)".format(self.fileListWidgetList[i].count()))

    def tabChanged(self):
        ti = self.tabs.currentIndex()
        # print("ci=" + str(self.fileListWidgetList[ti].currentRow()))
        if self.fileListWidgetList[ti].count() > 0:
            if self.fileListWidgetList[ti].currentRow() == -1:
                self.fileListWidgetList[ti].setCurrentRow(0)
            self.fileSelectionChanged()
        else:
            self.resetState()

    # by hw1230
    def login(self):
        self.login_id = self.id.text().strip()

        if self.login_id == "":
            QMessageBox.warning(self, "", "전화번호를 입력하세요.", QMessageBox.Ok)
            return

        for i in range(0, 2):
            self.fileListWidgetList[i].clear()
            self.okListWidgetList[i].clear()
            self.rejectListWidgetList[i].clear()
            self.okBtnList[i].setEnabled(False)
            self.rejectBtnList[i].setEnabled(False)

            bucket_download_directory = down_directory_list[i]
    
            try:
                target_path = local_depository + local_directory_name[i] + r"\\"
                if type(bucket_download_directory) is list:
                    osh.download_directory_by_client(down_bucket_name_list[i], bucket_download_directory, target_path, self.login_id)
                else:
                    osh.download_directory_image(down_bucket_name_list[i], img_bucket_name, bucket_download_directory, target_path, self.login_id)

            except Exception as E:
                QMessageBox.warning(self, "", str(E), QMessageBox.Ok)
                return

            self.importDirImages(i, target_path)

            if self.fileListWidgetList[i].count() > 0:
                self.okBtnList[i].setEnabled(True)
                self.rejectBtnList[i].setEnabled(True)

            # localFiles = os.listdir(target_path)
            # for f in localFiles:
            #     if f.endswith(".bak"):
            #         ff = f.rsplit('.', 1)[0].rsplit('_', 1)
            #         item = QtWidgets.QListWidgetItem(ff[0] + "." + ff[1])
            #         # self.doneListWidget.addItem(item)
        self.changeTabTitle()

    def process(self, is_ok):       # is_ok : 승인 / 반려
        if not self.mayContinue():
            return

        ti = self.tabs.currentIndex()
        # print(ti)
        si = self.fileListWidgetList[ti].currentRow()
        fullPath = self.fileListWidgetList[ti].item(si).data(99)
        # print(fullPath)
        fileName = os.path.basename(fullPath)
        # print(fileName)
        upFile = os.path.splitext(fullPath)[0] + ".json"
        # print(upFile)

        log_bucket_name = down_bucket_name_list[ti]
        remain_num = self.fileListWidgetList[ti].count() - 1
        ok_num = self.okListWidgetList[ti].count()
        reject_num = self.rejectListWidgetList[ti].count()

        this_bucket_name = up_bucket_name  # 승인
        action_type = "승인 "
        if not is_ok:
            this_bucket_name = upnok_bucket_name  # 반려
            action_type = "반려 "
            reject_num = reject_num + 1
        else:
            ok_num = ok_num + 1

        if ti == 0:   # process03
            try:
                if os.path.isfile(upFile):
                    # json 업로드
                    osh.upload_object_simply(this_bucket_name, upFile, upFile.split(local_directory_name[ti] + r"\\")[1].replace(os.path.sep, "/"))
                    osh.log_by_bucket_name(local_depository + local_directory_name[ti] + r"\\",
                                           action_type + fileName + "\n" + self.login_id + " 잔여: %d건, 승인: %d건, 반려: %d건" % (remain_num, ok_num, reject_num), log_bucket_name)

                    # 로컬 .json 을 _json.bak 으로 변경
                    newName = osh.get_bak_file_name(upFile)
                    if os.path.isfile(newName):
                        os.remove(newName)
                    os.rename(upFile, newName)

                    # 로컬 이미지 삭제
                    os.remove(fullPath)
            except Exception as E:
                QMessageBox.warning(self, "", str(E), QMessageBox.Ok)
        else:       # process03-rework
            try:
                if os.path.isfile(upFile):
                    # json 업로드
                    osh.upload_object_simply(this_bucket_name, upFile, upFile.split(local_directory_name[ti] + r"\\")[1].replace(os.path.sep, "/"))
                    osh.log_by_bucket_name(local_depository + local_directory_name[ti] + r"\\",
                                           action_type + fileName + "\n" + self.login_id + " 잔여: %d건, 승인: %d건, 반려: %d건" % (remain_num, ok_num, reject_num), log_bucket_name)

                    # -rework json 삭제
                    osh.delete_object(down_bucket_name_list[1], upFile.split(local_directory_name[ti] + r"\\")[1].replace(os.path.sep, "/"))

                    os.remove(upFile)   # 로컬 json 삭제

                    # 로컬 이미지 삭제
                    os.remove(fullPath)
            except Exception as E:
                QMessageBox.warning(self, "", str(E), QMessageBox.Ok)

        item = QtWidgets.QListWidgetItem(fileName)
        if is_ok:
            self.okListWidgetList[ti].addItem(item)  # 승인 목록에 추가
        else:
            self.rejectListWidgetList[ti].addItem(item)  # 반려 목록에 추가
        self.fileListWidgetList[ti].takeItem(si)

        # 검수 목록이 비게 되면
        if self.fileListWidgetList[ti].count() == 0:
            self.resetState()
            self.okBtnList[ti].setEnabled(False)
            self.rejectBtnList[ti].setEnabled(False)

    def ok(self):
        self.process(True)
        ti = self.tabs.currentIndex()
        self.resultLabelList[ti][0].setText(result_title[0] + " ({:,}건)".format(self.okListWidgetList[ti].count()))
        self.changeTabTitle()

    def reject(self):
        self.process(False)
        ti = self.tabs.currentIndex()
        self.resultLabelList[ti][1].setText(result_title[1] + " ({:,}건)".format(self.rejectListWidgetList[ti].count()))
        self.changeTabTitle()

    # by hw1230
    def autoAnnotation(self):
        self.canvas.setEnabled(False)
        shapes = [
            {		"label": "num_tape",
                         "points": [
                             [
                                 566,
                                 1021
                             ],
                             [
                                 563,
                                 1027
                             ],
                             [
                                 563,
                                 1092
                             ],
                             [
                                 566,
                                 1098
                             ],
                             [
                                 568,
                                 1100
                             ],
                             [
                                 580,
                                 1100
                             ],
                             [
                                 593,
                                 1101
                             ],
                             [
                                 599,
                                 1102
                             ],
                             [
                                 604,
                                 1103
                             ],
                             [
                                 613,
                                 1106
                             ],
                             [
                                 622,
                                 1107
                             ],
                             [
                                 633,
                                 1107
                             ],
                             [
                                 637,
                                 1108
                             ],
                             [
                                 641,
                                 1109
                             ],
                             [
                                 651,
                                 1113
                             ],
                             [
                                 663,
                                 1116
                             ],
                             [
                                 669,
                                 1117
                             ],
                             [
                                 683,
                                 1117
                             ],
                             [
                                 715,
                                 1115
                             ],
                             [
                                 715,
                                 1114
                             ],
                             [
                                 717,
                                 1112
                             ],
                             [
                                 718,
                                 1109
                             ],
                             [
                                 719,
                                 1097
                             ],
                             [
                                 719,
                                 1028
                             ],
                             [
                                 716,
                                 1022
                             ],
                             [
                                 714,
                                 1020
                             ],
                             [
                                 569,
                                 1019
                             ]
                         ],

                         "shape_typ" : "polygon", "flag" : {}, "group_i" : None, "other_dat" : {}},
            {			"label": "g_tape",
                         "points": [
                             [
                                 623,
                                 1960
                             ],
                             [
                                 617,
                                 1963
                             ],
                             [
                                 615,
                                 1965
                             ],
                             [
                                 614,
                                 1965
                             ],
                             [
                                 613,
                                 1966
                             ],
                             [
                                 613,
                                 1967
                             ],
                             [
                                 611,
                                 1969
                             ],
                             [
                                 611,
                                 1977
                             ],
                             [
                                 612,
                                 1992
                             ],
                             [
                                 614,
                                 1996
                             ],
                             [
                                 615,
                                 2001
                             ],
                             [
                                 616,
                                 2006
                             ],
                             [
                                 616,
                                 2019
                             ],
                             [
                                 617,
                                 2031
                             ],
                             [
                                 618,
                                 2033
                             ],
                             [
                                 620,
                                 2036
                             ],
                             [
                                 622,
                                 2038
                             ],
                             [
                                 624,
                                 2039
                             ],
                             [
                                 736,
                                 2039
                             ],
                             [
                                 739,
                                 2036
                             ],
                             [
                                 740,
                                 2034
                             ],
                             [
                                 741,
                                 2032
                             ],
                             [
                                 741,
                                 1967
                             ],
                             [
                                 740,
                                 1965
                             ],
                             [
                                 739,
                                 1963
                             ],
                             [
                                 736,
                                 1960
                             ]
                         ],
                         "shape_typ" : "polygon", "flag" : {}, "group_i" : None, "other_dat" : {}},
            {			"label": "g_tape",
                         "points": [
                             [
                                 691,
                                 180
                             ],
                             [
                                 688,
                                 181
                             ],
                             [
                                 680,
                                 185
                             ],
                             [
                                 679,
                                 187
                             ],
                             [
                                 678,
                                 189
                             ],
                             [
                                 678,
                                 214
                             ],
                             [
                                 679,
                                 218
                             ],
                             [
                                 680,
                                 222
                             ],
                             [
                                 682,
                                 226
                             ],
                             [
                                 683,
                                 230
                             ],
                             [
                                 684,
                                 236
                             ],
                             [
                                 685,
                                 244
                             ],
                             [
                                 686,
                                 258
                             ],
                             [
                                 686,
                                 293
                             ],
                             [
                                 687,
                                 302
                             ],
                             [
                                 688,
                                 309
                             ],
                             [
                                 690,
                                 313
                             ],
                             [
                                 692,
                                 315
                             ],
                             [
                                 703,
                                 315
                             ],
                             [
                                 715,
                                 312
                             ],
                             [
                                 722,
                                 310
                             ],
                             [
                                 725,
                                 309
                             ],
                             [
                                 728,
                                 307
                             ],
                             [
                                 731,
                                 306
                             ],
                             [
                                 734,
                                 305
                             ],
                             [
                                 738,
                                 304
                             ],
                             [
                                 744,
                                 303
                             ],
                             [
                                 751,
                                 302
                             ],
                             [
                                 763,
                                 301
                             ],
                             [
                                 787,
                                 302
                             ],
                             [
                                 793,
                                 302
                             ],
                             [
                                 798,
                                 297
                             ],
                             [
                                 800,
                                 294
                             ],
                             [
                                 801,
                                 292
                             ],
                             [
                                 802,
                                 289
                             ],
                             [
                                 803,
                                 277
                             ],
                             [
                                 804,
                                 265
                             ],
                             [
                                 805,
                                 251
                             ],
                             [
                                 805,
                                 224
                             ],
                             [
                                 804,
                                 209
                             ],
                             [
                                 802,
                                 206
                             ],
                             [
                                 798,
                                 202
                             ],
                             [
                                 795,
                                 200
                             ],
                             [
                                 793,
                                 199
                             ],
                             [
                                 771,
                                 199
                             ],
                             [
                                 760,
                                 198
                             ],
                             [
                                 753,
                                 197
                             ],
                             [
                                 747,
                                 196
                             ],
                             [
                                 744,
                                 195
                             ],
                             [
                                 741,
                                 194
                             ],
                             [
                                 731,
                                 188
                             ],
                             [
                                 729,
                                 187
                             ],
                             [
                                 719,
                                 183
                             ],
                             [
                                 715,
                                 182
                             ],
                             [
                                 710,
                                 181
                             ],
                             [
                                 700,
                                 180
                             ]
                         ],
                         "shape_typ" : "polygon", "flag" : {}, "group_i" : None, "other_dat" : {}}
        ]
        self.canvas.isAuto = True
        self.loadLabels(shapes, False)
        self.actions.autoAnnotation.setEnabled(False)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)
        self.canvas.setEnabled(True)
        self.paintCanvas()
        self.toggleActions(True)
        self.canvas.setFocus()
