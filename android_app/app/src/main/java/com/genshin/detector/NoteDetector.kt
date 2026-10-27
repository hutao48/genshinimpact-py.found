package com.genshin.detector

import kotlin.math.*

/**
 * 音高 / 起音 / BPM 检测器 - 21 键风物之诗琴
 * Q-U=C5-B5, A-J=C4-B4, Z-M=C3-B3
 *
 * 与桌面版 detection.py 同步的关键修复：
 *  1. 时间基准改为音频样本时钟，并按 1024 帧移做重叠分帧。原实现每次 read 4096 个样本当作一帧、
 *     用系统时间打时间戳：时间分辨率只有 93 ms，confirm=4 帧意味着 ~370 ms 的确认延迟，起音时刻抖动大。
 *  2. 细分辨率起音函数（1024 窗 / 256 帧移，log 谱通量 + 频率最大值滤波）定位真实敲击时刻；
 *     其后总功率下降的通量峰（硬截止"咔哒"）不算起音。
 *  3. 起音须有"音高证据"：某个琴键频点在起音前后整窗比较上升 ≥2 dB。同键连按也能产生起音
 *     （原实现连按同一键时该音一直处于活跃状态，不会产生新起音，BPM 会掉到一半）。
 *  4. 和弦（各音相距 <35 ms）合并为一个起音事件，不再一个和弦算 3~4 个起音。
 *  5. 新 BPM 估计：一/二/三阶起音间隔在候选周期上做软高斯核打分（按倍数 k 以 1/√k 降权，
 *     不再"取得分平台最左端"而系统性偏快）→ 分段同相位网格合并回归精修周期 → 两次确认才跳变。
 *  6. 修复：原实现 `prevMag = mag` 只保存了对复用数组的引用，下一帧原地覆盖后"上一帧幅度"就等于当前帧，
 *     攻击比恒 ≤1 → 永远不会开音、不会产生起音，BPM 与当前按键始终为空（离线回放实测 0 个起音）。
 *     另修复 streak 与活跃音共用 miss 计数、静音时直接清空活跃音、陈旧攻击值误放行。
 */
class NoteDetector(private val sensitivity: Float = 0.7f, srVal: Int = 44100) {
    private val sr = srVal
    private val fftSize = 4096
    private val fftN = 16384
    private val hop = 1024
    private val ofN = 1024
    private val ofHop = 256
    private val grace = 7
    private val confirm = 4

    private val keyMidi = mapOf(
        "Q" to 72, "W" to 74, "E" to 76, "R" to 77, "T" to 79, "Y" to 81, "U" to 83,
        "A" to 60, "S" to 62, "D" to 64, "F" to 65, "G" to 67, "H" to 69, "J" to 71,
        "Z" to 48, "X" to 50, "C" to 52, "V" to 53, "B" to 55, "N" to 57, "M" to 59
    )
    private val midiKey = keyMidi.entries.associate { (k, v) -> v to k }
    private val validMidis = keyMidi.values.sorted()

    // ---------------- 音频缓冲与样本时钟
    private var buf = FloatArray(fftSize * 4)
    private var bufLen = 0
    private var bufPos = 0L                    // buf[0] 在整条音频流中的样本序号
    private var nIn = 0L                       // 已接收样本总数
    private var ofBuf = FloatArray(ofN * 8)
    private var ofLen = 2 * ofN                // 开头补 2048 个"虚拟静音"，首音也能形成起音峰
    private var ofPos = -2L * ofN

    // ---------------- 音高跟踪
    private class ActiveNote(var start: Double, var last: Double)

    private val active = mutableMapOf<Int, ActiveNote>()
    private val activeMiss = mutableMapOf<Int, Int>()   // 活跃音连续缺席帧数（与 streak 的 miss 分开）
    private val streak = mutableMapOf<Int, Int>()
    private val miss = mutableMapOf<Int, Int>()
    private val attack = mutableMapOf<Int, Float>()
    private val attackT = mutableMapOf<Int, Double>()
    private var prevMag: FloatArray? = null
    private var noiseFloor = 1e-7f
    private var recentPeak = 0f
    private var noiseSpec: FloatArray? = null

