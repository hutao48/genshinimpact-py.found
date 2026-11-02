package com.genshin.detector

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.FileProvider
import java.io.File
import kotlin.math.*

class MainActivity : AppCompatActivity() {
    private lateinit var txtStatus: TextView
    private lateinit var txtNotes: TextView
    private lateinit var txtBpm: TextView
    private lateinit var txtChord: TextView
    private lateinit var txtKey: TextView
    private lateinit var txtLevel: TextView
    private lateinit var txtUpdate: TextView
    private lateinit var btnStart: ToggleButton
    private lateinit var btnUpdate: Button
    private var recording = false
    private var recordThread: Thread? = null
    private var detector: NoteDetector? = null

    companion object {
        const val SAMPLE_RATE = 44100
        const val FFT_SIZE = 4096
        const val APP_VERSION = "1.1.0"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            detector = NoteDetector(0.7f, SAMPLE_RATE)

            val layout = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(48, 96, 48, 48)
                setBackgroundColor(0xFF1C1D21.toInt())
            }

            val title = TextView(this).apply {
                text = "原神乐器演奏检测器 v${APP_VERSION}"
                setTextColor(0xFFE8E8E8.toInt())
                textSize = 20f
                setPadding(0, 0, 0, 24)
            }
            layout.addView(title)

            btnStart = ToggleButton(this).apply {
                textOff = "开始监听"
                textOn = "停止监听"
                setOnCheckedChangeListener { _, checked ->
                    if (checked) startRecording() else stopRecording()
                }
            }
            layout.addView(btnStart)

            txtStatus = TextView(this).apply {
                text = "点击开始，对着游戏扬声器演奏"
                setTextColor(0xFF9AA0A6.toInt())
                setPadding(0, 24, 0, 8)
            }
            layout.addView(txtStatus)

            txtLevel = TextView(this).apply {
                text = "电平: -- dB"
                setTextColor(0xFF4AA3FF.toInt())
                setPadding(0, 0, 0, 8)
            }
            layout.addView(txtLevel)

            layout.addView(smallLabel("当前 BPM"))
            txtBpm = bigLabel("—", 40f, 0xFFF5A623.toInt())
            layout.addView(txtBpm)

            layout.addView(smallLabel("当前调性"))
            txtKey = bigLabel("—", 20f, 0xFFF5A623.toInt())
            layout.addView(txtKey)

            layout.addView(smallLabel("和弦"))
            txtChord = bigLabel("—", 18f, 0xFF34C759.toInt())
            layout.addView(txtChord)

            layout.addView(smallLabel("当前按键"))
            txtNotes = bigLabel("—", 22f, 0xFF4AA3FF.toInt())
            layout.addView(txtNotes)

            btnUpdate = Button(this).apply {
                text = "检查更新"
                setOnClickListener { checkForUpdates() }
            }
            layout.addView(btnUpdate)

            txtUpdate = TextView(this).apply {
                text = "当前版本 $APP_VERSION"
                setTextColor(0xFF9AA0A6.toInt())
                textSize = 13f
                setPadding(0, 8, 0, 0)
            }
            layout.addView(txtUpdate)

