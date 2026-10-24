package com.jayfeather.xiaobengou

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(60, 120, 60, 60)
        }
        val title = TextView(this).apply {
            text = "小小笨狗"
            textSize = 26f
        }
        status = TextView(this).apply {
            textSize = 15f
            setPadding(0, 30, 0, 30)
        }
        val grant = Button(this).apply {
            text = "① 授予悬浮窗权限"
            setOnClickListener {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    )
                )
            }
        }
        val start = Button(this).apply {
            text = "② 让她出来"
            setOnClickListener {
                if (!canOverlay()) {
                    status.text = "还没有悬浮窗权限，先点第 ① 步"
                    return@setOnClickListener
                }
                startForegroundService(Intent(this@MainActivity, OverlayService::class.java))
                status.text = "她已经出来了，去看看桌面～"
            }
        }
        val stop = Button(this).apply {
            text = "③ 让她回家"
            setOnClickListener {
                stopService(Intent(this@MainActivity, OverlayService::class.java))
                status.text = "已收起"
            }
        }
        val hint = TextView(this).apply {
            textSize = 13f
            setPadding(0, 40, 0, 0)
            text = """
                操作说明：
                · 点一下 —— 她会喊痛
                · 点两下 —— 撸一撸
                · 按住拖动 —— 拎起来，松手会掉下去
                · 长按 —— 让她睡 / 叫醒
                · 通知栏里的「回家」可以随时收起

                部分手机（小米 / 华为 / OPPO / vivo）还需要在
                「设置 → 应用 → 小小笨狗」里额外允许后台运行与自启动，
                否则锁屏或切后台后可能会被系统清掉。
            """.trimIndent()
        }

        askNotifications()
        root.addView(title)
        root.addView(status)
        root.addView(grant)
        root.addView(start)
        root.addView(stop)
        root.addView(hint)
        setContentView(root)
    }

    private fun askNotifications() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") !=
                android.content.pm.PackageManager.PERMISSION_GRANTED
            ) {
                requestPermissions(arrayOf("android.permission.POST_NOTIFICATIONS"), 1)
            }
        }
    }

    private fun canOverlay(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Settings.canDrawOverlays(this) else true

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) {
            status.text = if (canOverlay()) {
                if (OverlayService.running) "状态：正在桌面上" else "状态：已授权，还没叫她出来"
            } else {
                "状态：缺少悬浮窗权限"
            }
        }
    }
}