    // ---------------- 起音函数（环形缓冲）
    private val ring = 1024
    private val odfT = DoubleArray(ring)
    private val odfV = FloatArray(ring)
    private val odfE = FloatArray(ring)
    private var odfCount = 0L
    private var odfChecked = 0L
    private var odfMax = 0f
    private var ofPrev1: FloatArray? = null
    private var ofPrev2: FloatArray? = null
    private val ofPeaks = ArrayDeque<DoubleArray>()      // [t, 强度]
    private val pending = ArrayDeque<DoubleArray>()      // 待做"音高证据"确认的起音 [t, 强度]

    // ---------------- 每帧各音基频频点电平历史（dB）
    private val trackLo = 34
    private val trackHi = 98
    private val trackBins = IntArray(trackHi - trackLo + 1) {
        min(fftN / 2, (midiFreq(trackLo + it) * fftN / sr).roundToInt())
    }
    private val histN = 64
    private val histT = DoubleArray(histN)
    private val histL = Array(histN) { FloatArray(trackBins.size) }
    private var histCount = 0L

    // ---------------- 起音事件 / BPM
    private val onsets = ArrayList<DoubleArray>()          // [t, 强度]（和弦已合并）
    private var onsetsVer = 0
    private var bpmKey = -1
    private var bpmSmooth: Double? = null
    private var bpmPending: Double? = null

    var bpm: Float? = null
        private set
    var bpmConfidence: Float = 0f
        private set
    var tonality: String = "分析中…"
        private set
    var chord: String? = null
        private set
    val activeLabels: Set<String>
        get() = active.keys.filter { (activeMiss[it] ?: 0) == 0 }.mapNotNull { midiKey[it] }.toSet()

    // FFT 缓冲
    private val re = DoubleArray(fftN)
    private val im = DoubleArray(fftN)
    private val mag = FloatArray(fftN / 2 + 1)
    private val win = FloatArray(fftSize) { (0.5 * (1 - cos(2 * PI * it / (fftSize - 1)))).toFloat() }
    private val ofWin = FloatArray(ofN) { (0.5 * (1 - cos(2 * PI * it / (ofN - 1)))).toFloat() }
    private val ofRe = DoubleArray(ofN)
    private val ofIm = DoubleArray(ofN)
    private val ofLo = max(1, kotlin.math.ceil(60.0 * ofN / sr).toInt())
    private val ofHi = min(ofN / 2, kotlin.math.floor(8000.0 * ofN / sr).toInt())
    private val ofNB = ofHi - ofLo + 1

    private fun midiFreq(m: Int): Double = 440.0 * 2.0.pow((m - 69) / 12.0)
    private fun ri(k: Long): Int = (k % ring).toInt()

    /** 当前音频时钟（秒） */
    val now: Double get() = nIn.toDouble() / sr

    /** 已确认的起音事件时刻（秒，和弦已合并）——供调试/离线评测 */
    fun onsetTimes(): DoubleArray = DoubleArray(onsets.size) { onsets[it][0] }

    /** 输入任意长度的单声道样本（-1..1）。内部按 4096 窗 / 1024 帧移分帧，时间取样本时钟。 */
    fun feedSamples(x: FloatArray, n: Int = x.size) {
        nIn += n
        buf = append(buf, bufLen, x, n); bufLen += n
        ofBuf = append(ofBuf, ofLen, x, n); ofLen += n
        processOdf()
        while (bufLen >= fftSize) {
            val tC = (bufPos + fftSize / 2.0) / sr       // 帧中心时刻
            processFrame(tC)
            System.arraycopy(buf, hop, buf, 0, bufLen - hop)
            bufLen -= hop
            bufPos += hop
        }
        updateBpm(now)
    }

    private fun append(dst: FloatArray, len: Int, x: FloatArray, n: Int): FloatArray {
        val out = if (len + n > dst.size) dst.copyOf(max(dst.size * 2, len + n)) else dst
        System.arraycopy(x, 0, out, len, n)
        return out
    }

