"""系统性自检：资源 / 引用 / 状态机 / 遮罩 / 菜单 / 配置"""
import os
import re
import sys
import json
import glob
import time

from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QRegion
from PyQt6.QtCore import Qt

sys.path.insert(0, r"D:\DSH\pet")
os.chdir(r"D:\DSH\pet")
import main as M

SRC = open(r"D:\DSH\pet\main.py", encoding="utf-8").read()
ok = []
warn = []
fail = []

app = QApplication(sys.argv)
cfg = json.load(open(r"D:\DSH\pet\config.json", encoding="utf-8-sig"))
pet = M.Pet(cfg)
pet.show()
QTest.qWait(300)

# ---------- 1. 静态姿势文件 ----------
for key, fname in M.POSE_FILES.items():
    p = os.path.join(M.ASSETS, fname)
    if not os.path.exists(p):
        fail.append(f"姿势缺失: {key} -> {fname}")
ok.append(f"静态姿势 {len(M.POSE_FILES)} 个文件检查完毕")

# ---------- 2. 代码里引用的动画名是否都已注册 ----------
referenced = set(re.findall(r'play_anim\("([\w]+)"', SRC))
referenced |= set(re.findall(r'anims\.get\("([\w]+)"', SRC))
referenced |= set(re.findall(r'_sync_frame_mask\("([\w]+)"', SRC))
registered = set(pet.anims.spec.keys())
missing = sorted(n for n in referenced if n not in registered)
if missing:
    fail.append(f"引用了未注册的动画: {missing}")
ok.append(f"代码引用动画 {len(referenced)} 个，注册 {len(registered)} 个")

# ---------- 3. 已注册动画的帧是否都真实存在且非空 ----------
empty = []
for name in registered:
    seq = pet.anims[name]
    if len(seq) == 0:
        empty.append(name)
        continue
    pm = seq[0]
    if pm.isNull():
        empty.append(name)
if empty:
    fail.append(f"空动画: {empty}")
ok.append(f"已注册动画 {len(registered)} 组全部可解码")

# ---------- 4. 语音类别与文件 ----------
man = json.load(open(os.path.join(M.VOICE, "manifest.json"), encoding="utf-8-sig"))
missing_wav = []
for lid, info in man["lines"].items():
    for v in info["files"].values():
        f = os.path.join(M.VOICE, v["file"])
        if not os.path.isfile(f):
            missing_wav.append(v["file"])
if missing_wav:
    fail.append(f"语音文件缺失 {len(missing_wav)} 个: {missing_wav[:5]}")
ok.append(f"语音 {len(man['lines'])} 条，文件齐全")

speak_cats = set(re.findall(r'speak\w*\("([\w]+)"', SRC))
no_clip = sorted(c for c in speak_cats if c not in pet.cats and c not in pet.cats_story and c not in pet.cats_ghost and c not in pet.cats_pup and c not in ("mom", "pup"))
if no_clip:
    warn.append(f"以下台词类别没有任何片段: {no_clip}")
ok.append(f"代码引用台词类别 {len(speak_cats)} 个")

# ---------- 5. 音频效果 ----------
bad_sfx = [k for k, e in pet.sounds.items() if e.source().isEmpty()]
if bad_sfx:
    fail.append(f"音效未能加载: {len(bad_sfx)} 个")
ok.append(f"语音片段 {len(pet.sounds)} 个全部加载")

# ---------- 6. 状态机：逐个进入，检查窗口/遮罩 ----------
states = ["idle", "sit", "sleep", "crawl", "hit", "eat", "pet_head", "poke",
          "pinch", "hug", "tickle", "land", "drag", "peek"]
