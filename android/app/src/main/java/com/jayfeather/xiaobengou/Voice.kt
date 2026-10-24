package com.jayfeather.xiaobengou

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.SoundPool
import org.json.JSONObject

/**
 * 声音：短音效用 SoundPool，语音用 MediaPlayer（WAV）。
 * 语音清单来自 assets/voice/manifest.json，与桌面版共用。
 */
class Voice(private val context: Context) {

    private val sfx = SoundPool.Builder()
        .setMaxStreams(4)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
        ).build()

    private val sfxIds = HashMap<String, Int>()
    private var player: MediaPlayer? = null

    /** 各类台词的文件名列表 */
    private val lines = HashMap<String, MutableList<String>>()

    fun load() {
        // 音效
        for (name in listOf("hit", "sit", "pet", "step")) {
            try {
                context.assets.openFd("sfx/$name.wav").use { fd ->
                    sfxIds[name] = sfx.load(fd, 1)
                }
            } catch (e: Exception) {
                // 缺音效不致命
            }
        }
        // 语音清单
        try {
            val json = context.assets.open("voice/manifest.json").bufferedReader().use { it.readText() }
            val root = JSONObject(json)
            val obj = root.optJSONObject("lines") ?: return
            for (key in obj.keys()) {
                val item = obj.getJSONObject(key)
                // 桌面版用 mode 区分语气；安卓先统一按普通台词处理
                val files = item.optJSONObject("files") ?: continue
                val list = lines.getOrPut("all") { mutableListOf() }
                for (vKey in files.keys()) {
                    val f = files.getJSONObject(vKey).optString("file")
                    if (f.isNotEmpty()) list.add(f)
                }
                // 按 id 前缀分类：hit_ / sleep_ / pet_ 等
                val prefix = key.substringBefore('_')
                if (key.contains('_')) list.also { lines.getOrPut(prefix) { mutableListOf() }.addAll(0, emptyList()) }
            }
        } catch (e: Exception) {
            // 没有语音也能跑
        }
    }

    fun playSfx(name: String, volume: Float = 1f) {
        val id = sfxIds[name] ?: return
        try {
            sfx.play(id, volume, volume, 1, 0, 1f)
        } catch (e: Exception) {
        }
    }

    /** 随机播一条该类别台词；返回时长毫秒（未知则 1200） */
    fun speak(category: String): Int {
        val list = lines[category] ?: lines["all"] ?: return 1200
        if (list.isEmpty()) return 1200
        val file = list.random()
        return try {
            player?.release()
            val p = MediaPlayer()
            context.assets.openFd("voice/$file").use { fd ->
                p.setDataSource(fd.fileDescriptor, fd.startOffset, fd.length)
            }
            p.prepare()
            p.start()
            player = p
            p.duration.coerceAtLeast(600)
        } catch (e: Exception) {
            1200
        }
    }

    fun release() {
        player?.release()
        player = null
        sfx.release()
    }
}