            setContentView(layout)

            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            }
        } catch (e: Exception) {
            Log.e("GenshinDetector", "onCreate error", e)
        }
    }

    private fun smallLabel(t: String) = TextView(this).apply {
        text = t; setTextColor(0xFF9AA0A6.toInt()); setPadding(0, 24, 0, 4)
    }
    private fun bigLabel(t: String, sz: Float, color: Int) = TextView(this).apply {
        text = t; textSize = sz; setTextColor(color)
    }

    private fun checkForUpdates() {
        if (!btnUpdate.isEnabled) return
        btnUpdate.isEnabled = false
        txtUpdate.text = "正在检查更新…"
        Thread {
            try {
                val rel = UpdateChecker.latest()
                if (rel == null) {
                    runOnUiThread {
                        txtUpdate.text = "已是最新版本 ($APP_VERSION)"
                        btnUpdate.isEnabled = true
                    }
                    return@Thread
                }
                runOnUiThread { txtUpdate.text = "发现 v${rel.version}，正在下载…" }
                val file = UpdateChecker.download(this, rel)
                runOnUiThread {
                    txtUpdate.text = "下载完成，正在打开安装程序…"
                    installApk(file)
                    btnUpdate.isEnabled = true
                }
            } catch (e: Exception) {
                Log.e("GenshinDetector", "update failed", e)
                runOnUiThread {
                    txtUpdate.text = "更新失败：${e.message ?: "网络错误"}"
                    btnUpdate.isEnabled = true
                }
            }
        }.start()
    }

    private fun installApk(file: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !packageManager.canRequestPackageInstalls()) {
            txtUpdate.text = "请允许安装未知来源应用后重试"
            try {
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:$packageName")))
            } catch (e: Exception) {
                Log.e("GenshinDetector", "open install settings failed", e)
            }
            return
        }
        try {
            val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)
        } catch (e: Exception) {
            Log.e("GenshinDetector", "install apk failed", e)
            txtUpdate.text = "无法打开安装程序：${e.message ?: "未知错误"}"
        }
    }

    private fun startRecording() {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            btnStart.isChecked = false
            txtStatus.text = "未获得麦克风权限"
            return
        }
        recording = true
        txtStatus.text = "正在监听麦克风…"
        recordThread = Thread {
            var rec: AudioRecord? = null
            try {
                val rates = intArrayOf(44100, 48000, 32000)
                var bestRate = 0
                var bestBuf = 0
                for (r in rates) {
                    val minBuf = AudioRecord.getMinBufferSize(r,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                    if (minBuf > 0) {
                        bestRate = r
                        bestBuf = maxOf(minBuf, FFT_SIZE * 4)
                        break
                    }
                }
                Log.i("GenshinDetector", "Using rate=$bestRate buf=$bestBuf")
                if (bestRate == 0 || bestBuf <= 0) {
                    recording = false
                    runOnUiThread {
                        btnStart.isChecked = false
                        txtStatus.text = "无法初始化音频采集"
                    }
                    return@Thread
                }

                rec = AudioRecord(MediaRecorder.AudioSource.MIC, bestRate,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, bestBuf)
                rec.startRecording()
                // 检测器按实际采样率创建；时间戳由检测器内部的样本时钟给出（不再用系统时间），
                // 帧之间按 1024 样本重叠，读块长度不再影响时间精度
                val det = NoteDetector(0.7f, bestRate)
                detector = det
                val buf = ShortArray(FFT_SIZE)
                while (recording) {
                    val n = rec.read(buf, 0, FFT_SIZE)
                    if (n <= 0) continue
                    val mono = FloatArray(n) { buf[it] / 32768f }
                    var sum = 0.0
                    for (v in mono) sum += v * v
                    val rms = sqrt(sum / n)
                    det.feedSamples(mono, n)
                    // 在采集线程里取快照再交给 UI 线程，避免 UI 线程遍历检测器内部的 Map 时被并发修改
                    val bpmV = det.bpm
                    val labels = det.activeLabels.joinToString("  ")
                    val tonality = det.tonality
                    val chord = det.chord
                    runOnUiThread {
                        val db = if (rms > 0.0001) 20 * log10(rms).toFloat() else -99f
                        txtLevel.text = "电平: %.1f dB".format(db)
                        updateUI(bpmV, labels, tonality, chord)
                    }
                }
                rec.stop(); rec.release()
            } catch (e: Exception) {
                Log.e("GenshinDetector", "recording error", e)
                rec?.release()
                recording = false
                runOnUiThread {
                    btnStart.isChecked = false
                    txtStatus.text = "采集出错，请重试"
                }
            }
        }
        recordThread?.start()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1 && (grantResults.isEmpty() || grantResults[0] != PackageManager.PERMISSION_GRANTED)) {
            btnStart.isChecked = false
            txtStatus.text = "未获得麦克风权限"
        }
    }

    override fun onPause() {
        if (recording) {
            stopRecording()
            btnStart.isChecked = false
            txtStatus.text = "已暂停"
        }
        super.onPause()
    }

    override fun onDestroy() {
        recording = false
        recordThread?.join(1000)
        recordThread = null
        super.onDestroy()
    }

    private fun stopRecording() {
        recording = false
        recordThread?.join(1000)
        txtStatus.text = "已停止"
    }

    private fun updateUI(bpm: Float?, labels: String, tonality: String, chord: String?) {
        txtBpm.text = bpm?.let { String.format("%.1f", it) } ?: "—"
        txtKey.text = tonality
        txtChord.text = chord ?: "—"
        txtNotes.text = labels
    }
}
