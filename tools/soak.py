import os
import sys
import json
import random
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
QTest.qWait(200)

errors = []
actions = ["feed", "pet_head", "poke", "pinch", "hug", "tickle", "touch_collar",
           "doze", "wake", "_play_beg"]
t0 = time.time()
n = 0
while time.time() - t0 < 55:
    try:
        a = random.choice(actions)
        getattr(pet, a)()
        n += 1
        QTest.qWait(random.randint(150, 400))
        if pet.width() <= 0 or pet.mask().isEmpty():
            errors.append(f"{a}: 窗口/遮罩异常")
    except Exception as e:
        errors.append(f"{a}: {type(e).__name__}: {e}")
        traceback.print_exc()

print("触发动作次数:", n)
print("异常:", len(errors))
for e in errors[:5]:
    print("  ", e)
print("最终状态:", pet.state, "窗口", pet.width(), pet.height())
app.quit()
