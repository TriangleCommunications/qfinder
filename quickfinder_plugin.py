from __future__ import absolute_import
#-----------------------------------------------------------
#
# QGIS Quick Finder Plugin
# Copyright (C) 2013 Denis Rouzaud
#
#-----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
#---------------------------------------------------------------------

import os.path
from qgis.PyQt.QtCore import Qt, QObject, QSettings, QCoreApplication, QTranslator, QUrl, pyqtSlot
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon, QColor, QDesktopServices
from qgis.gui import QgsRubberBand
from qgis.core import Qgis

from .core.project_finder import ProjectFinder, n_days_ago_iso_date
#from .core.osm_finder import OsmFinder
#from .core.geomapfish_finder import GeomapfishFinder
#from .core.postgis_finder import PostgisFinder
from .core.my_settings import MySettings
from .gui.configuration_dialog import ConfigurationDialog
from .gui.refresh_dialog import RefreshDialog
from .gui.finder_box import FinderBox

from . import resources_rc


class QuickFinder(QObject):

    name = u"&Quick Finder"
    actions = None
    toolbar = None
    finders = {}

    loadingIcon = None

    def __init__(self, iface):
        QObject.__init__(self)
        self.iface = iface
        self.actions = {}
        self.finders = {}
        self.settings = MySettings()
        self.rubber = None

        self._init_finders()

        self.iface.projectRead.connect(self._reload_finders)
        self.iface.newProjectCreated.connect(self._reload_finders)

        # translation environment
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value("locale/userLocale")[0:2]
        localePath = os.path.join(self.plugin_dir, 'i18n', 'quickfinder_{0}.qm'.format(locale))
        if os.path.exists(localePath):
            self.translator = QTranslator()
            self.translator.load(localePath)
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        self.actions['showSettings'] = QAction(
            QIcon(":/plugins/quickfinder/icons/settings.svg"),
            self.tr(u"&Settings"),
            self.iface.mainWindow())
        self.actions['showSettings'].triggered.connect(self.show_settings)
        self.iface.addPluginToMenu(self.name, self.actions['showSettings'])
        self._init_toolbar()

        # set selection area sytle and color
        self.rubber = QgsRubberBand(self.iface.mapCanvas())
        self.rubber.setColor(QColor(255, 255, 50, 200))
        self.rubber.setIcon(self.rubber.ICON_CIRCLE)
        self.rubber.setIconSize(15)
        self.rubber.setWidth(4)
        self.rubber.setBrushStyle(Qt.NoBrush)

    def unload(self):
        """ Unload plugin """
        for key in list(self.finders.keys()):
            self.finders[key].close()
        for action in self.actions.values():
            self.iface.removePluginMenu(self.name, action)
        if self.toolbar:
            del self.toolbar
        if self.rubber:
            self.iface.mapCanvas().scene().removeItem(self.rubber)
            del self.rubber

    def _init_toolbar(self):
        """setup the plugin toolbar."""
        self.toolbar = self.iface.addToolBar(self.name)
        self.toolbar.setObjectName('mQuickFinderToolBar')
        self.search_action = QAction(QIcon(":/plugins/quickfinder/icons/magnifier13.svg"), self.tr("Search"), self.toolbar)
        self.stop_action = QAction(QIcon(":/plugins/quickfinder/icons/wrong2.svg"), self.tr("Cancel"), self.toolbar)
        self.finder_box = FinderBox(self.finders, self.iface, self.toolbar)
        self.finder_box.search_started.connect(self.search_started)
        self.finder_box.search_finished.connect(self.search_finished)
        self.finder_box_action = self.toolbar.addWidget(self.finder_box)
        self.finder_box_action.setVisible(True)
        self.search_action.triggered.connect(self.finder_box.search)
        self.toolbar.addAction(self.search_action)
        self.stop_action.setVisible(False)
        self.stop_action.triggered.connect(self.finder_box.stop)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.setVisible(True)

    def _init_finders(self):
#        self.finders['geomapfish'] = GeomapfishFinder(self)
#        self.finders['osm'] = OsmFinder(self)
        self.finders['project'] = ProjectFinder(self)
#        self.finders['postgis'] = PostgisFinder(self)
        for key in list(self.finders.keys()):
            self.finders[key].message.connect(self.display_message)
        self.refresh_project()

    def _reload_finders(self):
        for key in list(self.finders.keys()):
            self.finders[key].close()
            self.finders[key].reload()
        self.refresh_project()

    @pyqtSlot(str, Qgis.MessageLevel)
    def display_message(self, message, level):
        self.iface.messageBar().pushMessage("QuickFinder", message, level)

    def show_settings(self):
#        self.win = ConfigurationDialog()
#        self.win.show()
        #ConfigurationDialog().show()
        if ConfigurationDialog().exec_():
            self._reload_finders()

    def search_started(self):
        self.search_action.setVisible(False)
        self.stop_action.setVisible(True)

    def search_finished(self):
        self.search_action.setVisible(True)
        self.stop_action.setVisible(False)

    def refresh_project(self):
        if not self.finders['project'].activated:
            return
        if not self.settings.value("refreshAuto"):
            return
        n_days = self.settings.value("refreshDelay")
        # do not ask more ofen than 3 days
        ask_limit = min(3, n_days)
        recently_asked = self.settings.value("refreshLastAsked") >= n_days_ago_iso_date(ask_limit)
        if recently_asked:
            return
        thresh_date = n_days_ago_iso_date(n_days)
        uptodate = True
        for search in list(self.finders['project'].searches.values()):
            if search.dateEvaluated <= thresh_date:
                uptodate = False
                break
        if uptodate:
            return
        self.settings.setValue("refreshLastAsked", n_days_ago_iso_date(0))
        ret = QMessageBox(QMessageBox.Warning,
                          "Quick Finder",
                          QCoreApplication.translate("Auto Refresh", "Some searches are outdated. Do you want to refresh them ?"),
                          QMessageBox.Cancel | QMessageBox.Yes).exec_()
        if ret == QMessageBox.Yes:
            RefreshDialog(self.finders['project']).exec_()



