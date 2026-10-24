package com.jayfeather.xiaobengou

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.graphics.Point
import android.os.Build
import android.os.IBinder
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.WindowManager
import android.widget.Toast

/**
 * 悬浮窗服务：把 PetView 挂到 WindowManager 上，浮在所有应用之上。
 * 需要 SYSTEM_ALERT_WINDOW 权限。
 */
class OverlayService : Service(), PetView.Host {

    companion object {
        const val CHANNEL_ID = "xiaobengou"
        const val NOTIF_ID = 1001
        @Volatile
        var running = false
    }

    private lateinit var wm: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private var pet: PetView? = null
    private var store: AnimStore? = null
    private var voice: Voice? = null
    private var screen = Point(0, 0)
    private var petHeightPx = 0

    override fun onCreate() {
        super.onCreate()
        running = true
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        screen = Point(metrics.widthPixels, metrics.heightPixels)

        startForeground(NOTIF_ID, buildNotification())

        val s = AnimStore(assets)
        val v = Voice(this).apply { load() }
        store = s
        voice = v

        // 尺寸：按屏幕高度取比例，保持帧的宽高比
        val first = s.get("idle", 0)
        val aspect = if (first != null && first.height > 0) {
            first.width.toFloat() / first.height
        } else 1.0f
        petHeightPx = (screen.y * 0.28f).toInt().coerceIn(320, 900)
        val petWidthPx = (petHeightPx * aspect).toInt()

        val view = PetView(this, s, v)
        view.host = this
        pet = view

        params = WindowManager.LayoutParams(
            petWidthPx,
            petHeightPx,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (screen.x - petWidthPx) / 2
            y = screen.y - petHeightPx - 120
        }

        try {
            wm.addView(view, params)
            view.start()
        } catch (e: Exception) {
            toast("悬浮窗创建失败：${e.message}")
        }
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "小小笨狗", NotificationManager.IMPORTANCE_MIN)
            ch.setShowBadge(false)
            nm.createNotificationChannel(ch)
        }
        val stop = PendingIntent.getService(
            this, 1,
            Intent(this, OverlayService::class.java).setAction("stop"),
            PendingIntent.FLAG_IMMUTABLE
        )
        val open = PendingIntent.getActivity(
            this, 2,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            Notification.Builder(this, CHANNEL_ID)
        else
            @Suppress("DEPRECATION") Notification.Builder(this))
            .setContentTitle("小小笨狗在外面玩")
            .setContentText("点通知可以设置，或在这里让她回家")
            .setSmallIcon(android.R.drawable.ic_menu_gallery)
            .setContentIntent(open)
            .addAction(
                Notification.Action.Builder(
                    android.graphics.drawable.Icon.createWithResource(
                        this, android.R.drawable.ic_menu_close_clear_cancel
                    ),
                    "回家", stop
                ).build()
            )
            .setOngoing(true)
            .build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        pet?.stop()
        pet?.let {
            try {
                wm.removeView(it)
            } catch (e: Exception) {
            }
        }
        voice?.release()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ---------- Host ----------
    override fun moveBy(dx: Int, dy: Int) {
        params.x = (params.x + dx).coerceIn(-params.width / 3, screen.x - params.width * 2 / 3)
        params.y = (params.y + dy).coerceIn(0, screen.y - params.height)
        pet?.let {
            try {
                wm.updateViewLayout(it, params)
            } catch (e: Exception) {
            }
        }
    }

    override fun requestMenu() {
        val p = pet ?: return
        if (p.stateIsSleeping()) {
            p.wake()
            toast("醒啦")
        } else {
            p.goSleep()
            toast("睡着啦")
        }
    }

    override fun onFell() {}

    override fun floorY(): Int = screen.y - params.height

    override fun curY(): Int = params.y

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}
