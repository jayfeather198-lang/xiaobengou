"""运行时交互自检：逐个调用交互入口，捕获异常并检查状态是否合法"""
import os
import sys
import json
import time
import traceback

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

sys.path.insert(0, r"D:\DSH\pet")
os.chdir(r"D:\DSH\pet")
import main as M

app = QApplication(sys.argv)
cfg = json.load(open(r"D:\DSH\pet\config.json", encoding="utf-8-sig"))
pet = M.Pet(cfg)
pet.show()
QTest.qWait(300)

results = []


def run(label, fn, wait=350):
    try:
        fn()
        QTest.qWait(wait)
        w, h = pet.width(), pet.height()
        mask = pet.mask().boundingRect()
        state = pet.state
        bad = []
        if w <= 0 or h <= 0:
            bad.append(f"窗口 {w}x{h}")
        if mask.isEmpty():
            bad.append("遮罩为空")
        if bad:
            results.append(("WARN", label, f"state={state} " + " / ".join(bad)))
        else:
            results.append(("OK", label, f"state={state} win={w}x{h}"))
    except Exception as e:
        results.append(("FAIL", label, f"{type(e).__name__}: {e}"))
        traceback.print_exc()


run("喂苹果", pet.feed, 700)
run("撸一撸", pet.pet_head, 700)
run("戳一下", pet.poke, 500)
run("捏脸", pet.pinch, 700)
run("抱抱", pet.hug, 700)
run("挠痒痒", pet.tickle, 900)
run("摸摸项圈", pet.touch_collar, 600)
run("探头", lambda: (pet.start_peek("left"), QTest.qWait(400), pet.end_peek()), 500)
run("睡觉", pet.doze, 700)
run("醒来", pet.wake, 700)
run("故事模式开", lambda: pet.toggle_story_mode(True), 400)
run("故事模式关", lambda: pet.toggle_story_mode(False), 300)
run("幽灵必现开", lambda: pet.toggle_ghost_always(True), 200)
run("幽灵必现关", lambda: pet.toggle_ghost_always(False), 200)
run("沉睡模式开", lambda: pet.toggle_deep_sleep(True), 700)
run("沉睡模式关", lambda: pet.toggle_deep_sleep(False), 300)
run("戴手套开", lambda: pet.toggle_mitten(True), 300)
run("戴手套关", lambda: pet.toggle_mitten(False), 300)
run("坐姿小表演", pet._play_beg, 600)
run("抓边-左", lambda: (setattr(pet, "fx", pet.screen_rect().left() + 6),
                       setattr(pet, "fy", pet.screen_rect().top() + 500),
                       pet._try_grab_edge()), 500)
run("抓边-上", lambda: (pet.end_hang(climb=True),
                       setattr(pet, "fx", pet.screen_rect().left() + 700),
                       setattr(pet, "fy", pet.screen_rect().top() + pet.H),
                       pet._try_grab_edge()), 500)
run("松手掉落", lambda: (pet.end_hang(climb=True), pet.go("drag", 1.0),
                       setattr(pet, "state", "fall"),
                       setattr(pet, "vy", 0.0),
                       setattr(pet, "_fall_from", pet.fy)), 1200)

print("\n===== 运行时自检 =====")
bad = 0
for level, label, info in results:
    print(f"  [{level}] {label}: {info}")
    if level != "OK":
        bad += 1
print(f"总计 {len(results)} 项，异常 {bad} 项")
app.quit()
