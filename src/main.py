"""小小笨狗 · 桌面宠物

行为：整个显示器范围活动；大部分时间睡觉，偶尔醒来朝鼠标爬过去；点击喊痛，可拖拽。
"""
import json
import math
import os
import random
import sys
import time
from datetime import datetime

# 打包后需要先把 Qt 的 DLL 目录注册进搜索路径，否则 QtCore 加载失败
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    for _sub in (os.path.join(_exe_dir, "_internal", "PyQt6", "Qt6", "bin"),
                 os.path.join(_exe_dir, "_internal")):
        if os.path.isdir(_sub):
            try:
                os.add_dll_directory(_sub)
            except Exception:
                pass

# 双 Qt 兼容：安卓用 PySide6，桌面用 PyQt6
try:
    from PySide6.QtCore import QPoint, QProcess, QRect, Qt, QTimer, QUrl
    from PySide6.QtGui import (QBitmap, QCursor, QGuiApplication, QImage, QPainter,
                               QPixmap, QRegion, QTransform)
    from PySide6.QtMultimedia import QSoundEffect
    from PySide6.QtWidgets import QApplication, QMenu, QWidget
    QT_BINDING = "PySide6"
except ImportError:
    from PyQt6.QtCore import QPoint, QProcess, QRect, Qt, QTimer, QUrl
    from PyQt6.QtGui import (QBitmap, QCursor, QGuiApplication, QImage, QPainter,
                             QPixmap, QRegion, QTransform)
    from PyQt6.QtMultimedia import QSoundEffect
    from PyQt6.QtWidgets import QApplication, QMenu, QWidget
    QT_BINDING = "PyQt6"

if getattr(sys, "frozen", False):
    # PyInstaller 打包后，__file__ 在临时目录，资源要跟着 exe 走
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = (os.path.join(BASE, "assets", "final")
          if os.path.isdir(os.path.join(BASE, "assets", "final"))
          else r"D:\DSH\pet_assets\final")
VOICE = (os.path.join(BASE, "assets", "voice")
         if os.path.isdir(os.path.join(BASE, "assets", "voice"))
         else r"D:\DSH\pet_assets\voice\baked")

POSE_FILES = {
    "idle": "idle_front.png",
    "crawl": "crawl_side.png",
    "crawl_front": "crawl_front.png",
    "crawl_back": "crawl_back.png",
    "sit": "sit.png",
    "sleep": "sleep.png",
    "hit": "hit.png",
    "drag": "drag.png",
    "land": "land.png",
    "eat": "eat.png",
    "pet_head": "pet_head.png",
    "poke": "poke.png",
    "pick": "pick.png",
    "pinch": "pinch.png",
    "hug": "hug.png",
    "tickle": "tickle.png",
    "peek": "peek.png",

}





class FrameSeq:
    """一段动画：像列表一样用，但帧在读取时才解码。"""

    def __init__(self, store, name, files, kind="plain"):
        self.store = store
        self.name = name
        self.files = files
        self.kind = kind
        n = len(files)
        self._n = (2 * n - 2) if kind in ("pingpong", "pingpong_mirror") and n > 1 else n

    def __len__(self):
        return self._n

    def _map(self, i):
        n = len(self.files)
        if self.kind == "reverse":
            return n - 1 - i, False
        if self.kind == "pingpong" and i >= n:
            return 2 * n - 2 - i, False
        if self.kind == "pingpong_mirror":
            return (i if i < n else 2 * n - 2 - i), True
        return i, self.kind == "mirror"

    def __getitem__(self, i):
        if i < 0:
            i += self._n
        if i < 0 or i >= self._n:
            raise IndexError(i)
        return self.store.frame(self.name, i, self)


class AnimStore:
    """动画仓库：帧按需解码，全局只保留 MAXF 帧（约 170 MB 上限）。"""

    MAXF = 110

    def __init__(self, dpr):
        self.dpr = dpr
        self.files = {}
        self.spec = {}
        self.seqs = {}
        self.cache = {}          # (name, idx) -> QPixmap
        self._order = []

    def add(self, name, files):
        self.files[name] = files
        self.spec[name] = ("plain", name)

    def add_derived(self, name, base, kind):
        if base in self.files:
            self.spec[name] = (kind, base)

    def __contains__(self, name):
        return name in self.spec

    def keys(self):
        return self.spec.keys()

    def get(self, name, default=None):
        if name not in self.spec:
            return default
        return self[name]

    def __getitem__(self, name):
        if name not in self.spec:
            raise KeyError(name)
        seq = self.seqs.get(name)
        if seq is None:
            kind, base = self.spec[name]
            seq = FrameSeq(self, name, self.files[base], kind)
            self.seqs[name] = seq
            print(f"[anim] ready {name}: {len(seq)} frames", flush=True)
        return seq

    def frame(self, name, i, seq):
        key = (name, i)
        pm = self.cache.get(key)
        if pm is not None:
            return pm
        src, mirror = seq._map(i)
        pm = QPixmap(seq.files[src])
        pm.setDevicePixelRatio(self.dpr)
        if mirror:
            pm = pm.transformed(QTransform().scale(-1, 1))
            pm.setDevicePixelRatio(self.dpr)
        self.cache[key] = pm
        self._order.append(key)
        while len(self._order) > self.MAXF:
            old = self._order.pop(0)
            if old != (name, i):
                self.cache.pop(old, None)
        return pm


class GhostWindow(QWidget):
    """睡梦中出现的幽灵：淡入 → 停留 → 淡出，不接收鼠标事件"""

    PEAK = 0.45

    def __init__(self, pm):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.pm = pm
        sz = pm.deviceIndependentSize()
        self.setFixedSize(int(sz.width()), int(sz.height()))
        self.setWindowOpacity(0.0)
        self._t = 0.0
        self._hold = 6.0
        self._phase = "idle"
        self._drift_from = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    def start(self, hold=6.0):
        self._phase, self._t, self._hold = "in", 0.0, hold
        self.setWindowOpacity(0.0)
        self.show()
        if not self.timer.isActive():
            self.timer.start(40)

    def stop(self):
        self.timer.stop()
        self._phase = "idle"
        self.hide()

    def _step(self):
        self._t += 0.04
        if self._phase == "in":
            o = min(1.0, self._t / 1.2)
            self.setWindowOpacity(self.PEAK * o)
            if self._drift_from is not None:
                e = o * o * (3 - 2 * o)
                fx, fy = self._drift_from
                self.move(int(fx + (self._base_x - fx) * e),
                          int(fy + (self._base_y - fy) * e))
            if self._t >= 1.2:
                self._phase, self._t = "hold", 0.0
        elif self._phase == "hold":
            # 左右轻摆 + 上下浮动 + 明暗呼吸
            self.move(self._base_x + int(math.sin(self._t * 0.75) * 7),
                      self._base_y + int(math.sin(self._t * 1.25) * 5))
            self.setWindowOpacity(self.PEAK * (0.86 + 0.14 * math.sin(self._t * 1.6)))
            if self._t >= self._hold:
                self._phase, self._t = "out", 0.0
        else:
            o = max(0.0, 1.0 - self._t / 1.4)
            self.setWindowOpacity(self.PEAK * o)
            if o <= 0.0:
                self.stop()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self.pm)