    // ------------------------------------------------------------------ 细分辨率起音函数
    private fun processOdf() {
        while (ofLen >= ofN) {
            for (i in 0 until ofN) {
                ofRe[i] = (ofBuf[i] * ofWin[i]).toDouble(); ofIm[i] = 0.0
            }
            fft(ofRe, ofIm)
            val l = FloatArray(ofNB)
            var pw = 0.0
            for (b in 0 until ofNB) {
                val k = ofLo + b
                val s2 = ofRe[k] * ofRe[k] + ofIm[k] * ofIm[k]
                pw += s2
                l[b] = ln(1.0 + 100.0 * sqrt(s2)).toFloat()
            }
            val lm = FloatArray(ofNB) { b ->
                max(l[b], max(if (b > 0) l[b - 1] else 0f, if (b < ofNB - 1) l[b + 1] else 0f))
            }
            var v = 0f
            val p2 = ofPrev2
            if (p2 != null) {
                for (b in 0 until ofNB) {
                    val d = l[b] - p2[b]
                    if (d > 0f) v += d
                }
            }
            ofPrev2 = ofPrev1
            ofPrev1 = lm
            val r = ri(odfCount)
            odfT[r] = (ofPos + ofN / 2.0) / sr
            odfV[r] = v
            odfE[r] = (10.0 * log10(pw + 1e-12)).toFloat()
            odfCount++
            System.arraycopy(ofBuf, ofHop, ofBuf, 0, ofLen - ofHop)
            ofLen -= ofHop
            ofPos += ofHop
        }
        pickPeaks()
    }

    private fun pickPeaks() {
        val w = 2
        val decay = 0.5.pow(ofHop.toDouble() / sr / 2.0).toFloat()   // 近期最大值半衰期 2 s
        while (odfChecked + w < odfCount) {
            val i = odfChecked
            odfChecked++
            val vi = odfV[ri(i)]
            odfMax = max(vi, odfMax * decay)
            if (i < w || vi <= 0f) continue
            var isMax = true
            for (k in i - w..i + w) if (odfV[ri(k)] > vi) { isMax = false; break }
            if (!isMax) continue
            val lo = max(0L, i - 64)
            val cnt = (i - lo).toInt()
            val med = if (cnt > 0) FloatArray(cnt) { odfV[ri(lo + it)] }.also { it.sort() }[cnt / 2] else 0f
            val thr = 1.4f * med + max(8f, 0.08f * odfMax)
            if (vi < thr) continue
            // 硬截止"咔哒"：其后总功率下降，不是起音
            val net = (odfE[ri(i + 1)] + odfE[ri(i + 2)]) - (odfE[ri(i - 2)] + odfE[ri(i - 1)])
            if (net <= 0f) continue
            val a = odfV[ri(i - 1)]
            val c = odfV[ri(i + 1)]
            val den = a - 2f * vi + c
            val d = (if (den < -1e-12f) 0.5f * (a - c) / den else 0f).coerceIn(-0.5f, 0.5f)
            val t = odfT[ri(i)] + d * ofHop / sr
            val last = ofPeaks.lastOrNull()
            if (last != null && t - last[0] < 0.025) {
                if (vi > last[1]) {
                    val pl = pending.lastOrNull()
                    if (pl != null && pl[0] == last[0]) { pl[0] = t; pl[1] = vi.toDouble() }
                    last[0] = t; last[1] = vi.toDouble()
                }
                continue
            }
            ofPeaks.addLast(doubleArrayOf(t, vi.toDouble()))
            if (ofPeaks.size > 160) ofPeaks.removeFirst()
            pending.addLast(doubleArrayOf(t, vi.toDouble()))
        }
    }

