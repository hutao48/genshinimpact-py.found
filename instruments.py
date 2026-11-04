# -*- coding: utf-8 -*-
"""
原神乐器定义：键位 → MIDI 音高 / 和弦
已按游戏内实际布局核实：
  21 键琴（风物之诗琴/镜花之琴/跃律琴/谐律键琴）：三排 Q-U / A-J / Z-M，白键（无半音），
    默认音域 C3~B5（低音行 C3-B3、中音行 C4-B4、高音行 C5-B5）。
  晚风圆号：两排 Q-U / A-J，默认音域 C4~B5（低音行 C4-B4、高音行 C5-B5）。
  悠可琴：三排。Q-U 为 7 个和弦键（C Dm Em F G Am G7），A-J 高音行 C5-B5，Z-M 低音行 C4-B4。
移调 transpose 以半音为单位整体平移（用于校准音高基准）。
"""

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SOLFEGE = {0: "do", 2: "re", 4: "mi", 5: "fa", 7: "so", 9: "la", 11: "ti"}


def midi_to_name(midi: int) -> str:
    """MIDI 号 → 音名（科学音高记号，C4 = 中央C = 60）"""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_solfege(midi: int) -> str:
    return SOLFEGE.get(midi % 12, "")


class Instrument:
    """乐器：keys 为 [(键位标签, MIDI音高|None, 类型, 附加名), ...]
    类型: 'pitch' 普通音键；'chord' 和弦键（MIDI 为 None，附加名为和弦名）
    """

    def __init__(self, name: str, keys, transpose: int = 0, note: str = ""):
        self.name = name
        self.keys = list(keys)
        self.transpose = transpose
        self.note = note  # 布局说明文字

    # ---- 派生数据 ----
    def pitch_keys(self):
        """[(label, midi, kind, extra)] 仅普通音键"""
        return [k for k in self.keys if k[2] == "pitch"]

    def chord_keys(self):
        return [k for k in self.keys if k[2] == "chord"]

    def valid_midis(self):
        """有效音高集合（含移调）"""
        return sorted({k[1] + self.transpose for k in self.keys if k[2] == "pitch"})

    def min_midi(self):
        v = self.valid_midis()
        return v[0] if v else 0

    def max_midi(self):
        v = self.valid_midis()
        return v[-1] if v else 127

    def label_of(self, midi):
        """将检测到的 MIDI 音高映射回键位标签；越界/半音会就近吸附并标记近似"""
        trans_midi = midi - self.transpose
        for k in self.pitch_keys():
            if k[1] == trans_midi:
                return k[0], False
        # 就近吸附
        best = min(self.pitch_keys(), key=lambda k: abs(k[1] - trans_midi))
        return best[0], abs(best[1] - trans_midi) > 0

    def contains_midi(self, midi):
        return midi in self.valid_midis()

    # ---- 悠可琴和弦键匹配 ----
    def match_chord_key(self, pitch_classes):
        """若当前音级集合包含某和弦键的和弦音 → 返回 (键位, 和弦名)"""
        if self.name != "悠可琴":
            return None
        chord_tone_map = {
            "C": {0, 4, 7}, "Dm": {2, 5, 9}, "Em": {4, 7, 11},
            "F": {5, 9, 0}, "G": {7, 11, 2}, "Am": {9, 0, 4}, "G7": {7, 11, 2, 5},
        }
        for k in self.chord_keys():
            label, _, _, cname = k
            tones = chord_tone_map[cname]
            if tones <= set(pitch_classes):
                return label, cname
        return None


# ---------------------------------------------------------------------------
# 布局构建
# ---------------------------------------------------------------------------

DIATONIC_OFFSETS = [0, 2, 4, 5, 7, 9, 11]  # 白键 C D E F G A B 的半音偏移


def _diatonic_row(labels: str, base_octave: int):
    """一行 7 个白键：base_octave 表示该行 C 音的八度（C4=4 → MIDI 60）。
    键位里存的是未移调的音高；移调只记在 Instrument.transpose 上（valid_midis / label_of 统一加减），
    以前这里也加了一次移调，界面上移调 +12 时检测实际移了 +24"""
    out = []
    for i, ch in enumerate(labels):
        midi = 60 + (base_octave - 4) * 12 + DIATONIC_OFFSETS[i]
        out.append((ch, midi, "pitch", ""))
    return out


def build_lyre21(name: str, high=5, mid=4, low=3, transpose=0, note=""):
    keys = _diatonic_row("QWERTYU", high)
    keys += _diatonic_row("ASDFGHJ", mid)
    keys += _diatonic_row("ZXCVBNM", low)
    return Instrument(name, keys, transpose=transpose, note=note)


def build_horn(transpose=0):
    """晚风圆号：两排 Q-U（高） + A-J（低），14 键，按 C4~B5 识别。
    注：与游戏录像逐一对照，圆号最低的显著分音其实在这个音高下方一个八度、而 2~4 次谐波比它还强；
    按 C3~B4 识别时检测器多半找到的是更强的谐波、键反而认错（召回 21%，按 C4~B5 是 32%），所以仍按 C4~B5"""
    keys = _diatonic_row("QWERTYU", 5)
    keys += _diatonic_row("ASDFGHJ", 4)
    return Instrument("晚风圆号", keys, transpose=transpose,
                      note="两排 14 键（游戏界面为两排七音按钮）")


def build_youko(transpose=0):
    """悠可琴：7 和弦键 Q-U + 高音行 A-J + 低音行 Z-M"""
    keys = [
        ("Q", None, "chord", "C"),
        ("W", None, "chord", "Dm"),
        ("E", None, "chord", "Em"),
        ("R", None, "chord", "F"),
        ("T", None, "chord", "G"),
        ("Y", None, "chord", "Am"),
        ("U", None, "chord", "G7"),
    ]
    keys += _diatonic_row("ASDFGHJ", 5)
    keys += _diatonic_row("ZXCVBNM", 4)
    return Instrument("悠可琴", keys, transpose=transpose,
                      note="7 和弦键（Q C / W Dm / E Em / R F / T G / Y Am / U G7）+ 两排音高键")


def all_instruments():
    """全部可选乐器（默认音域基准，可在界面中移调 ±12）"""
    return [
        build_lyre21("风物之诗琴", high=5, mid=4, low=3,
                     note="三排 21 键，白键无半音，音域 C3~B5"),
        build_lyre21("镜花之琴", high=5, mid=4, low=3,
                     note="三排 21 键，白键无半音，音域 C3~B5"),
        build_lyre21("跃律琴", high=5, mid=4, low=3,
                     note="三排 21 键，白键无半音，音域 C3~B5"),
        build_lyre21("谐律键琴", high=5, mid=4, low=3,
                     note="三排 21 键，白键无半音，音域 C3~B5"),
        build_horn(),
        build_youko(),
    ]


# 和弦模板（用于从当前音高集合推断和弦名）
CHORD_TEMPLATES = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "5": (0, 7),
    "maj7": (0, 4, 7, 11),
    "7": (0, 4, 7, 10),
    "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
}