class Pet(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._load_sprites(cfg["sprite_height"])
        self._load_voices()
        self._load_anim()
        self._load_ghosts()
        self._load_mitten()
        self._load_cushion()
        self._load_hands()
        self._load_cling()
        self._load_mitten_cursor()
        self.loop_t = 0.0
        self.state_start = time.monotonic()

        self.state_pose = "idle"
        self.state = "idle"
        self.state_until = time.monotonic() + 2.0
        self.prev_state = "idle"
        self.cycles = 0
        self.fx = 0.0
        self.fy = 0.0
        self.tx = 0.0
        self.ty = 0.0
        self.vy = 0.0
        self.bob_t = 0.0
        self.dragging = False
        self._press_pos = None
        self._press_time = 0.0
        self._follow = QPoint(0, 0)
        self._speak_at = 0.0
        self._click_times = []

        self._place_initial()
        self.set_pose("idle")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(16, int(cfg.get("frame_ms", 33))))

    # ---------- 资源 ----------
    def _load_sprites(self, target_h):
        raw = QPixmap(os.path.join(ASSETS, POSE_FILES["idle"]))
        scale = target_h / raw.height()
        self.W = int(round(raw.width() * scale))
        self.H = int(target_h)
        self.pad = int(round(8 * scale))  # final/ 底部留的 8px 余量
        # 高 DPI：按物理像素加载，再标注 devicePixelRatio，避免拉伸发虚
        self.dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        pw, ph = int(round(self.W * self.dpr)), int(round(self.H * self.dpr))
        self.pix = {}
        self.mask_pix = {}
        for k, f in POSE_FILES.items():
            src = QPixmap(os.path.join(ASSETS, f))
            self.mask_pix[k] = src.scaled(self.W, self.H,
                                          Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            pm = src.scaled(pw, ph,
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(self.dpr)
            self.pix[k] = pm
        self.pix["crawl_l"] = self.pix["crawl"].transformed(QTransform().scale(-1, 1))
        self.pix["crawl_l"].setDevicePixelRatio(self.dpr)
        self.mask_pix["crawl_l"] = self.mask_pix["crawl"].transformed(QTransform().scale(-1, 1))

        # 探头用的独立头部贴图（比全身图窄，单独一个窗口尺寸）
        self.head_h = int(round(self.H * 0.62))
        hp = QPixmap(os.path.join(ASSETS, "peek_head.png"))
        hw = int(round(hp.width() * self.head_h / hp.height()))
        self.head_w = hw
        self.head_pix = hp.scaled(int(hw * self.dpr), int(self.head_h * self.dpr),
                                  Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        self.head_pix.setDevicePixelRatio(self.dpr)
        self.head_mask = hp.scaled(hw, self.head_h,
                                   Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.head_pix_l = self.head_pix.transformed(QTransform().scale(-1, 1))
        self.head_pix_l.setDevicePixelRatio(self.dpr)
        self.head_mask_l = self.head_mask.transformed(QTransform().scale(-1, 1))

        self.all_pix = dict(self.pix)
        self.all_mask = dict(self.mask_pix)
        self.all_pix["head"] = self.head_pix
        self.all_mask["head"] = self.head_mask
        self.all_pix["head_l"] = self.head_pix_l
        self.all_mask["head_l"] = self.head_mask_l

        self.setFixedSize(self.W, self.H)

    def _draw_mitten_hug(self, p):
        """睡着时把手套抱在怀里：贴在前爪位置，随呼吸轻微起伏"""
        pm = self._mitten_pix.get("side")
        if pm is None:
            return
        h = int(self.H * 0.24)
        w = int(pm.width() * h / pm.height())
        bob = math.sin(self.bob_t * 0.6) * 1.5
        x = int(self.W * 0.30)
        y = int(self.H * 0.70 + bob)
        p.setOpacity(0.96)
        p.drawPixmap(QRect(x, y, w, h), pm)
        p.setOpacity(1.0)

    def toggle_mitten(self, on):
        """戴上手套：把鼠标指针换成手套（不新建窗口，避免抢鼠标抓取）"""
        self.mitten_mode = bool(on)
        # 从菜单回调里同步改指针容易和菜单的 grab 打架，延后一拍再换
        QTimer.singleShot(0, self._apply_mitten_cursor)

    def _apply_mitten_cursor(self):
        try:
            if self.mitten_mode and getattr(self, "_mitten_qc", None) is not None:
                self.setCursor(self._mitten_qc)
            else:
                self.unsetCursor()
        except Exception as e:
            print("mitten cursor failed:", e, flush=True)

    def _spawn_ghost(self):
        if not self._ghost_pix:
            return
        key = "family" if random.random() < 0.55 else "mother"
        pm = self._ghost_pix[key]
        if self._ghost is None:
            self._ghost = GhostWindow(pm)
        else:
            self._ghost.pm = pm
            sz = pm.deviceIndependentSize()
            self._ghost.setFixedSize(int(sz.width()), int(sz.height()))
        g = self._ghost
        geo = self.geometry()
        gx = geo.x() - g.width() + int(self.W * 0.10)
        gy = geo.y() + self.H - g.height() + self.pad
        scr = self.screen_rect()
        if gx < scr.left():
            gx = geo.x() + int(self.W * 0.62)
        g._base_x, g._base_y = gx, gy
        # 从画面外侧飘向目标位置：母亲在左边就再往左退一点
        away = -160 if gx < geo.x() + self.W * 0.5 else 160
        g._drift_from = (gx + away, gy - 40)
        g.move(gx + away, gy - 40)
        self._ghost_kind = key
        # 梦话 0.7s -> 母亲 2.4s -> 幼崽（母亲讲完再接）
        QTimer.singleShot(700, lambda: self.speak("dream"))
        QTimer.singleShot(2400, self._ghost_speak_mom)
        hold = random.uniform(8.0, 11.0) if key == "family" else random.uniform(6.0, 8.5)
        g.start(hold=hold)
        QTimer.singleShot(int((hold + 4.0) * 1000), self._rearm_ghost)

    def _ghost_speak_mom(self):
        d = self.speak_ghost("mom", volume=0.72)
        if getattr(self, "_ghost_kind", "") == "family":
            QTimer.singleShot(int((d + 0.7) * 1000),
                              lambda: self.speak_ghost("pup", volume=0.6))

    def _rearm_ghost(self):
        """梦醒了还在睡的话，过一阵再做一个"""
        if self.state != "sleep":
            return
        chance = self.cfg.get("ghost_chance", 0.6)
        if getattr(self, "story_mode", False):
            chance = min(1.0, chance + 0.2)
        if getattr(self, "ghost_always", False):
            chance = 1.0
        if random.random() < chance:
            self._ghost_plan = time.monotonic() + random.uniform(12.0, 30.0)

    def _despawn_ghost(self):
        if self._ghost is not None:
            self._ghost.stop()

    def _load_cushion(self):
        path = os.path.join(ASSETS, "cushion.png")
        self._cushion_pix = None
        if not os.path.exists(path):
            return
        src = QPixmap(path)
        w = int(self.W * 0.62)
        h = int(src.height() * w / src.width())
        pm = src.scaled(int(w * self.dpr), int(h * self.dpr),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(self.dpr)
        self._cushion_pix = pm

    def _load_hands(self):
        """程序合成用的手套贴图（正/镜像），按窗口高度定尺寸"""
        self._hand_pix = {}
        path = os.path.join(ASSETS, "mitten_side.png")
        if not os.path.exists(path):
            return
        src = QPixmap(path)
        h = int(self.H * 0.30)
        w = int(src.width() * h / src.height())
        pm = src.scaled(int(w * self.dpr), int(h * self.dpr),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(self.dpr)
        self._hand_pix["r"] = pm
        self._hand_pix["l"] = pm.transformed(QTransform().scale(-1, 1))
        self._hand_pix["l"].setDevicePixelRatio(self.dpr)

    def _load_cling(self):
        """攀附姿势：侧身，左右两份；比例与窗口不同，按高度等比加载"""
        self._cling_pix = {}
        self._fit_pix = {}
        for key, fname in (("left", "cling_side.png"), ("right", "cling_side_r.png")):
            path = os.path.join(ASSETS, fname)
            if not os.path.exists(path):
                continue
            src = QPixmap(path)
            h = int(self.H * 1.08)
            w = int(src.width() * h / src.height())
            pm = src.scaled(int(w * self.dpr), int(h * self.dpr),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(self.dpr)
            self._cling_pix[key] = pm
        # 随机坐姿变体：比窗口窄，等比缩放到窗口高度
        path = os.path.join(ASSETS, "sit2.png")
        if os.path.exists(path):
            src = QPixmap(path)
            h = int(self.H * 0.98)
            w = int(src.width() * h / src.height())
            pm = src.scaled(int(w * self.dpr), int(h * self.dpr),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(self.dpr)
            self._fit_pix["sit2"] = pm

    def _load_mitten_cursor(self):
        path = os.path.join(ASSETS, "mitten_side.png")
        if not os.path.exists(path):
            return
        pm = QPixmap(path)
        h = int(self.H * 0.30)
        w = int(pm.width() * h / pm.height())
        s = pm.scaled(int(w * self.dpr), int(h * self.dpr),
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)
        s.setDevicePixelRatio(self.dpr)
        self._mitten_cursor_pix = s
        # 指针图：把袖口上沿当作热点，手套自然垂在指针下方
        hot_x = int(s.deviceIndependentSize().width() * 0.5)
        hot_y = int(s.deviceIndependentSize().height() * 0.06)
        self._mitten_qc = QCursor(s, hot_x, hot_y)

    def _load_mitten(self):
        """故事模式用：兽皮手套"""
        self._mitten_pix = {}
        for key, f in (("side", "mitten_side.png"), ("pair", "mitten_pair.png")):
            path = os.path.join(ASSETS, f)
            if not os.path.exists(path):
                continue
            self._mitten_pix[key] = QPixmap(path)

    def _load_ghosts(self):
        """睡梦里出现的幽灵：母亲 / 全家"""
        for key, f in (("mother", "ghost_mother.png"), ("family", "ghost_family.png")):
            path = os.path.join(ASSETS, f)
            if not os.path.exists(path):
                continue
            pm = QPixmap(path)
            h = int(self.H * 1.05)
            w = int(pm.width() * h / pm.height())
            s = pm.scaled(int(w * self.dpr), int(h * self.dpr),
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            s.setDevicePixelRatio(self.dpr)
            self._ghost_pix[key] = s

    def _load_voices(self):
        self.sounds = {}
        self.cats = {}
        self.cats_story = {}
        self.cats_ghost = {}
        self.cats_pup = {}
        self.eff_dur = {}
        path = os.path.join(VOICE, "manifest.json")
        if not os.path.isfile(path):
            return
        man = json.load(open(path, encoding="utf-8-sig"))
        for lid, info in man["lines"].items():
            base_lid = lid[2:] if lid.startswith("s_") else lid
            cat = base_lid.split("_")[0]
            if lid.startswith("g_mom"):
                cat = "mom"
            elif lid.startswith("g_pup"):
                cat = "pup"
            mode = info.get("mode", "normal")
            for v in info["files"].values():
                f = os.path.join(VOICE, v["file"])
                if not os.path.isfile(f):
                    continue
                eff = QSoundEffect()
                eff.setSource(QUrl.fromLocalFile(f))
                eff.setVolume(0.85)
                self.sounds[f] = eff
                self.eff_dur[eff] = v.get("dur", 2.0)
                bucket = {"story": self.cats_story, "ghost": self.cats_ghost,
                          "pup": self.cats_pup}.get(mode, self.cats)
                bucket.setdefault(cat, []).append(eff)
                # 落地/摔落专用：排除“别戳了”这类只适合被点的台词
                if cat == "hit" and not any(w in (info.get("text") or "") for w in ("戳", "打", "别")):
                    bucket.setdefault("drop", []).append(eff)
        for c in self.cats:
            print(f"[voice] {c}: {len(self.cats[c])} clips")
        self._load_sfx()

    def _load_sfx(self):
        """合成音效（撞击/脚步等），与语音分开，避免互相打断"""
        self.sfx = {}
        sdir = (os.path.join(BASE, "assets", "audio")
                if os.path.isdir(os.path.join(BASE, "assets", "audio"))
                else r"D:\DSH\pet_assets\audio")
        if not os.path.isdir(sdir):
            return
        for name in ("hit_1", "hit_2", "hit_3", "sit", "pet", "step_1", "step_2", "step_3"):
            f = os.path.join(sdir, name + ".wav")
            if not os.path.isfile(f):
                continue
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(f))
            eff.setVolume(0.55 if name.startswith("hit") else 0.35)
            key = "hit" if name.startswith("hit") else name.split("_")[0]
            self.sfx.setdefault(key, []).append(eff)
        print(f"[sfx] {list(self.sfx)}", flush=True)

    def play_sfx(self, key):
        clips = self.sfx.get(key)
        if clips:
            random.choice(clips).play()

    def _mask_at(self, name, idx):
        """取某动画某帧的遮罩（逻辑像素），带 LRU 缓存"""
        if not hasattr(self, "_mask_cache"):
            self._mask_cache = {}
            self._mask_order = []
        key = (name, idx)
        reg = self._mask_cache.get(key)
        if reg is not None:
            return reg
        frames = self.anims.get(name) or []
        if not frames:
            return None
        idx = max(0, min(idx, len(frames) - 1))
        pm = frames[idx]
        small = pm.scaled(self.W, self.H, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.FastTransformation)
        reg = QRegion(small.mask())
        self._mask_cache[key] = reg
        self._mask_order.append(key)
        if len(self._mask_order) > 600:
            old = self._mask_order.pop(0)
            self._mask_cache.pop(old, None)
        return reg

    def _sync_mask(self, name, idx):
        """让窗口遮罩跟随当前帧；只有换帧才真正调用 setMask"""
        if os.environ.get("PET_NOMASK") == "1":
            return
        key = (name, idx)
        if getattr(self, "_mask_key", None) == key:
            return
        reg = self._mask_at(name, idx)
        if reg is not None and not reg.isEmpty():
            self.setMask(reg)
            self._mask_key = key

    def _load_anim(self):
        """只登记动画帧文件，真正用到时才解码（省内存）"""
        import glob
        base = (os.path.join(BASE, "assets", "anim")
                if os.path.isdir(os.path.join(BASE, "assets", "anim"))
                else r"D:\DSH\pet_assets\anim")
        self.anim_masks = {}
        self.anims = AnimStore(self.dpr)
        names = ("speak_pain", "idle", "idle2", "idle3", "sleep", "talk", "crawl",
                 "hit", "pet", "eat", "hug", "pinch", "tickle", "land", "pick",
                 "tickle_hand",
                 "trans_sit_sleep", "trans_sleep_sit", "trans_sit_idle", "trans_idle_sit",
                 "trans_hit_sit", "trans_pet_sit", "trans_pinch_sit", "trans_hug_sit",
                 "trans_tickle_sit", "trans_eat_sit", "sleep_mitten", "pet_mitten",
                 "hang1arm", "trans_sit_beg", "trans_beg_sit",
                 "yawn", "stretch", "stare", "tailchase", "air_roll", "cling_kick")
        for name in names:
            files = sorted(glob.glob(os.path.join(base, name, "frames", "f_*.png")))
            if not files:
                files = sorted(glob.glob(os.path.join(base, name, "frames", "f_*.webp")))
            if files:
                self.anims.add(name, files)
        # 派生动画：往返 / 镜像 / 倒放，同样按需构建
        self.anims.add_derived("crawl", "crawl", "pingpong")
        self.anims.add_derived("crawl_l", "crawl", "pingpong_mirror")
        self.anims.add_derived("cling_kick_l", "cling_kick", "mirror")
        self.anims.add_derived("trans_sit_idle_rev", "trans_idle_sit", "reverse")
        print(f"[anim] registered {len(self.anims.spec)} animations", flush=True)
        self.anim_frames = self.anims.get("speak_pain", [])
        self.crawl_left = False
        self._mask_key = None
        self._anim_after = None
        self.deep_sleep = bool(self.cfg.get("deep_sleep", False))
        self.story_mode = bool(self.cfg.get("story_mode", False))
        self.ghost_always = bool(self.cfg.get("ghost_always", False))
        self._ghost = None
        self._ghost_plan = None
        self._ghost_pix = {}
        self._mitten_pix = {}
        self.mitten_mode = False
        self._fall_from = 0.0
        self._cushion_on = False
        self._soft_t0 = 0.0
        self._soft_fall = False
        self._roll_t0 = 0.0
        self._soft_dur = 0.0
        self._soft_amp = 0.0
        self.CATCH_H = int(round(self.H * 0.55)) if hasattr(self, "H") else 150
        self._micro_next = time.monotonic() + random.uniform(18.0, 40.0)
        # 环境感知
        self._cursor_prev = QCursor.pos()
        self._cursor_t = time.monotonic()
        self._cursor_speed = 0.0
        self._active_since = time.monotonic()   # 连续活跃起点
        self._last_rest = time.monotonic()
        self._care_next = time.monotonic() + random.uniform(2400, 4200)  # 40-70 分钟后可能关心一次
        self._mitten_cursor_pix = None
        self._mitten_qc = None

    def speak(self, cat):
        """播放一条台词，返回 (effect, 时长秒)；播不了返回 (None, 0)"""
        clips = None
        if getattr(self, "story_mode", False):
            clips = self.cats_story.get(cat)
        if not clips:
            clips = self.cats.get(cat)
        if not clips:
            return None, 0.0
        for e in self.sounds.values():
            if e.isPlaying():
                e.stop()
        eff = random.choice(clips)
        eff.play()
        return eff, self.eff_dur.get(eff, 2.0)

    def speak_ghost(self, cat, volume=0.7):
        """幽灵的台词：独立音库、音量略低；返回时长秒"""
        clips = self.cats_ghost.get(cat) or self.cats_pup.get(cat)
        if not clips:
            return 0.0
        eff = random.choice(clips)
        eff.setVolume(volume)
        eff.play()
        return self.eff_dur.get(eff, 2.0)

    # ---------- 位置 ----------
    def screen_rect(self):
        scr = QGuiApplication.screenAt(QPoint(int(self.fx), int(self.fy))) \
            or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _place_initial(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.fx = g.right() - self.W * 0.5 - 80
        self.fy = g.bottom() - 4
        self._apply_pos()

    def _apply_pos(self):
        self.move(int(self.fx - self.W / 2), int(self.fy - (self.H - self.pad)))

    def set_pose(self, name):
        if self.state_pose == name:
            return
        self.state_pose = name
        if os.environ.get('PET_NOMASK') != '1':
            fit = self._fit_pix.get(name)
            if fit is not None:
                sz = fit.deviceIndependentSize()
                w, h = int(sz.width()), int(sz.height())
                reg = QRegion(fit.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.FastTransformation).mask())
                self.setMask(reg.translated((self.W - w) // 2, self.H - h))
                self._mask_key = name
            else:
                pm = self.all_mask.get(name)
                if pm is not None:
                    self.setMask(QRegion(pm.mask()))
                    self._mask_key = name
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.state == "anim" and self.anim_frames:
            idx = min(len(self.anim_frames) - 1, self.anim_idx)
            self._sync_mask(getattr(self, "_anim_name", ""), idx)
            p.drawPixmap(QRect(0, 0, self.W, self.H), self.anim_frames[idx])
            self._draw_hands(p)
            return
        if self.state == "hang":
            self._paint_hang(p)
            return
        loop_key = {"idle": getattr(self, "idle_variant", "idle"), "sleep": "sleep",
                    "drag": "pick"}.get(self.state)
        if self.state == "sleep" and getattr(self, "story_mode", False) \
                and self.anims.get("sleep_mitten"):
            loop_key = "sleep_mitten"
        if self.state == "crawl" and self.anims.get("crawl"):
            # 动画是朝左爬的步态：往左用原帧正放，往右用镜像帧正放
            loop_key = "crawl" if self.crawl_left else "crawl_l"
        if loop_key and self.anims.get(loop_key):
            frames = self.anims[loop_key]
            idx = int(self.loop_t * 24) % len(frames)
            self._sync_mask(loop_key, idx)
            p.drawPixmap(QRect(0, 0, self.W, self.H), frames[idx])
            return
        if self.state == "crawl":
            # 没有可用爬行动画时，用静态图做程序化起伏 + 轻微倾斜，避免滑步
            dy = math.sin(self.loop_t * 7.0) * 2.5
            ang = math.sin(self.loop_t * 7.0) * 1.2
            p.translate(self.W / 2, self.H)
            p.rotate(ang)
            p.translate(-self.W / 2, -self.H)
            p.drawPixmap(0, int(dy), self.all_pix[self.state_pose])
            return
        fit = self._fit_pix.get(self.state_pose)
        if fit is not None:
            sz = fit.deviceIndependentSize()
            w, h = int(sz.width()), int(sz.height())
            x = (self.W - w) // 2
            y = self.H - h + int(math.sin(self.bob_t) * 1.5)
            p.drawPixmap(x, y, fit)
            p.setOpacity(1.0)
            return
        roll = self.anims.get("air_roll") if (self.state == "fall" and self._roll_t0) else None
        if roll:
            k = min(1.0, (time.monotonic() - self._roll_t0) / 0.62)
            idx = min(len(roll) - 1, int(k * (len(roll) - 1)))
            self._sync_frame_mask("air_roll", idx)
            p.drawPixmap(QRect(0, 0, self.W, self.H), roll[idx])
        else:
            p.drawPixmap(0, int(math.sin(self.bob_t) * 1.5), self.all_pix[self.state_pose])

    def _draw_hands(self, p):
        """在“捏脸 / 撸”时按曲线贴上的手套手（代替生成式画手）"""
        if not getattr(self, "_hand_pix", None):
            return
        name = getattr(self, "_anim_name", "")
        total = max(1, len(self.anim_frames))
        k = min(1.0, (self.anim_idx + 0.5) / total)

        def ease(x):
            return x * x * (3 - 2 * x)

        def come(kk, a=0.16, b=0.84):
            up = ease(min(1.0, kk / a))
            down = ease(max(0.0, min(1.0, (kk - b) / (1.0 - b))))
            return up * (1.0 - down)

        def lsize(pm):
            """逻辑尺寸（Qt 的 deviceIndependentSize 在这台机器上不可靠，手算）"""
            return int(pm.width() / self.dpr), int(pm.height() / self.dpr)

        app = come(k)
        if name == "pinch":
            push = math.sin(min(1.0, max(0.0, (k - 0.3) / 0.4)) * math.pi) * self.W * 0.035
            for side in ("l", "r"):
                pm = self._hand_pix[side]
                w, h = lsize(pm)
                if side == "l":
                    x0 = -w * 1.05
                    x1 = self.W * 0.37 - w + push      # 右手套右缘贴左脸颊
                else:
                    x0 = self.W + w * 0.05
                    x1 = self.W * 0.63 - push          # 左手套左缘贴右脸颊
                x = x0 + (x1 - x0) * app
                y = int(self.H * 0.30 - h * 0.5 + math.sin(k * 7.0) * 2)
                p.drawPixmap(QRect(int(x), y, w, h), pm)
        elif name == "hug":
            close = ease(min(1.0, k / 0.25)) * (1.0 - ease(max(0.0, (k - 0.75) / 0.25)))
            for side in ("l", "r"):
                pm = self._hand_pix[side]
                w, h = lsize(pm)
                if side == "l":
                    x0, x1 = -w * 1.2, self.W * 0.30 - w * 0.85
                else:
                    x0, x1 = self.W + w * 0.2, self.W * 0.70 - w * 0.15
                x = x0 + (x1 - x0) * close
                y = int(self.H * 0.42 - h * 0.5)
                p.drawPixmap(QRect(int(x), y, w, h), pm)
        elif name == "pet":
            pm = self._hand_pix["r"]
            w, h = lsize(pm)
            stroke = math.sin(k * 8.0) * self.W * 0.045
            x = self.W * 0.50 - w * 0.5 + stroke
            y0, y1 = -h * 1.1, self.H * 0.04
            y = y0 + (y1 - y0) * app + math.sin(k * 8.0) * 2
            p.drawPixmap(QRect(int(x), int(y), w, h), pm)

    def _sync_frame_mask(self, name, idx):
        """让遮罩跟随某一动画的某一帧（用于坠落翻滚等临时画面）"""
        if os.environ.get("PET_NOMASK") == "1":
            return
        key = (name, idx)
        if getattr(self, "_mask_key", None) == key:
            return
        seq = self.anims.get(name)
        if seq is None:
            return
        pm = seq[min(idx, len(seq) - 1)]
        small = pm.scaled(self.W, self.H, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.FastTransformation)
        reg = QRegion(small.mask())
        if not reg.isEmpty():
            self.setMask(reg)
            self._mask_key = key

    def _paint_hang(self, p):
        """悬空：上边缘用单臂悬挂动画，左右用攀附静图 + 程序化下滑"""
        edge0 = getattr(self, "hang_edge", "left")
        if edge0 == "top":
            anim = self.anims.get("hang1arm")
        else:
            anim = self.anims.get("cling_kick_l" if edge0 == "left" else "cling_kick")
        if anim:
            idx = int(self.loop_t * 24) % len(anim)
            pm = anim[idx]
            key = ("hang1arm", idx)
        else:
            edge = getattr(self, "hang_edge", "left")
            pm = self._cling_pix.get("right" if edge == "left" else "left")
            idx = 0
            key = ("cling", 0)
        if pm is None:
            return
        sz = pm.deviceIndependentSize()
        pw, ph = max(1.0, sz.width()), max(1.0, sz.height())
        rw, rh = self.width(), self.height()
        s = min(rw / pw, rh / ph)
        dw, dh = pw * s, ph * s
        dx = (rw - dw) / 2.0
        dy = 0.0 if getattr(self, "hang_edge", "") == "top" else (rh - dh) / 2.0
        if anim is None:
            # 攀附：缓慢下滑 + 细微抖动（撑不住的观感）
            t = self.loop_t
            dy += math.sin(t * 1.6) * 2.0
            dx += math.sin(t * 2.3) * 1.2
            slip = max(0.0, math.sin(t * 0.55)) * 5.0
            dy += slip
        rect = QRect(int(dx), int(dy), int(dw), int(dh))
        if self._mask_key != key:
            small = pm.scaled(int(dw), int(dh), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.FastTransformation)
            self.setMask(QRegion(small.mask()).translated(int(dx), int(dy)))
            self._mask_key = key
        else:
            # 程序化位移时遮罩要跟着挪
            if anim is None:
                small = pm.scaled(int(dw), int(dh), Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.FastTransformation)
                self.setMask(QRegion(small.mask()).translated(int(dx), int(dy)))
        p.drawPixmap(rect, pm)

    def _ensure_full_window(self):
        """探头会把窗口缩成头部大小；任何其它状态都要先恢复，否则只会画出左上角"""
        if self.width() != self.W or self.height() != self.H:
            self.setFixedSize(self.W, self.H)
            self._apply_pos()
            self._mask_key = None

    def play_anim(self, name, dur, then=None):
        frames = self.anims.get(name)
        if not frames:
            return False
        self._anim_after = then
        self._ensure_full_window()
        self.anim_frames = frames
        self._anim_name = name
        self.state = "anim"
        self.anim_t0 = time.monotonic()
        self.anim_dur = max(0.6, dur)
        self.anim_idx = 0
        self.state_until = self.anim_t0 + self.anim_dur
        self._sync_mask(name, 0)
        return True

    # ---------- 状态机 ----------
    def go(self, state, dur=None):
        t = self.cfg["timing"]
        if state != "peek":
            self._ensure_full_window()
        self._anim_after = None          # 换状态即作废未执行的过渡回调
        self.state = state
        now = time.monotonic()
        if dur is None:
            dur = {
                "idle": random.uniform(t["idle_min"], t["idle_max"]),
                "sit": random.uniform(t["sit_min"], t["sit_max"]),
                "sleep": random.uniform(t["sleep_min"], t["sleep_max"]),
                "hit": t["hit_recover"],
                "crawl": 20.0,
                "fall": 6.0,
                "land": 0.38,
                "eat": 3.5,
                "pet_head": 3.0,
                "poke": 1.5,
                "pinch": 2.0,
                "hug": 2.0,
                "tickle": 2.0,
            }.get(state, 3.0)
        self.state_start = now
        self.state_until = now + dur
        sit_pose = "sit"
        self.set_pose({
            "idle": "idle", "sit": sit_pose, "sleep": "sleep",
            "hit": "hit", "drag": "pick", "fall": "pick",
            "crawl": "crawl", "land": "land", "eat": "eat",
            "pet_head": "pet_head", "poke": "poke", "pinch": "pinch",
            "hug": "hug", "tickle": "tickle",
        }[state])
        # 这些状态画的是动画帧，遮罩必须用动画的，否则会被静态剪影切碎
        if state == "idle":
            opts = [n for n in ("idle", "idle2", "idle3") if self.anims.get(n)]
            self.idle_variant = random.choice(opts) if opts else "idle"
        key = {"idle": getattr(self, "idle_variant", "idle"), "sleep": "sleep",
               "crawl": "crawl" if self.crawl_left else "crawl_l",
               "drag": "pick"}.get(state)
        if key:
            self._sync_mask(key, 0)
        if state == "sit" and self.anims.get("trans_sit_beg") \
                and self.anims.get("trans_beg_sit") \
                and time.monotonic() - getattr(self, "_beg_last", 0.0) > 25.0 \
                and random.random() < 0.35:
            self._beg_last = time.monotonic()
            QTimer.singleShot(400, self._play_beg)

        if state == "sleep":
            chance = self.cfg.get("ghost_chance", 0.6)
            if getattr(self, "story_mode", False):
                chance = min(1.0, chance + 0.2)
            if getattr(self, "ghost_always", False):
                chance = 1.0
            self._ghost_plan = (time.monotonic() + random.uniform(1.5, 4.5)
                                if random.random() < chance else None)
        else:
            self._ghost_plan = None
            self._despawn_ghost()

    def tick(self):
        now = time.monotonic()
        self.bob_t += 0.22
        self.loop_t = now - self.state_start

        # ---- 环境感知：光标速度 / 连续使用时长 ----
        cur = QCursor.pos()
        dt = max(1e-3, now - self._cursor_t)
        self._cursor_speed = ((cur - self._cursor_prev).manhattanLength()) / dt
        self._cursor_prev, self._cursor_t = cur, now
        if self._cursor_speed > 80:
            self._active_since = self._active_since      # 保持
        if now >= self._care_next and self.state in ("idle", "sit"):
            busy_min = (now - self._last_rest) / 60.0
            if busy_min > 35:
                self._care_next = now + random.uniform(3600, 5400)
                if self.play_anim("stare", 3.0, then=lambda: self.go("sit", 2.5)):
                    QTimer.singleShot(400, lambda: self.speak("amb"))
                    self._last_rest = now
            else:
                self._care_next = now + 600

        # 快速移动的光标会吸引她的注意
        if self._cursor_speed > 1400 and self.state in ("idle", "sit") \
                and random.random() < 0.12:
            if self.play_anim("stare", 2.4, then=lambda: self.go("sit", 2.0)):
                self._micro_next = now + random.uniform(30.0, 70.0)

        # 空闲时偶尔来点小动作（打哈欠 / 伸懒腰 / 发呆 / 追尾巴）
        if self.state in ("idle", "sit") and now >= self._micro_next \
                and self.state_until - now > 2.0:
            self._micro_next = now + random.uniform(25.0, 70.0)
            name = random.choice(("yawn", "stretch", "stare", "tailchase"))
            frames = self.anims.get(name)
            if frames:
                self.play_anim(name, max(3.6, len(frames) / 24.0),
                               then=lambda: self.go("sit", 2.5))

        # 睡着时有概率在身旁浮出家人的幽灵
        if self.state == "sleep" and self._ghost_plan and now >= self._ghost_plan:
            self._ghost_plan = None
            self._spawn_ghost()

        # 软着陆的阻尼弹跳
        if self._soft_t0 and self.state == "anim":
            t = now - self._soft_t0
            if t >= self._soft_dur:
                self._soft_t0 = 0.0
            else:
                g2 = self.screen_rect()
                base = g2.bottom() - 2
                self.fy = base - self._soft_amp * math.exp(-3.2 * t) * abs(math.sin(9.0 * t))

        if self.state in ("drag", "peek"):
            pass
        elif self.state == "fall":
            self.vy += self.cfg["fall_gravity"] * 0.033 * 0.62
            self.fy += self.vy * 0.033
            g = self.screen_rect()
            if self._soft_fall and self._roll_t0 == 0.0 \
                    and self.anims.get("air_roll") \
                    and (g.bottom() - 2 - self.fy) < 320:
                self._roll_t0 = now
            if self.fy >= g.bottom() - 2:
                self.fy = g.bottom() - 2
                self.vy = 0
                self.cycles += 1
                # 轻盈落地：高度不足屏幕一半，或主人放了气垫
                fall_h = (g.bottom() - 2) - self._fall_from
                soft = fall_h < g.height() * 0.5
                had_cushion = False
                self._cushion_on = False
                self._roll_t0 = 0.0
                self._soft_fall = False
                self._ensure_full_window()
                if soft:
                    # 轻巧落地：压缩 + 阻尼弹跳（气垫更弹）
                    self.play_sfx("pet" if had_cushion else "step")
                    self._soft_t0 = time.monotonic()
                    self._soft_dur = 1.15
                    self._soft_amp = self.H * (0.16 if had_cushion else 0.10)
                    frames = self.anims.get("land")
                    if frames:
                        self.play_anim("land", 1.2,
                                       then=lambda: self.go("sit", 2.0))
                    else:
                        self.go("sit", 2.0)
                else:
                    self.play_sfx("hit")
                    _eff, _dur = self.speak("drop")
                    if not self.play_anim("land", max(0.5, _dur + 0.25)):
                        self.go("land", max(0.5, _dur + 0.25))
        elif self.state == "crawl":
            self._crawl_step(now)
        elif self.state == "anim":
            frac = (now - self.anim_t0) / self.anim_dur
            self.anim_idx = int(max(0.0, min(0.999, frac)) * len(self.anim_frames))
            if now >= self.state_until:
                cb, self._anim_after = self._anim_after, None
                if cb:
                    cb()
                else:
                    self.go("sit", 2.5)
        elif self.state == "hang":
            if now >= self.hang_until:
                self.end_hang(climb=False)
        elif self.state in ("idle", "sit", "sleep", "hit", "land", "eat",
                            "pet_head", "poke", "pinch", "hug", "tickle"):
            if now >= self.state_until:
                self._advance(now)

        if self.state not in ("drag", "peek", "hang"):
            self._apply_pos()
        if self.state == "peek" and now >= self.state_until:
            self.end_peek()
        self.update()

    def _advance(self, now):
        if self.state == "hit":
            self.go(self.prev_state, 2.0)
            return
        if self.state == "land":
            self.go("sit", 2.5)
            return
        if self.state == "eat":
            self.go("sit", 3.0)
            return
        if self.state in ("pet_head", "poke", "pinch", "hug", "tickle"):
            self.go("sit", 2.0)
            return
        if self.state == "sleep":
            if getattr(self, "deep_sleep", False):
                self.state_until = now + 6.0   # 沉睡模式：一直睡，等主人叫醒
                return
            self.speak("wake")
            if not self.play_anim("trans_sleep_sit", 4.8,
                                  then=lambda: self.go("sit", 2.0)):
                self.go("sit", 2.0)
            return
        if self.state == "idle":
            hour = datetime.now().hour
            night = hour >= 23 or hour < 6
            if night and random.random() < 0.45:
                self.speak("amb")
                self.go("sit", 2.0)
                return
            chase = self.cfg["behavior"]["chase_mouse_chance"]
            if getattr(self, "story_mode", False):
                chase *= 0.45
            if random.random() < chase and self._mouse_far():
                self._start_crawl()
            else:
                if random.random() < self.cfg["behavior"]["idle_talk_chance"]:
                    _e, d = self.speak("idle")
                    if self.play_anim("talk", max(1.5, d + 0.3)):
                        return
                if not self.play_anim("trans_idle_sit", 3.5,
                                      then=lambda: self.go("sit")):
                    self.go("sit")
            return
        if self.state == "sit":
            self.cycles += 1
            if self.cycles >= self.cfg["behavior"]["sleep_after_cycles"]:
                self.cycles = 0
                self.speak("sleep")
                if not self.play_anim("trans_sit_sleep", 5.0,
                                      then=lambda: self.go("sleep")):
                    self.go("sleep")
            else:
                if not (self.play_anim("trans_sit_idle_rev", 4.0,
                                       then=lambda: self.go("idle"))
                        or self.play_anim("trans_sit_idle", 4.5,
                                          then=lambda: self.go("idle"))):
                    self.go("idle")
            return
        self.go("idle")

    def _mouse_far(self):
        g = self.screen_rect()
        m = QCursor.pos()
        if not g.contains(m):
            return False
        return math.hypot(m.x() - self.fx, m.y() - self.fy) > 120

    def _start_crawl(self):
        """只沿桌面底部水平爬，不往上下飘"""
        m = QCursor.pos()
        g = self.screen_rect()
        self.tx = min(max(m.x(), g.left() + self.W * 0.3), g.right() - self.W * 0.3)
        self.ty = self.fy  # 锁死当前高度（地面）
        self.crawl_left = self.tx < self.fx   # 先定方向，遮罩才不会用旧值
        self.go("crawl", 16.0)

    def _crawl_step(self, now):
        dx = self.tx - self.fx
        stop = self.cfg["crawl_stop_distance"]
        if abs(dx) <= stop or now >= self.state_until:
            # 爬行结束：借用「站 -> 坐」过渡（爬行首帧同为正面四足姿态）
            if not self.play_anim("trans_idle_sit", 3.2,
                                  then=lambda: self.go("sit", 2.0)):
                self.go("sit", 2.0)
            return
        step = self.cfg["crawl_speed"] * 0.033
        self.fx += math.copysign(min(step, abs(dx)), dx)
        self.fy = self.ty
        left = dx < 0
        if left != self.crawl_left:
            self.crawl_left = left
            # 方向变了：画面用镜像帧，遮罩也要跟着换
            if self.anims.get("crawl") and os.environ.get("PET_NOMASK") != "1":
                key = "crawl" if left else "crawl_l"
                self._sync_mask(key, int(self.loop_t * 24) % len(self.anims.get("crawl", [1])))

    # ---------- 交互 ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self._press_pos = ev.globalPosition().toPoint()
            self._press_time = time.monotonic()
            self._follow = self._press_pos - self.pos()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._press_pos is None:
            return
        cur = ev.globalPosition().toPoint()
        if not self.dragging and (cur - self._press_pos).manhattanLength() > 6:
            self.dragging = True
            self.prev_state = "sit"
            self.state = "drag"
            self._ensure_full_window()   # 悬空态窗口更窄，拖动前必须还原
            self.set_pose("drag")
            self.speak("drag")
        if self.dragging:
            p = cur - self._follow
            self.fx = p.x() + self.W / 2
            self.fy = p.y() + (self.H - self.pad)
            self.move(p)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        was_drag = self.dragging
        self.dragging = False
        self._press_pos = None
        if was_drag:
            self.vy = 0.0
            if self._try_grab_edge():
                return
            self.state = "fall"
            self.state_until = time.monotonic() + 6.0
            self.set_pose("drag")
            self._fall_from = self.fy
            self._roll_t0 = 0.0
            g0 = self.screen_rect()
            self._soft_fall = (g0.bottom() - 2 - self.fy) < g0.height() * 0.5
            self._cushion_on = False
            self.setFixedSize(self.W, self.H)
            if os.environ.get("PET_NOMASK") != "1":
                reg = QRegion(self.all_mask["drag"].mask())
                self.setMask(reg)
                self._mask_key = "drag"
        else:
            if time.monotonic() - self._press_time < 0.6:
                self.on_click()
        ev.accept()

    def _try_grab_edge(self):
        """松手时如果贴着屏幕边缘，就抓住边缘悬空"""
        g = self.screen_rect()
        edge, threshold = None, int(self.W * 0.22)
        cx = self.fx   # fx 是水平中心
        if cx < g.left() + threshold:
            edge = "left"
        elif cx > g.right() - threshold:
            edge = "right"
        elif self.fy - (self.H - self.pad) < g.top() + threshold:
            edge = "top"
        if edge is None:
            return False
        self.start_hang(edge)
        return True

    def start_hang(self, edge):
        """进入悬空状态：上边缘用单臂悬挂动画，左右用攀附静图"""
        self.hang_edge = edge
        self.hang_t0 = time.monotonic()
        self.hang_until = self.hang_t0 + random.uniform(6.0, 14.0)
        src = self.anims.get("hang1arm") if edge == "top" else None
        if edge == "top" and src:
            aspect = src[0].width() / src[0].height()
        elif self.anims.get("cling_kick"):
            f0 = self.anims["cling_kick"][0]
            sz = f0.deviceIndependentSize()
            aspect = sz.width() / sz.height()
        elif self._cling_pix:
            key = "right" if edge == "left" else "left"   # 左边缘用镜像版
            pm0 = self._cling_pix.get(key) or self._cling_pix.get("left")
            sz = pm0.deviceIndependentSize()
            aspect = sz.width() / sz.height()
        else:
            aspect = 0.75
        self.hang_h = int(self.H * 1.08)
        self.hang_w = max(40, int(self.hang_h * aspect))
        self.setFixedSize(self.hang_w, self.hang_h)
        self.state = "hang"
        self.state_until = self.hang_until
        g = self.screen_rect()
        bottom = self.y() + self.H             # 松手那一刻她的脚底（用常规高度，此时窗口可能已被改小）
        if edge == "top":
            left = min(max(self.fx - self.hang_w / 2, g.left()), g.right() - self.hang_w)
            top = g.top() - 6
        elif edge == "left":
            left = g.left() - 6
            top = min(max(bottom - self.hang_h, g.top()), g.bottom() - self.hang_h)
        else:
            left = g.right() - self.hang_w + 6
            top = min(max(bottom - self.hang_h, g.top()), g.bottom() - self.hang_h)
        self.move(int(left), int(top))
        self.fx, self.fy = left + self.hang_w / 2, top + self.hang_h
        self._mask_key = None
        self.set_pose("cling")
        self.update()

    def end_hang(self, climb=False):
        """结束悬空：要么爬回去，要么撑不住掉下去"""
        self.state = "fall" if not climb else "land"
        self.vy = 0.0
        self.state_until = time.monotonic() + 6.0
        self._ensure_full_window()
        if climb:
            self.go("sit", 2.0)
        else:
            self.set_pose("drag")

    def on_click(self):
        if self.state == "hang":
            self.end_hang(climb=True)
            return
        # 戴着手套时，单击就是用手套摸她
        if self.mitten_mode:
            self.pet_head()
            return
        # 单次点击 = 戳；2.5 秒内连戳 3 次 = 惹急了，受击
        now = time.monotonic()
        self._click_times = [t for t in self._click_times if now - t < 2.5]
        self._click_times.append(now)
        if len(self._click_times) < 3:
            self.poke()
            return
        self._click_times.clear()
        self.prev_state = self.state if self.state not in ("hit", "drag", "fall", "peek") else "sit"
        dur = self.cfg["timing"]["hit_recover"]
        if random.random() < self.cfg["behavior"]["hit_talk_chance"]:
            _eff, d = self.speak("hit")
            dur = max(dur, d + 0.15)  # 姿势保持到语音播完
        if not self.play_anim("hit", dur,
                              then=lambda: self.play_anim("trans_hit_sit", 4.0,
                                                          then=lambda: self.go("sit", 2.0))):
            self.go("hit", dur)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.pet_head()

    def pet_head(self):
        """撸：被摸头，眯眼蹭手"""
        if self.mitten_mode and self.anims.get("pet_mitten"):
            _eff, dur = self.speak("mitten")
            if not self.play_anim("pet_mitten", max(2.2, dur + 1.2),
                                  then=lambda: self.play_anim("trans_pet_sit", 4.0,
                                                              then=lambda: self.go("sit", 2.0))):
                self.go("pet_head", 2.5)
            return
        _eff, dur = self.speak("pet")
        if not self.play_anim("pet", max(1.5, dur + 0.4),
                              then=lambda: self.play_anim("trans_pet_sit", 4.0,
                                                          then=lambda: self.go("sit", 2.0))):
            self.go("pet_head", max(1.5, dur + 0.4))

    def poke(self):
        """戳：推一下，眼睛瞪圆"""
        _eff, dur = self.speak("poke")
        if not self.play_anim("speak_pain", max(1.2, dur + 0.2)):
            self.go("poke", max(0.8, dur + 0.2))

    def pinch(self):
        _eff, dur = self.speak("pinch")
        if not (self.play_anim("pinch", max(1.4, dur + 0.3),
                               then=lambda: self.play_anim("trans_pinch_sit", 4.0,
                                                           then=lambda: self.go("sit", 2.0)))
                or self.play_anim("pinch", max(1.2, dur + 0.3),
                                  then=lambda: self.play_anim("trans_pinch_sit", 4.0,
                                                              then=lambda: self.go("sit", 2.0)))):
            self.go("pinch", max(1.2, dur + 0.3))

    def hug(self):
        _eff, dur = self.speak("hug")
        if not self.play_anim("hug", max(1.2, dur + 0.3),
                              then=lambda: self.play_anim("trans_hug_sit", 4.0,
                                                          then=lambda: self.go("sit", 2.0))):
            self.go("hug", max(1.2, dur + 0.3))

    def tickle(self):
        _eff, dur = self.speak("tickle")
        if not (self.play_anim("tickle_hand", max(2.4, dur + 1.0),
                               then=lambda: self.play_anim("trans_tickle_sit", 4.0,
                                                           then=lambda: self.go("sit", 2.0)))
                or self.play_anim("tickle", max(1.2, dur + 0.3),
                                  then=lambda: self.play_anim("trans_tickle_sit", 4.0,
                                                              then=lambda: self.go("sit", 2.0)))):
            self.go("tickle", max(1.2, dur + 0.3))

    def start_peek(self, side=None):
        """从屏幕左/右边缘只探出一个脑袋，盯——"""
        side = side or random.choice(["left", "right"])
        g = self.screen_rect()
        self.setFixedSize(self.head_w, self.head_h)
        self.set_pose("head" if side == "right" else "head_l")
        if side == "right":
            x = g.right() - int(self.head_w * 0.55)
        else:
            x = g.left() - int(self.head_w * 0.45)
        y = g.bottom() - self.head_h + 2
        self.move(int(x), int(y))
        self.state = "peek"
        self.state_until = time.monotonic() + 5.0
        self.speak("peek")

    def end_peek(self):
        self.setFixedSize(self.W, self.H)
        self.go("sit", 2.5)
        self._apply_pos()

    def _save_cfg(self):
        try:
            with open(os.path.join(BASE, "config.json"), "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            print("save config failed:", e, flush=True)

    def touch_collar(self):
        """摸摸项圈（故事模式语料）"""
        _eff, dur = self.speak("collar")
        if not self.play_anim("pet", max(2.0, dur + 0.8),
                              then=lambda: self.play_anim("trans_pet_sit", 4.0,
                                                          then=lambda: self.go("sit", 2.0))):
            self.go("sit", 2.5)

    def toggle_ghost_always(self, on):
        self.ghost_always = bool(on)
        self.cfg["ghost_always"] = self.ghost_always
        self._save_cfg()

    def toggle_story_mode(self, on):
        """故事模式：时间线在一切结束之后，台词与行为都变"""
        self.story_mode = bool(on)
        self.cfg["story_mode"] = self.story_mode
        self._save_cfg()
        if self.story_mode:
            # 开场白：隔一拍再说，避免和菜单/动作打架
            QTimer.singleShot(1200, self._story_intro)

    def _play_beg(self):
        """坐姿小表演：抬起前爪讨要，再放下"""
        if self.state != "sit":
            return
        self.play_anim("trans_sit_beg", 3.2, then=self._play_unbeg)

    def _play_unbeg(self):
        self.play_anim("trans_beg_sit", 3.0, then=lambda: self.go("sit", 3.0))

    def _story_intro(self):
        if not getattr(self, "story_mode", False):
            return
        _eff, d = self.speak("intro")
        if self.state in ("idle", "sit"):
            self.play_anim("talk", max(1.8, d + 0.4),
                           then=lambda: self.go("sit", 2.0))

    def toggle_deep_sleep(self, on):
        """沉睡模式：开启后一直睡到被唤醒"""
        self.deep_sleep = bool(on)
        self.cfg["deep_sleep"] = self.deep_sleep
        self._save_cfg()
        if self.deep_sleep:
            self.doze()

    def wake(self):
        """手动醒来：睡着就走过渡，否则直接回待机"""
        if self.deep_sleep:
            self.deep_sleep = False
            self.cfg["deep_sleep"] = False
            self._save_cfg()
        if self.state == "sleep" and self.anims.get("trans_sleep_sit"):
            self.speak("wake")
            self.play_anim("trans_sleep_sit", 4.8, then=lambda: self.go("sit", 2.0))
        else:
            self.go("idle", 2.0)

    def doze(self):
        """手动睡觉：同样先播过渡（没有过渡素材就直接切）"""
        self.speak("sleep")
        if not self.play_anim("trans_sit_sleep", 5.0, then=lambda: self.go("sleep")):
            self.go("sleep")

    def feed(self):
        """投喂苹果：播放吃东西的姿势 + 语音，姿势保持到语音结束"""
        _eff, dur = self.speak("eat")
        self.play_sfx("pet")
        if not self.play_anim("eat", max(2.0, dur + 0.8),
                              then=lambda: self.play_anim("trans_eat_sit", 4.5,
                                                          then=lambda: self.go("sit", 2.0))):
            self.go("eat", max(2.0, dur + 0.8))

    def set_size(self, height):
        """改体积：写进配置后重启进程（比运行时缩放更稳）"""
        if int(self.cfg.get("sprite_height", 300)) == int(height):
            return
        self.cfg["sprite_height"] = int(height)
        try:
            path = os.path.join(BASE, "config.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            print("save config failed:", e, flush=True)
        script = os.path.join(BASE, "main.py")
        QProcess.startDetached(sys.executable, [script])
        QApplication.instance().quit()

    def contextMenuEvent(self, ev):
        m = QMenu(self)

        # 互动：全部放在一级，常用项不该藏进子菜单
        m.addAction("🍎 喂苹果", self.feed)
        m.addAction("✋ 撸一撸", self.pet_head)
        m.addAction("👆 戳一下", self.poke)
        m.addAction("🤏 捏脸", self.pinch)
        m.addAction("🤗 抱抱", self.hug)
        m.addAction("🪶 挠痒痒", self.tickle)
        m.addAction("👀 探头", self.start_peek)
        m.addAction("🎀 摸摸项圈", self.touch_collar)
        act_mitten = m.addAction("🧤 戴上手套")
        act_mitten.setCheckable(True)
        act_mitten.setChecked(bool(getattr(self, "mitten_mode", False)))
        act_mitten.toggled.connect(self.toggle_mitten)

        m.addSeparator()
        m.addAction("睡觉", self.doze)
        m.addAction("醒来", self.wake)

        m.addSeparator()
        act_story = m.addAction("故事模式")
        act_story.setCheckable(True)
        act_story.setChecked(bool(getattr(self, "story_mode", False)))
        act_story.toggled.connect(self.toggle_story_mode)
        act_ghost = m.addAction("幽灵梦境（每次必现）")
        act_ghost.setCheckable(True)
        act_ghost.setChecked(bool(getattr(self, "ghost_always", False)))
        act_ghost.toggled.connect(self.toggle_ghost_always)
        act_deep = m.addAction("沉睡模式（一直睡到叫醒）")
        act_deep.setCheckable(True)
        act_deep.setChecked(bool(getattr(self, "deep_sleep", False)))
        act_deep.toggled.connect(self.toggle_deep_sleep)

        m.addSeparator()
        size_menu = m.addMenu("大小")
        for label, h in (("小 (240)", 240), ("中 (300)", 300), ("大 (380)", 380), ("特大 (460)", 460)):
            act = size_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(int(self.cfg.get("sprite_height", 300)) == h)
            act.triggered.connect(lambda _c=False, hh=h: self.set_size(hh))

        m.addSeparator()
        m.addAction("退出", QApplication.instance().quit)
        m.exec(ev.globalPos())


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8-sig"))
    pet = Pet(cfg)
    pet.show()
    scr = QGuiApplication.primaryScreen()
    print("geom", pet.geometry(), "dpr", pet.devicePixelRatioF(),
          "screen", scr.geometry(), "avail", scr.availableGeometry(),
          "sdpr", scr.devicePixelRatio(), flush=True)
    print("pet running:", pet.W, "x", pet.H)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