    // ------------------------------------------------------------------ 音高帧
    private fun processFrame(tC: Double) {
        for (i in 0 until fftN) {
            re[i] = if (i < fftSize) (buf[i] * win[i]).toDouble() else 0.0
            im[i] = 0.0
        }
        fft(re, im)
        for (i in 0..fftN / 2) mag[i] = sqrt(re[i] * re[i] + im[i] * im[i]).toFloat()
        val hr = (histCount % histN).toInt()
        histT[hr] = tC
        for (j in trackBins.indices) histL[hr][j] = (20.0 * log10(mag[trackBins[j]] + 1e-12)).toFloat()
        histCount++

        val peak = mag.maxOrNull() ?: 0f
        if (noiseSpec == null) noiseSpec = mag.copyOf()
        val noise = noiseSpec!!
        for (i in noise.indices) noise[i] = (0.997 * noise[i] + 0.003 * mag[i]).toFloat()
        val magClean = FloatArray(mag.size) { i -> maxOf(mag[i] - noise[i], 0.1f * mag[i]) }

        if (peak > 1e-9) {
            val sorted = mag.copyOf().also { it.sort() }
            noiseFloor = 0.92f * noiseFloor + 0.08f * maxOf(sorted[sorted.size / 2] * 4f, 1e-7f)
        }
        recentPeak = maxOf(peak, (recentPeak * exp(-hop.toDouble() / sr * 1.2)).toFloat())
        val gate = maxOf(noiseFloor * 4f, 1.5e-4f, 0.06f * recentPeak)

        if (peak < gate) {
            // 静音：候选与活跃音都按缺席处理（原实现直接清空活跃音，且不更新上一帧谱）
            for (m in streak.keys.toList()) bumpMiss(m)
            for (m in active.keys.toList()) bumpActiveMiss(m)
            prevMag = mag.copyOf()
            evalPending(tC)
            return
        }

        val relThr = 0.16f - 0.13f * sensitivity
        val absThr = maxOf(noiseFloor * 2f, peak * relThr)
        val peaks = findPeaks(magClean, absThr)
        if (peaks.isNotEmpty()) {
            val topAmp = peaks[0].second
            peaks.retainAll { it.second >= 0.12f * topAmp }
        }
        val midis = peaks.map { (bin, _) ->
            val freq = bin * sr / fftN
            (69 + 12 * log2(freq / 440.0)).roundToInt()
        }.filter { it in 47..84 }.toSet()
        val midisNew = midis.filter { hasHarmonicSupport(it, magClean) }

        val prev = prevMag
        for (m in midisNew) {
            val amp = ampOf(m, magClean)
            val prevAmp = prev?.let { it[binOf(m)] } ?: 0f
            val ratio = amp / maxOf(prevAmp, 1e-9f)
            // 只认 0.35 s 内的攻击记录：旧的大比值会永久压住后来的真实骤起
            if (ratio > (attack[m] ?: 0f) || tC - (attackT[m] ?: -1e9) > 0.35) {
                attack[m] = ratio; attackT[m] = tC
            }
        }
        prevMag = mag.copyOf()

        for (m in streak.keys.toList()) if (m !in midis) bumpMiss(m)
        for (m in midis) { miss[m] = 0; streak[m] = (streak[m] ?: 0) + 1 }
        val current = streak.filter { it.value >= confirm }.keys

        val attackMin = maxOf(1.3f, 2.2f - sensitivity)
        for (m in current) {
            val a = active[m]
            if (a == null) {
                var near = 0f
                for (mm in m - 1..m + 1) {
                    if (tC - (attackT[mm] ?: -1e9) <= 0.35) near = maxOf(near, attack[mm] ?: 0f)
                }
                if (near >= attackMin) { active[m] = ActiveNote(tC, tC); activeMiss[m] = 0 }
            } else {
                a.last = tC
                activeMiss[m] = 0
            }
        }
        for (m in active.keys.toList()) if (m !in current) bumpActiveMiss(m)
        evalPending(tC)
    }

    private fun bumpMiss(m: Int) {
        miss[m] = (miss[m] ?: 0) + 1
        if ((miss[m] ?: 0) >= 2) { streak[m] = 0; attack.remove(m); attackT.remove(m) }
    }

    private fun bumpActiveMiss(m: Int) {
        val k = (activeMiss[m] ?: 0) + 1
        activeMiss[m] = k
        if (k >= grace) { active.remove(m); activeMiss.remove(m) }
    }

    /** 起音峰 + 音高证据：起音前后整窗比较，某个琴键频点上升 ≥2 dB 且不是很弱的分量 → 起音事件 */
    private fun evalPending(tC: Double) {
        while (pending.isNotEmpty() && pending.first()[0] <= tC - 0.10) {
            val p = pending.removeFirst()
            val t = p[0]
            var rb = -1; var ra = -1
            var tb = -1e18; var ta = 1e18
            val kMin = max(0L, histCount - histN)
            for (k in kMin until histCount) {
                val r = (k % histN).toInt()
                val tt = histT[r]
                if (tt <= t - 0.043 && tt > tb) { tb = tt; rb = r }
                if (tt >= t + 0.043 && tt < ta) { ta = tt; ra = r }
            }
            if (rb < 0 || ra < 0) continue
            val lb = histL[rb]
            val la = histL[ra]
            var topA = -999f
            for (m in validMidis) topA = maxOf(topA, la[m - trackLo])
            var ok = false
            for (m in validMidis) {
                val j = m - trackLo
                if (la[j] - lb[j] >= 2f && la[j] >= topA - 20f) { ok = true; break }
            }
            if (ok) addOnset(t, p[1])
        }
    }

