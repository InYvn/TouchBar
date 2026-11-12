#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TouchBar 插件入口 —— 由宿主（Mipad DP Touch）动态加载。

宿主约定（api = 1）：
    mod = <import touchbar_plugin>
    ctl = mod.create(on_hide=..., log=...)
    ctl.show() / ctl.hide() / ctl.toggle() / ctl.is_visible
    ctl.set_auto(True) / ctl.tick()      # tick 由宿主定时器驱动
    ctl.close()                          # 卸载前收尾

插件不自带菜单栏 / Dock 入口，也不检查权限：权限是宿主进程的事。
"""

import json
import os

from .bar import Bar

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_MANIFEST = os.path.join(os.path.dirname(_PKG_DIR), "plugin.json")


def meta():
    try:
        with open(_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class Controller:
    def __init__(self, on_hide=None, log=None):
        self._on_hide = on_hide
        self._log = log or (lambda *_: None)
        self.bar = Bar(log=self._log)

    @property
    def is_visible(self):
        return self.bar.visible

    def show(self):
        self.bar.show()

    def hide(self):
        self.bar.hide()
        if self._on_hide:
            self._on_hide()

    def toggle(self):
        if self.bar.visible:
            self.hide()
        else:
            self.show()

    def set_auto(self, _flag):
        """宿主兼容用：本插件不跟随输入焦点，无需自动显隐。"""

    def tick(self):
        self.bar.tick_(None)

    def close(self):
        self.bar.close()


def create(on_hide=None, log=None):
    return Controller(on_hide=on_hide, log=log)
