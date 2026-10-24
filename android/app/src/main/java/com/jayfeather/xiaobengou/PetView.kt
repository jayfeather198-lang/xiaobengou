package com.jayfeather.xiaobengou

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.view.Choreographer
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.random.Random

/**
 * 宠物本体：负责逐帧绘制、状态机、触摸手势。
 * 位置由 OverlayService 通过 layoutParams 控制，这里只报告位移与事件。
 */
@SuppressLint("ViewConstructor")
class PetView(
    context: Context,
    private val store: AnimStore,
    private val voice: Voice,
) : View(context), Choreographer.FrameCallback {

    interface Host {
        fun moveBy(dx: Int, dy: Int)
        fun requestMenu()
        fun onFell()
        fun floorY(): Int      // 桌面底边（屏幕坐标）
        fun curY(): Int        // 当前窗口顶部（屏幕坐标）
    }

    var host: Host? = null

    private val paint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private var frame: Bitmap? = null

    // 当前动画
    private var animName = "idle"
    private var animIndex = 0
    private var animTime = 0f
    private var loop = true
    private var onEnd: (() -> Unit)? = null

    private var state = "idle"
    private var stateUntil = 0L

    // 拖拽 / 手势
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var lastY = 0f
    private var downAt = 0L
    private var dragging = false
    private var lastTapAt = 0L

    // 下落
    private var vy = 0f
    private var falling = false

    private var lastFrameAt = 0L
    private var running = false

    private val fps = 24f

    init {
        setBackgroundColor(Color.TRANSPARENT)
        play("idle", true)
    }

    // ---------- 动画控制 ----------
    fun play(name: String, looping: Boolean, then: (() -> Unit)? = null) {
        if (!store.has(name)) {
            then?.invoke()
            return
        }
        animName = name
        animIndex = 0
        animTime = 0f
        loop = looping
        onEnd = then
        store.prefetch(name, 0)
        updateFrame()
    }

    private fun updateFrame() {
        frame = store.get(animName, animIndex)
        invalidate()
    }

    private fun advance(dt: Float) {
        val count = store.frameCount(animName)
        if (count <= 0) return
        animTime += dt
        val per = 1f / fps
        while (animTime >= per) {
            animTime -= per
            animIndex++
            if (animIndex >= count) {
                if (loop) {
                    animIndex = 0
                } else {
                    animIndex = count - 1
                    val cb = onEnd
                    onEnd = null
                    cb?.invoke()
                    break
                }
            }
        }
        updateFrame()
    }

    // ---------- 状态 ----------
    fun goSleep() {
        state = "sleep"
        play("sleep", true)
    }

    fun wake() {
        state = "idle"
        stateUntil = System.currentTimeMillis() + 15000
        play("idle", true)
    }

    fun poke() {
        if (falling) return
        val wasSleep = state == "sleep"
        state = "hit"
        voice.playSfx("hit", 0.9f)
        val dur = voice.speak("hit")
        play("hit", false) {
            if (wasSleep) goSleep() else backToIdle()
        }
        stateUntil = System.currentTimeMillis() + maxOf(900, dur)
    }

    fun pet() {
        if (falling) return
        state = "pet"
        voice.playSfx("pet", 0.8f)
        val dur = voice.speak("pet")
        play("pet", false) { backToIdle() }
        stateUntil = System.currentTimeMillis() + maxOf(1200, dur)
    }

    private fun backToIdle() {
        state = "idle"
        stateUntil = System.currentTimeMillis() + Random.nextLong(12000, 26000)
        val variants = listOf("idle", "idle2", "idle3").filter { store.has(it) }
        play(variants.randomOrNull() ?: "idle", true)
    }

    // ---------- 帧循环 ----------
    override fun doFrame(nanos: Long) {
        if (!running) return
        val now = System.currentTimeMillis()
        val dt = if (lastFrameAt == 0L) 0f else (now - lastFrameAt) / 1000f
        lastFrameAt = now

        if (falling) {
            stepFall(dt)
        } else {
            advance(dt.coerceAtMost(0.1f))
            // 长时间空闲后自己睡着
            if (state == "idle" && now > stateUntil) {
                if (Random.nextFloat() < 0.55f) {
                    goSleep()
                } else {
                    stateUntil = now + Random.nextLong(12000, 26000)
                }
            }
        }
        Choreographer.getInstance().postFrameCallback(this)
    }

    private fun stepFall(dt: Float) {
        vy += 2600f * dt
        val dy = (vy * dt).toInt()
        host?.moveBy(0, dy)
        // 快落地时切空中翻滚
        val floor = host?.floorY() ?: 0
        val cur = host?.curY() ?: 0
        val remain = floor - cur
        if (remain < height * 1.2 && store.has("air_roll") && animName != "air_roll") {
            play("air_roll", false)
        }
        if (remain <= 0) {
            falling = false
            vy = 0f
            voice.playSfx("step", 0.9f)
            play("land", false) { backToIdle() }
            host?.onFell()
        }
    }

    // ---------- 触摸 ----------
    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.rawX; downY = event.rawY
                lastX = downX; lastY = downY
                downAt = System.currentTimeMillis()
                dragging = false
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = event.rawX - lastX
                val dy = event.rawY - lastY
                lastX = event.rawX; lastY = event.rawY
                if (!dragging && (abs(event.rawX - downX) > 12 || abs(event.rawY - downY) > 12)) {
                    dragging = true
                    if (falling) falling = false
                    state = "drag"
                    play("pick", true)
                }
                if (dragging) host?.moveBy(dx.toInt(), dy.toInt())
                return true
            }
            MotionEvent.ACTION_UP -> {
                val held = System.currentTimeMillis() - downAt
                if (dragging) {
                    startFallIfNeeded()
                } else if (held > 600) {
                    host?.requestMenu()
                } else {
                    val now = System.currentTimeMillis()
                    if (now - lastTapAt < 320) {
                        lastTapAt = 0
                        pet()
                    } else {
                        lastTapAt = now
                        poke()
                    }
                }
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun startFallIfNeeded() {
        val floor = host?.floorY() ?: return
        val cur = host?.curY() ?: return
        if (cur < floor - height / 3) {
            falling = true
            vy = 0f
            state = "fall"
            play("drag", true)
        } else {
            backToIdle()
        }
    }

    // ---------- 绘制 ----------
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bmp = frame ?: return
        val src = Rect(0, 0, bmp.width, bmp.height)
        canvas.drawBitmap(bmp, src, Rect(0, 0, width, height), paint)
    }

    fun stateIsSleeping(): Boolean = state == "sleep"

    fun start() {
        if (running) return
        running = true
        lastFrameAt = 0L
        stateUntil = System.currentTimeMillis() + 15000
        Choreographer.getInstance().postFrameCallback(this)
    }

    fun stop() {
        running = false
        Choreographer.getInstance().removeFrameCallback(this)
    }
}
