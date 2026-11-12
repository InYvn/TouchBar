#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TouchBar —— 跟随前台 App 的浮动工具栏。

一条浮在屏幕上的条子，内容来自前台 App 自己的 AX 工具栏：
按钮标题、启用状态、分组都照搬，点一下走 AXPress 执行真实动作。

同一份代码两种用法：
  * 独立 App：`python src/touchbar.py`（菜单栏常驻，可退出）
  * 插件：`plugin/__init__.py` 的 create() 返回控制器，由宿主驱动
"""

import json
import os

import ApplicationServices as AS
from AppKit import (
    NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
    NSButton, NSColor, NSEvent, NSFont, NSFloatingWindowLevel, NSImage,
    NSImageSymbolConfiguration, NSImageView, NSMakeRect, NSMenu, NSMenuItem,
    NSPanel, NSScreen, NSStatusBar, NSTextField, NSTimer, NSView,
    NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel, NSWorkspace,
)

BAR_H = 56.0
PAD = 8.0
BTN = 44.0
GAP = 4.0
MAX_BTN = 10
EDGE = 24.0
TAB_W, TAB_H = 14.0, 92.0
OPACITIES = (1.0, 0.85, 0.70, 0.55)
DEFAULT_STATE = os.path.expanduser("~/Library/Application Support/TouchBar/state.json")

SYSTEM_GROUP = [
    ("speaker.wave.1", "vol-", "音量 -"),
    ("speaker.wave.3", "vol+", "音量 +"),
    ("speaker.slash", "mute", "静音"),
]

SYMBOLS = [
    (("返回", "back"), "chevron.left"),
    (("前进", "forward"), "chevron.right"),
    (("刷新", "reload"), "arrow.clockwise"),
    (("共享", "share"), "square.and.arrow.up"),
    (("搜索", "search"), "magnifyingglass"),
    (("添加", "新建", "add", "new"), "plus"),
    (("删除", "delete", "trash"), "trash"),
    (("编辑", "edit"), "pencil"),
    (("标签", "tag"), "tag"),
    (("群组", "group"), "folder.badge.gearshape"),
    (("操作", "action", "more"), "ellipsis.circle"),
    (("保存", "save"), "square.and.arrow.down"),
    (("打印", "print"), "printer"),
    (("撤消", "撤销", "undo"), "arrow.uturn.backward"),
    (("重做", "redo"), "arrow.uturn.forward"),
    (("图标", "icon"), "square.grid.2x2"),
    (("列表", "list"), "list.bullet"),
    (("分栏", "column"), "rectangle.split.3x1"),
    (("画廊", "gallery"), "rectangle.grid.1x2"),
    (("日历", "calendar"), "calendar"),
    (("收件箱", "inbox"), "tray"),
    (("播放", "play"), "play.fill"),
    (("暂停", "pause"), "pause.fill"),
    (("设置", "settings"), "gearshape"),
]
TEXT_ONLY = {"日", "周", "月", "年", "今天"}


def symbol_for(label):
    low = (label or "").lower()
    for keys, sym in SYMBOLS:
        for k in keys:
            if k and k.lower() in low:
                return sym
    return None


def attr(el, name):
    err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def kids(el):
    v = attr(el, "AXChildren")
    return list(v) if v else []


def find_role(el, role, depth=0, budget=None):
    budget = budget if budget is not None else [400]
    if depth > 6 or budget[0] <= 0:
        return None
    for ch in kids(el):
        budget[0] -= 1
        if attr(ch, "AXRole") == role:
            return ch
        got = find_role(ch, role, depth + 1, budget)
        if got is not None:
            return got
    return None


def collect(el):
    out = []
    for gi, top in enumerate(kids(el)):
        stack = [(top, 0)]
        while stack and len(out) < MAX_BTN * 3:
            node, d = stack.pop()
            if d > 4:
                continue
            role = attr(node, "AXRole") or ""
            label = ((attr(node, "AXTitle") or "") or (attr(node, "AXDescription") or "")).strip()
            label = label.replace("\n", " ")
            if role in ("AXButton", "AXMenuButton", "AXCheckBox", "AXRadioButton") and label:
                out.append((label, bool(attr(node, "AXEnabled")), node, gi))
            for ch in reversed(kids(node)):
                stack.append((ch, d + 1))
    return out


def front_toolbar():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None, []
    axapp = AS.AXUIElementCreateApplication(app.processIdentifier())
    wins = attr(axapp, "AXWindows") or []
    main = attr(axapp, "AXMainWindow")
    for w in ([main] if main is not None else []) + list(wins):
        tb = find_role(w, "AXToolbar")
        if tb is not None:
            items = collect(tb)
            if items:
                return app, items[:MAX_BTN]
    return app, []


def screen_under_mouse():
    p = NSEvent.mouseLocation()
    for s in NSScreen.screens():
        f = s.frame()
        if (f.origin.x <= p.x <= f.origin.x + f.size.width
                and f.origin.y <= p.y <= f.origin.y + f.size.height):
            return s
    return NSScreen.mainScreen()


def sym_image(name, size=18.0):
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if img is None:
        return None
    try:
        img = img.imageWithSymbolConfiguration_(
            NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, 0.0))
    except Exception:
        pass
    return img


def osa(script):
    import subprocess
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()


def sys_key(action):
    if action == "mute":
        muted = osa("output muted of (get volume settings)") == "true"
        osa("set volume without output muted" if muted else "set volume with output muted")
        return
    try:
        vol = int(osa("output volume of (get volume settings)") or 0)
    except ValueError:
        vol = 0
    osa("set volume output volume %d" % max(0, min(100, vol + (6 if action == "vol+" else -6))))


class PassThrough(NSImageView):
    """只画图标，不参与命中测试 —— 让父视图拿到拖动事件。"""

    def hitTest_(self, point):
        return None


class BarView(NSView):
    """空白处可拖动；松手后由 Bar 决定是否吸附。"""

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        self._origin = NSEvent.mouseLocation()
        self._frame = self.window().frame().origin

    def mouseDragged_(self, event):
        if not getattr(self, "_origin", None):
            return
        p = NSEvent.mouseLocation()
        self.window().setFrameOrigin_((self._frame.x + p.x - self._origin.x,
                                       self._frame.y + p.y - self._origin.y))

    def mouseUp_(self, event):
        self._origin = None
        self.bar.snap_or_save()


class Bar:
    def __init__(self, state_path=None, log=None):
        self.state_path = state_path or DEFAULT_STATE
        self.log = log or (lambda *_: None)
        self.state = self.load()
        self.opacity = self.state.get("opacity", 1.0)
        self.docked = self.state.get("docked")
        self.pos = tuple(self.state.get("pos") or (0, 0))
        self.items = []
        self.sig = None
        self.visible = True

        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 480, BAR_H),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setCollectionBehavior_(1 | 256)
        self.panel.setAlphaValue_(self.opacity)
        self.view = BarView.alloc().initWithFrame_(NSMakeRect(0, 0, 480, BAR_H))
        self.view.bar = self
        self.view.setWantsLayer_(True)
        self.panel.setContentView_(self.view)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.6, self, "tick:", None, True)

    # ---------------------------------------------------------------- 状态
    def load(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"opacity": self.opacity, "docked": self.docked,
                           "pos": list(self.pos)}, f)
        except Exception as exc:
            self.log("state save failed: %r" % (exc,))

    # ---------------------------------------------------------------- 显隐
    def show(self):
        self.visible = True
        if self.docked:
            self.build_tab()
        else:
            app, items = front_toolbar()
            self.rebuild(app, items)

    def hide(self):
        self.visible = False
        self.panel.orderOut_(None)

    def toggle(self):
        self.hide() if self.visible else self.show()

    def close(self):
        try:
            self.timer.invalidate()
        except Exception:
            pass
        self.panel.orderOut_(None)
        self.panel.close()

    # ---------------------------------------------------------------- 刷新
    def tick_(self, _t):
        if self.docked or not self.visible:
            return
        app, items = front_toolbar()
        sig = (app.localizedName() if app else "", tuple((i[0], i[1]) for i in items))
        if sig == self.sig:
            return
        self.sig = sig
        self.rebuild(app, items)

    def _style(self):
        layer = self.view.layer()
        layer.setCornerRadius_(14.0 if not self.docked else 7.0)
        layer.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.10, 0.94).CGColor())
        layer.setBorderWidth_(1.0)
        layer.setBorderColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.10).CGColor())

    def _btn(self, x, y, w, h, symbol=None, text=None, enabled=True, tooltip="", action="press:"):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        if symbol:
            img = sym_image(symbol, 18.0)
            if img is not None:
                b.setImage_(img)
                b.setImagePosition_(1)
        if text:
            b.setTitle_(text)
            b.setFont_(NSFont.systemFontOfSize_(11.0))
            try:
                b.cell().setLineBreakMode_(4)
            except Exception:
                pass
        else:
            b.setTitle_("")
        b.setContentTintColor_(NSColor.whiteColor() if enabled
                               else NSColor.colorWithCalibratedWhite_alpha_(1, 0.32))
        b.setBordered_(False)
        b.setToolTip_(tooltip)
        b.setEnabled_(enabled)
        b.setTarget_(self)
        b.setAction_(action)
        b.setWantsLayer_(True)
        b.layer().setCornerRadius_(9.0)
        b.layer().setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.06).CGColor())
        self.view.addSubview_(b)
        return b

    def _sep(self, x):
        sep = NSView.alloc().initWithFrame_(NSMakeRect(x, 14, 1, BAR_H - 28))
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.14).CGColor())
        self.view.addSubview_(sep)

    def build_tab(self):
        for v in list(self.view.subviews()):
            v.removeFromSuperview()
        w, h = (TAB_W, TAB_H) if self.docked in ("left", "right") else (TAB_H, TAB_W)
        self.panel.setFrame_display_(NSMakeRect(0, 0, w, h), True)
        self.view.setFrame_(NSMakeRect(0, 0, w, h))
        self._style()
        arrow = {"left": "chevron.right", "right": "chevron.left", "bottom": "chevron.up"}[self.docked]
        b = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        img = sym_image(arrow, 11.0)
        if img is not None:
            b.setImage_(img)
            b.setImagePosition_(1)
        b.setBordered_(False)
        b.setTitle_("")
        b.setContentTintColor_(NSColor.colorWithCalibratedWhite_alpha_(1, 0.75))
        b.setTarget_(self)
        b.setAction_("undock:")
        self.view.addSubview_(b)
        self.place_tab()
        if not self.visible:
            self.panel.orderOut_(None)

    def place_tab(self):
        scr = screen_under_mouse().visibleFrame()
        w = self.panel.frame().size.width
        h = self.panel.frame().size.height
        if self.docked == "left":
            origin = (scr.origin.x, scr.origin.y + (scr.size.height - h) / 2)
        elif self.docked == "right":
            origin = (scr.origin.x + scr.size.width - w, scr.origin.y + (scr.size.height - h) / 2)
        else:
            origin = (scr.origin.x + (scr.size.width - w) / 2, scr.origin.y)
        self.panel.setFrameOrigin_(origin)
        self.panel.orderFrontRegardless()

    def rebuild(self, app, items):
        for v in list(self.view.subviews()):
            v.removeFromSuperview()
        self.items = items
        self._els = {}
        x = PAD

        grip = PassThrough.alloc().initWithFrame_(NSMakeRect(x, (BAR_H - 18) / 2, 14, 18))
        gimg = sym_image("line.3.horizontal", 13.0)
        if gimg is not None:
            grip.setImage_(gimg)
            grip.setContentTintColor_(NSColor.colorWithCalibratedWhite_alpha_(1, 0.35))
        self.view.addSubview_(grip)
        x += 14 + 6

        if app is not None:
            icon = NSWorkspace.sharedWorkspace().iconForFile_(app.bundleURL().path())
            if icon is not None:
                icon.setSize_((22.0, 22.0))
                iv = NSImageView.alloc().initWithFrame_(NSMakeRect(x, (BAR_H - 22) / 2, 22, 22))
                iv.setImage_(icon)
                self.view.addSubview_(iv)
                x += 22 + 8

        if not items:
            lab = NSTextField.labelWithString_("%s · 无工具栏" % (app.localizedName() if app else ""))
            lab.setFrame_(NSMakeRect(x, (BAR_H - 20) / 2, 190, 20))
            lab.setTextColor_(NSColor.secondaryLabelColor())
            lab.setFont_(NSFont.systemFontOfSize_(12.0))
            self.view.addSubview_(lab)
            x += 200
        else:
            last_group = items[0][3]
            for i, (label, enabled, el, gi) in enumerate(items):
                if gi != last_group:
                    self._sep(x + 3)
                    x += 9
                    last_group = gi
                sym = None if label in TEXT_ONLY else symbol_for(label)
                b = self._btn(x, (BAR_H - BTN) / 2, BTN, BTN, symbol=sym,
                              text=None if sym else label[:6], enabled=enabled, tooltip=label)
                b.setTag_(i)
                self._els[i] = el
                x += BTN + GAP

        x += 6
        self._sep(x)
        x += 9
        for si, (sym, code, tip) in enumerate(SYSTEM_GROUP):
            b = self._btn(x, (BAR_H - BTN) / 2, BTN, BTN, symbol=sym, tooltip=tip, action="systemKey:")
            b.setTag_(si)
            x += BTN + GAP

        x += 4
        self._btn(x, (BAR_H - BTN) / 2, BTN, BTN, symbol="circle.lefthalf.filled",
                  tooltip="不透明度 %d%%" % round(self.opacity * 100), action="cycleOpacity:")
        x += BTN + GAP
        self._btn(x, (BAR_H - BTN) / 2, BTN, BTN, symbol="sidebar.right",
                  tooltip="收纳到侧边", action="dockNearest:")
        x += BTN + PAD

        w = max(x, 200)
        self.panel.setFrame_display_(NSMakeRect(0, 0, w, BAR_H), True)
        self.view.setFrame_(NSMakeRect(0, 0, w, BAR_H))
        self._style()
        self.restore_position(w)
        if not self.visible:
            self.panel.orderOut_(None)

    def restore_position(self, w):
        scr = screen_under_mouse().visibleFrame()
        x, y = self.pos
        if not x and not y:
            x = scr.origin.x + (scr.size.width - w) / 2
            y = scr.origin.y + 20
        x = min(max(x, scr.origin.x), scr.origin.x + scr.size.width - w)
        y = min(max(y, scr.origin.y), scr.origin.y + scr.size.height - BAR_H)
        self.panel.setFrameOrigin_((x, y))
        self.panel.orderFrontRegardless()

    # ---------------------------------------------------------------- 位置
    def snap_or_save(self):
        scr = screen_under_mouse().visibleFrame()
        f = self.panel.frame()
        x, y = f.origin.x, f.origin.y
        if x <= scr.origin.x + EDGE:
            return self.dock("left")
        if x + f.size.width >= scr.origin.x + scr.size.width - EDGE:
            return self.dock("right")
        if y <= scr.origin.y + EDGE:
            return self.dock("bottom")
        self.pos = (x, y)
        self.save()

    def dock(self, side):
        self.pos = (self.panel.frame().origin.x, self.panel.frame().origin.y)
        self.docked = side
        self.save()
        self.build_tab()

    def undock_(self, _sender):
        self.docked = None
        self.save()
        self.sig = None
        app, items = front_toolbar()
        self.rebuild(app, items)

    def dockNearest_(self, _sender):
        scr = screen_under_mouse().visibleFrame()
        f = self.panel.frame()
        cx = f.origin.x + f.size.width / 2
        cy = f.origin.y + f.size.height / 2
        d = {"left": cx - scr.origin.x,
             "right": scr.origin.x + scr.size.width - cx,
             "bottom": cy - scr.origin.y}
        self.dock(min(d, key=d.get))

    def cycleOpacity_(self, _sender):
        i = OPACITIES.index(self.opacity) if self.opacity in OPACITIES else 0
        self.opacity = OPACITIES[(i + 1) % len(OPACITIES)]
        self.panel.setAlphaValue_(self.opacity)
        self.save()
        self.sig = None

    def press_(self, sender):
        el = self._els.get(sender.tag())
        if el is None:
            return
        err = AS.AXUIElementPerformAction(el, "AXPress")
        self.log("press %s -> %d" % (sender.toolTip(), err))
        self.sig = None

    def systemKey_(self, sender):
        sys_key(SYSTEM_GROUP[sender.tag()][1])


# ---------------------------------------------------------------- 独立 App
def run_standalone():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    bar = Bar()

    status = NSStatusBar.systemStatusBar().statusItemWithLength_(-1)
    img = sym_image("rectangle.topthird.inset.filled", 16.0)
    if img is not None:
        status.button().setImage_(img)
    menu = NSMenu.alloc().init()
    for title, action in (("显示 / 隐藏", "toggle:"), ("回到屏幕中央", "recenter:"),
                          ("退出", "quit:")):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(app.delegate() if app.delegate() else None)
        menu.addItem_(item)
    status.setMenu_(menu)

    class _Menu:
        def toggle_(self, _s):
            bar.toggle()

        def recenter_(self, _s):
            bar.pos = (0, 0)
            bar.docked = None
            bar.save()
            app, items = front_toolbar()
            bar.rebuild(app, items)

        def quit_(self, _s):
            bar.close()
            NSApplication.sharedApplication().terminate_(None)

    handler = _Menu()
    for item in menu.itemArray():
        item.setTarget_(handler)
    app._handler = handler

    bar.show()
    app.run()


def selftest():
    """无 UI 自检：符号映射、状态持久化、AX 读取不崩。"""
    NSApplication.sharedApplication()
    assert symbol_for("返回") == "chevron.left"
    assert symbol_for("Share") == "square.and.arrow.up"
    assert symbol_for("随便一个没映射的名字") is None
    print("ok symbol mapping")

    import tempfile
    tmp = tempfile.mkdtemp(prefix="tb-selftest-")
    state = os.path.join(tmp, "state.json")
    bar = Bar(state_path=state)
    bar.opacity = 0.7
    bar.docked = "left"
    bar.pos = (10, 20)
    bar.save()
    again = Bar(state_path=state)
    assert abs(again.opacity - 0.7) < 1e-6 and again.docked == "left" and again.pos == (10, 20)
    print("ok state round-trip")

    app, items = front_toolbar()
    print("ok ax probe: app=%r items=%d" % (app.localizedName() if app else None, len(items)))
    bar.close()
    again.close()
    print("SELFTEST OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_standalone()