    private fun addOnset(t: Double, s: Double) {
        for (i in onsets.size - 1 downTo max(0, onsets.size - 12)) {
            val e = onsets[i]
            if (abs(e[0] - t) < 0.035) {
                e[0] = min(e[0], t); e[1] = max(e[1], s); onsetsVer++
                return
            }
        }
        var i = onsets.size
        while (i > 0 && onsets[i - 1][0] > t) i--
        onsets.add(i, doubleArrayOf(t, s))
        if (onsets.size > 2000) onsets.subList(0, 1000).clear()
        onsetsVer++
    }

    // ------------------------------------------------------------------ BPM
    private fun updateBpm(nowT: Double) {
        val window = 12.0
        val ev = onsets.filter { it[0] > nowT - window }
        val key = onsetsVer * 31 + (ev.firstOrNull()?.get(0)?.times(1000)?.toInt() ?: 0)
        if (key == bpmKey) return
        bpmKey = key
        if (ev.size < 5) { bpm = null; return }
        val times = DoubleArray(ev.size) { ev[it][0] }
        val w = DoubleArray(ev.size) { exp(-(nowT - times[it]) / (0.4 * window)) }
        val est = estimateIoiPeriod(times, w) ?: return
        bpmConfidence = est.second.toFloat()
        if (est.second < 0.35) return
        val nb = 60.0 / est.first
        val s = bpmSmooth
        val ps = bpmPending
        bpmSmooth = when {
            s == null -> nb
            abs(nb - s) / s <= 0.03 -> { bpmPending = null; 0.5 * s + 0.5 * nb }
            ps != null && abs(nb - ps) / ps <= 0.03 -> { bpmPending = null; nb }  // 连续两次相同：确认变速
            else -> { bpmPending = nb; s }                                     // 单次离群：暂不采纳
        }
        bpm = (round(bpmSmooth!! * 10.0) / 10.0).toFloat()
    }

    /** 起音时间 → (起音周期秒, 置信度)。算法与 detection.py 的 estimate_ioi_period 一致。 */
    private fun estimateIoiPeriod(t: DoubleArray, w0: DoubleArray): Pair<Double, Double>? {
        val n = t.size
        if (n < 4) return null
        val pMin = 0.20
        val pMax = 1.60
        if (t[n - 1] - t[0] <= 2 * pMin) return null
        val d = ArrayList<Double>()
        val wd = ArrayList<Double>()
        for ((lag, lw) in listOf(1 to 1.0, 2 to 0.5, 3 to 0.25)) {
            for (i in 0 until n - lag) {
                val dd = t[i + lag] - t[i]
                if (dd >= 0.6 * pMin && dd <= 4.5 * pMax) { d.add(dd); wd.add(lw * sqrt(w0[i + lag] * w0[i])) }
            }
        }
        if (d.size < 3) return null
        var bestP = pMin
        var bestS = -1.0
        var lp = ln(pMin)
        while (lp <= ln(pMax) + 1e-12) {
            val p = exp(lp)
            val sigBase = max(0.012, 0.035 * p)
            var s = 0.0
            for (q in d.indices) {
                val k = Math.rint(d[q] / p)
                if (k < 1.0 || k > 4.0) continue
                val res = d[q] - k * p
                val sig = sigBase * sqrt(k)
                s += wd[q] * exp(-0.5 * (res / sig) * (res / sig)) / sqrt(k)
            }
            val prior = exp(-0.5 * (log2((60.0 / p) / 120.0) / 1.5).pow(2))
            s *= 0.92 + 0.08 * prior
            if (s > bestS) { bestS = s; bestP = p }
            lp += 0.002
        }
        // 分段同相位网格精修
        val p0 = bestP
        val ok = BooleanArray(n - 1)
        val k1 = DoubleArray(n - 1)
        for (i in 0 until n - 1) {
            val d1 = t[i + 1] - t[i]
            val k = Math.rint(d1 / p0)
            k1[i] = k
            val tol = max(0.025, 0.08 * p0) * sqrt(max(k, 1.0))
            ok[i] = k >= 1.0 && k <= 4.0 && abs(d1 - k * p0) <= tol
        }
        val pos = DoubleArray(n)
        val run = IntArray(n)
        var r = 0
        for (i in 1 until n) {
            if (ok[i - 1]) pos[i] = pos[i - 1] + k1[i - 1] else r++
            run[i] = r
        }
        val w = w0.copyOf()
        var period = p0
        for (iter in 0 until 2) {
            var num = 0.0
            var den = 0.0
            for (rr in 0..r) {
                var sw = 0.0; var st = 0.0; var sp = 0.0; var cnt = 0
                for (i in 0 until n) if (run[i] == rr) { sw += w[i]; st += w[i] * t[i]; sp += w[i] * pos[i]; cnt++ }
                if (cnt < 2) continue
                val tm = st / sw
                val pm = sp / sw
                for (i in 0 until n) if (run[i] == rr) {
                    num += w[i] * (pos[i] - pm) * (t[i] - tm); den += w[i] * (pos[i] - pm) * (pos[i] - pm)
                }
            }
            if (den <= 1e-9) break
            val cand = num / den
            if (cand < 0.97 * p0 || cand > 1.03 * p0) break
            period = cand
            // 剔除离群起音（段内网格残差过大）后再拟合一次
            val res = DoubleArray(n)
            for (rr in 0..r) {
                var sw = 0.0; var sa = 0.0; var cnt = 0
                for (i in 0 until n) if (run[i] == rr) { sw += w[i]; sa += w[i] * (t[i] - period * pos[i]); cnt++ }
                if (cnt < 2) continue
                val a = sa / sw
                for (i in 0 until n) if (run[i] == rr) res[i] = t[i] - (a + period * pos[i])
            }
            val nz = res.filter { it != 0.0 }.map { abs(it) }.sorted()
            val mad = if (nz.isNotEmpty()) nz[nz.size / 2] else 0.0
            val lim = max(0.015, 4.5 * mad)
            var anyBad = false
            for (i in 0 until n) if (abs(res[i]) > lim) { w[i] *= 1e-3; anyBad = true }
            if (!anyBad) break
        }
        var sw1 = 0.0
        var swOk = 0.0
        for (i in 0 until n - 1) {
            val ww = sqrt(w[i + 1] * w[i])
            sw1 += ww
            if (ok[i]) swOk += ww
        }
        return Pair(period, swOk / max(sw1, 1e-9))
    }

