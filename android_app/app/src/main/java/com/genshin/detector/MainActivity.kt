package com.genshin.detector

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.util.Log
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import kotlin.math.*

class MainActivity : AppCompatActivity() {
    private lateinit var txtStatus: TextView
    private lateinit var txtNotes: TextView
    private lateinit var txtBpm: TextView
    private lateinit var txtChord: TextView
    private lateinit var txtKey: TextView
    private lateinit var txtLevel: TextView
    private lateinit var btnStart: ToggleButton
    private var recording = false
    private var recordThread: Thread? = null
    private var detector: NoteDetector? = null

    companion object {
        const val SAMPLE_RATE = 44100
        const val FFT_SIZE = 4096
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
                text = "原神乐器演奏检测器 v1.0.2"
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

    private fun startRecording() {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1)
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
            }
        }
        recordThread?.start()
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