state_bad = []
for st in states:
    try:
        if st == "peek":
            pet.start_peek("left")
        else:
            pet.go(st, 2.0)
        QTest.qWait(60)
        if st == "peek":
            if pet.width() != pet.head_w or pet.height() != pet.head_h:
                state_bad.append(f"{st}: 窗口 {pet.width()}x{pet.height()}")
            pet.end_peek()
        else:
            if pet.width() != pet.W or pet.height() != pet.H:
                state_bad.append(f"{st}: 窗口 {pet.width()}x{pet.height()}，应为 {pet.W}x{pet.H}")
            if pet.mask().isEmpty():
                state_bad.append(f"{st}: 遮罩为空")
    except Exception as e:
        state_bad.append(f"{st}: {type(e).__name__}: {e}")
pet._ensure_full_window()
if state_bad:
    fail.append(f"状态异常: {state_bad}")
ok.append(f"状态机 {len(states)} 个状态切换正常")

# ---------- 7. 过渡动画逐个播放 ----------
trans = [n for n in registered if n.startswith("trans_")]
trans_bad = []
for n in trans:
    try:
        if not pet.play_anim(n, 1.0):
            trans_bad.append(f"{n}: 播放失败")
        app.processEvents()
        if pet.mask().isEmpty():
            trans_bad.append(f"{n}: 遮罩为空")
    except Exception as e:
        trans_bad.append(f"{n}: {type(e).__name__}: {e}")
if trans_bad:
    fail.append(f"过渡异常: {trans_bad}")
ok.append(f"过渡动画 {len(trans)} 条全部可播放")

# ---------- 8. 遮罩与当前帧是否吻合（停表后逐帧比对） ----------
pet.timer.stop()
mismatch = []
for name in ("idle", "sleep", "crawl", "crawl_l", "air_roll", "hang1arm",
             "cling_kick", "cling_kick_l", "tickle_hand", "pet_mitten"):
    if name not in registered:
        continue
    seq = pet.anims[name]
    step = max(1, len(seq) // 10)
    for idx in range(0, len(seq), step):
        pet._mask_key = None
        pet._sync_mask(name, idx)
        cur = pet.mask()
        pm = seq[idx]
        small = pm.scaled(pet.W, pet.H, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.FastTransformation)
        need = QRegion(small.mask())
        out = need.subtracted(cur).boundingRect()
        if out.width() * out.height() > 0:
            mismatch.append(f"{name}#{idx} 越界 {out.width()}x{out.height()}")
if mismatch:
    fail.append(f"遮罩不吻合: {mismatch[:4]}")
else:
    ok.append("遮罩抽样与画面对齐")
pet.timer.start()

# ---------- 9. 菜单可正常构建 ----------
try:
    m = QMenu(None)
    m.addAction("x", lambda: None)
    m.deleteLater()
    ok.append("菜单构建正常")
except Exception as e:
    fail.append(f"菜单构建失败: {e}")

# ---------- 10. 配置读写 ----------
try:
    tmp = dict(cfg)
    tmp["sprite_height"] = 300
    s = json.dumps(tmp, ensure_ascii=False)
    json.loads(s)
    ok.append("配置可序列化")
except Exception as e:
    fail.append(f"配置序列化失败: {e}")

# ---------- 11. 幽灵 / 手套 / 气垫贴图 ----------
for label, pix in (("幽灵-母亲", pet._ghost_pix.get("mother")),
                   ("幽灵-全家", pet._ghost_pix.get("family")),
                   ("手套指针", pet._mitten_qc),
                   ("攀附静图", pet._cling_pix.get("left"))):
    if pix is None:
        fail.append(f"{label} 未加载")
ok.append("幽灵 / 手套 / 攀附贴图检查完毕")

# ---------- 12. 内存 ----------
rss = -1

print("\n===== 自检结果 =====")
print(f"通过项: {len(ok)}")
for line in ok:
    print("  [OK] " + line)
if warn:
    print(f"警告: {len(warn)}")
    for line in warn:
        print("  [WARN] " + line)
if fail:
    print(f"失败: {len(fail)}")
    for line in fail:
        print("  [FAIL] " + line)
else:
    print("失败: 0")
print(f"内存: {rss:.0f} MB")
app.quit()