    // ------------------------------------------------------------------ 频谱工具
    private fun findPeaks(mag: FloatArray, thr: Float): MutableList<Pair<Float, Float>> {
        val out = mutableListOf<Pair<Float, Float>>()
        for (i in 3 until mag.size - 3) {
            if (mag[i] > thr && mag[i] >= mag[i - 1] && mag[i] >= mag[i + 1]) {
                out.add(i.toFloat() to mag[i])
            }
        }
        out.sortByDescending { it.second }
        return out
    }

    private fun hasHarmonicSupport(midi: Int, mag: FloatArray): Boolean {
        val freq = midiFreq(midi)
        if (freq > 450) return true
        val base = (freq * fftN / sr).toInt()
        if (base !in mag.indices) return false
        var baseAmp = 0f
        for (i in maxOf(0, base - 2)..minOf(mag.size - 1, base + 3)) {
            if (mag[i] > baseAmp) baseAmp = mag[i]
        }
        baseAmp = maxOf(baseAmp, 1e-9f)
        for (k in 2..4) {
            val t = base * k
            if (t >= mag.size) break
            var maxV = 0f
            for (i in maxOf(0, t - 3)..minOf(mag.size - 1, t + 4)) {
                if (mag[i] > maxV) maxV = mag[i]
            }
            if (maxV > 0.03f * baseAmp) return true
        }
        return false
    }

    private fun binOf(midi: Int): Int {
        val i = (midiFreq(midi) * fftN / sr).toInt()
        return if (i in 0 until fftN / 2) i else 0
    }

    private fun ampOf(midi: Int, mag: FloatArray): Float {
        val i = binOf(midi)
        return if (i in mag.indices) mag[i] else 0f
    }

    private fun fft(re: DoubleArray, im: DoubleArray) {
        val n = re.size
        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) { j = j xor bit; bit = bit shr 1 }
            j = j xor bit
            if (i < j) {
                val tr = re[i]; re[i] = re[j]; re[j] = tr
                val ti = im[i]; im[i] = im[j]; im[j] = ti
            }
        }
        var len = 2
        while (len <= n) {
            val ang = -2.0 * PI / len
            val wr = cos(ang); val wi = sin(ang)
            for (i in 0 until n step len) {
                var cr = 1.0; var ci = 0.0
                for (k in 0 until len / 2) {
                    val ur = re[i + k]; val ui = im[i + k]
                    val vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci
                    val vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr
                    re[i + k] = ur + vr; im[i + k] = ui + vi
                    re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi
                    val ncr = cr * wr - ci * wi
                    ci = cr * wi + ci * wr; cr = ncr
                }
            }
            len *= 2
        }
    }
}
