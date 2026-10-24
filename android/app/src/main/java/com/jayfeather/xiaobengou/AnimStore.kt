package com.jayfeather.xiaobengou

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.util.LinkedHashMap

/**
 * 动画帧仓库：只在用到时解码，最多缓存 MAX 张位图（约 40 MB 上限）。
 * 与桌面版同一套思路，避免一次性把上百 MB 图片读进内存。
 */
class AnimStore(private val assets: AssetManager, private val maxCached: Int = 60) {

    private val frameNames = HashMap<String, List<String>>()
    private val cache = object : LinkedHashMap<String, Bitmap>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Bitmap>?): Boolean {
            return size > maxCached
        }
    }

    /** 列出 assets/anim 下所有动画名 */
    fun listAnims(): List<String> {
        return try {
            assets.list("anim")?.filter { name ->
                (assets.list("anim/$name/frames")?.isNotEmpty() == true)
            } ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun framesOf(name: String): List<String> {
        return frameNames.getOrPut(name) {
            (assets.list("anim/$name/frames")?.toList() ?: emptyList())
                .filter { it.endsWith(".webp") || it.endsWith(".png") }
                .sorted()
        }
    }

    fun frameCount(name: String): Int = framesOf(name).size

    fun has(name: String): Boolean = frameCount(name) > 0

    fun get(name: String, index: Int): Bitmap? {
        val frames = framesOf(name)
        if (frames.isEmpty()) return null
        val i = index.coerceIn(0, frames.size - 1)
        val key = "$name/$i"
        cache[key]?.let { return it }
        return try {
            assets.open("anim/${name}/frames/${frames[i]}").use { stream ->
                BitmapFactory.decodeStream(stream)?.also { cache[key] = it }
            }
        } catch (e: Exception) {
            null
        }
    }

    fun prefetch(name: String, from: Int, count: Int = 8) {
        for (i in from until (from + count)) {
            if (i < frameCount(name)) get(name, i)
        }
    }
}
