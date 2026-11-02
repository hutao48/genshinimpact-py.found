# Genshin Instrument Performance Detector

**Version**: Windows 1.0.3 / Android 1.0.2 | Download: [GitHub Releases](https://github.com/hutao48/genshinimpact-py.found/releases/latest) | [Chinese user guide (中文使用说明)](使用说明.md)

| Download | Description |
|---|---|
| `GenshinInstrumentDetector-1.0.3-win64-setup.exe` | Windows installer (installs into the current user's folder, no administrator rights required; creates Start Menu/desktop shortcuts and an uninstaller) |
| `GenshinInstrumentDetector-1.0.3-win64-portable.exe` | Windows portable single-file build; just double-click to run |
| `GenshinInstrumentDetector-1.0.2-android.apk` | Android package (package-installation verification may need to be disabled; every build is signed with a different key, so uninstall the old version before upgrading) |

**Release notes**:
- Windows 1.0.3: Fixed quiet background sound after a pause being mistaken for a new keypress. The threshold for new keys is now learned from confirmed onsets and held during pauses. The keyboard display now shows the current state of the last audio frame, so keys whose notes already ended inside a batch are no longer highlighted. After lowering the playback volume a lot, stop and restart monitoring to re-learn the level.
- 1.0.2: Added **boundary check** (more than 10 keys pressed at once, or a very long run of perfectly even note gaps, as evidence for judging whether a script is being used); BPM now follows tempo changes — it catches up about 1–1.5 s after a change (the old version could sit still for a dozen seconds when the tempo changed often), and rapid consecutive notes no longer get stuck below 300. The UI became a dark card layout; the BPM chart auto-scales its vertical axis, supports switching the displayed range, and shows a readout on hover; records are kept longer (BPM for 4 hours, duration table up to 20,000 rows) and can be exported to CSV.
- 1.0.1: With game background noise, sound effects and background music present, key durations are no longer frequently cut off, split into fragments, or falsely reported as "key release/cutoff".
- 1.0.0: Rewrote BPM and per-note duration detection (onsets aligned to the actual strike, repeated presses of the same key split individually, end reason labeled, BPM estimated from merged chords); added a Windows installer and offline analysis (`--analyze recording.wav`).

---

## 1. What It Is

A real-time detection tool that listens to your computer's speaker output or a phone microphone input and recognizes the 6 playable instruments in *Genshin Impact*:

| Instrument | Keys | Notes |
|---|---|---|
| Windsong Lyre | 21 keys | Three rows of white keys, C3–B5 |
| Floral Zither | 21 keys | Same layout as the Windsong Lyre |
| Vintage Lyre | 21 keys | Same layout as the Windsong Lyre |
| Harmonic Keys | 21 keys | Same layout as the Windsong Lyre |
| Nightwind Horn | 14 keys | Two rows of white keys, C4–B5 |
| Ukulele | 12 pitches + 7 chord keys | Q–U chord keys + A–J high row + Z–M low row |

For every performance, the app shows:

1. **The keys currently held** (including chords such as C, Dm, Em, F, G, Am and G7) — the on-screen keyboard highlights them in real time.
2. **The current key** (e.g., C major or A minor, with a confidence value).
3. **The exact duration of every note** (millisecond precision; the table keeps up to 20,000 rows, newest first, with start time, key, note name, solfège, duration, gap and end reason).
4. **The current BPM**, plus a **bar chart of how BPM changes over time** (one point every 0.5 s, up to 4 hours; switch between the last 30 s / 1 min / 5 min / all, with the vertical axis auto-scaled to the visible data, bar colors running from cyan to red as the tempo goes from slow to fast, and a tooltip showing the reading at any moment).

---

## 2. Quick Start

1. Run `GenshinInstrumentDetector-1.0.3-win64-setup.exe` and launch the app from the Start Menu/desktop, or double-click the portable exe (the first launch takes about 2–5 s because the single-file build extracts itself).
2. Choose an **instrument** at the top (Windsong Lyre by default).
3. The **capture device** is already set to "Speaker output · loopback" — it listens to everything played through the speakers, so in-game performances are captured automatically, **with no extra configuration**.
4. Click **▶ Start listening**, then play in the game.
5. While you play, key highlights, pressed keys/chords, key and BPM refresh in real time, the BPM bar chart scrolls, and the table below logs each note's duration. Drag the separators between the keyboard/metrics, BPM chart and duration table to resize them; the layout adapts when the window is resized. Stopping and starting again (or switching instruments) keeps appending to the existing records instead of clearing them; **Export** saves the duration table and BPM history as CSV.

> If detection feels insensitive or reports too many false positives, adjust the **Sensitivity** slider (40%–70% is a good range). Higher values are more sensitive and also pick up more background sound.

---

## 3. Instrument Key Layouts

### 21-key instruments (Windsong Lyre / Floral Zither / Vintage Lyre / Harmonic Keys)

Three rows of white keys covering the C major scale:

| Row | Keys | Range |
|---|---|---|
| Top | Q W E R T Y U | C5 – B5 |
| Middle | A S D F G H J | C4 – B4 |
| Bottom | Z X C V B N M | C3 – B3 |

### Nightwind Horn (14 keys)

| Row | Keys | Range |
|---|---|---|
| Top | Q W E R T Y U | C5 – B5 |
| Bottom | A S D F G H J | C4 – B4 |

### Ukulele (12 pitches + 7 chord keys)

| Row | Keys | Notes |
|---|---|---|
| Chord row | Q=C　W=Dm　E=Em　R=F　T=G　Y=Am　U=G7 | Pressing one key plays a full chord |
| High row | A S D F G H J | C5 – B5 |
| Low row | Z X C V B N M | C4 – B4 |

---

## 4. Listening to Speaker Output (and Other Devices)

- **Default mode — speaker output · loopback**: The app uses Windows WASAPI loopback capture to record **everything any application plays through the speakers**. In-game performances and any audio played on this machine are recognized directly. This is the recommended, zero-configuration mode.
- **Alternative mode — microphone**: Every entry marked "(Microphone)" in the device drop-down can be selected. The app then captures from a microphone or line input, which lets you listen to sound played by **another computer or an external device**:
  - Connect the audio output of another device (phone, second computer, Switch/PlayStation, etc.) to this computer's **line-in or microphone input** with an audio cable;
  - Or enable **Stereo Mix** in Windows sound settings and use it as the input source.
- The device drop-down lists every available capture device. Click **Refresh** to enumerate them again; all sound cards and capture devices connected to the computer are listed.

---

## 5. Interface Guide

| Area | Contents |
|---|---|
| Keyboard | Currently sounding keys are highlighted (gold = pitch key, green = chord key); key size adapts to the window |
| Live metrics | Current key (note name), detected chord, current key/tonality and current BPM (the small text below shows the lowest–highest BPM in the visible chart range) |
| BPM history | Bar chart with time (min:s) on the x-axis and BPM on the y-axis (auto-scaled to the visible data); one point every 0.5 s, kept for up to 4 hours; use the top-right control to switch the range (30 s / 1 min / 5 min / all); the header shows the current/average/minimum/maximum values in that range; the dashed line marks the current reading, and hovering shows the reading at that moment |
| Note durations | Table: start time (min:s.ms) / key / note name / solfège / duration (ms) / gap (ms) / end reason, newest first, up to 20,000 rows (see "How durations and BPM are defined" below) |
| Transpose | Pitch-reference calibration in semitones (−12 to +12); shift everything if detected pitches do not match the real ones |
| Clear | Clears the table, BPM history and live readouts |
| Export | Exports the duration table, BPM history and boundary-check results as CSV files (open directly in Excel): `演奏记录_日期_时间.csv` plus matching `_BPM.csv` and `_排查.csv` files |
| Boundary check | The second tab next to the duration table (also reachable by clicking the "Check" status in the top bar): lists operations that exceed human limits; see "Boundary check" below |

**How durations and BPM are defined**

- **Start time**: aligned to the actual strike (fine-resolution onset function, error about ±5 ms); the timeline is the audio time since monitoring started.
- **Duration**: from onset to the end of the note. The **end reason** column explains how it ended:
  - `Key release / cutoff`: the sound was cut off abruptly (key released, horn key released, or truncated); duration = key hold time (release tail subtracted);
  - `Same-key re-press`: the same key was pressed again; duration = time until the next press (repeated presses of one key are split individually);
  - `Natural decay`: on plucked instruments the sound keeps decaying after the key is released, and **the release moment cannot be observed in the audio**; this value is the audible decay length, not the key hold time.
- **Gap**: time since the previous onset (a chord counts as one onset). With script-style "press → hold → release → next" playing, the gap is approximately the key hold time plus a fixed overhead.
- **BPM**: 60 / onset period (the most common regular onset interval unit). A melody made entirely of eighth notes therefore reports the eighth-note rate. The reading follows the current tempo: about 1–1.5 s after a tempo change. If the notes merely become denser or sparser (the new tempo is exactly 2, 3 or 4 times the old one, or a fraction of it), it takes about 1 s (denser) / 3 s (sparser) before switching, to avoid the reading flipping back and forth. A continuous rapid run (each note < 0.2 s) can read above 300.

**Boundary check (evidence for judging whether an auto-play script is being used)**

This only reports evidence; it does not draw conclusions. There are two levels: "Beyond human limits" = a human cannot do it; "Suspected mechanical input" = a human would find it extremely difficult and other evidence is needed.

- **More than 10 keys pressed at the same time** (a human has only 10 fingers): notes whose onsets are within 45 ms of each other count as one press; the spectra before and after that press are compared, and the number of new spectral peaks at each key's fundamental is counted. Peaks that can be explained as harmonics of a lower key, obvious "ghost notes" much weaker than neighboring keys, and notes that only start after the press are not counted; harmonic levels are learned automatically from notes played alone in the recording. The count error is about ±1 key (larger when other notes follow immediately), so "Beyond human limits" is reported only at ≥ 12; 11 is reported as "Suspected". Note that one finger can press two adjacent keys on a computer keyboard, so this is strong evidence, not conclusive proof. The Ukulele has chord keys (one key sounds several notes) and is excluded from this check; the horn has strong harmonics and tends to undercount.
- **A very long run of notes with perfectly even gaps** (machine-level precision): Genshin emits audio in blocks of about 21 ms (1024 samples), so key times snap to block boundaries and human timing errors of a dozen milliseconds are invisible in the recording — **even a short trill played by a human looks "perfectly even"**. Therefore only long runs are reported: N consecutive onsets that all match a perfectly even timeline within one audio block, with N calibrated by tempo (for example, 52 notes at about 300 ms per note, 66 at about 120 ms; longer when the tempo is close to an integer multiple of the audio block, and some tempos are not judged at all). The calibration uses a human timing model that simulates a very steady player performing a 240-note run; the false-positive probability is < 0.5%. If the game reads keys per frame, a script is also disturbed by frames, so this check can miss it (but it will not falsely accuse).
- Measured results (`python eval_screening.py`): among 240 presses of chords with ≤ 10 keys, 0 were reported as "Beyond human limits" and 2 as "Suspected" (when a melody followed immediately, 9- and 10-key chords were each estimated at 11 once); 22 of 24 12-key lyre chords were reported (20 as "Beyond human limits"), and 21 of 24 14-key chords; the horn undercounts, and a 14-key chord was reported only as "Suspected"; script-style long runs were reported in 30 of 32 cases, while 64 simulated human long runs produced 0 false positives; 7 real recordings (including one hand-played recording with frequent tempo changes) produced 0 findings.

---

## 6. FAQ

| Symptom | What to do |
|---|---|
| No capture device found | Check that the speaker/microphone drivers work; click **Refresh**; allow apps to access the microphone in Windows sound settings (if using microphone mode) |
| No notes detected | Raise the sensitivity; make sure the volume is not muted; turn up the in-game performance volume |
| False positives / constant jumping | Lower the sensitivity; close software that plays music in the background; check whether other sounds are playing |
| Pitches are consistently wrong (an octave too high/low) | Use **Transpose** to shift within ±12 semitones |
| Antivirus warning | PyInstaller single-file builds are sometimes flagged by antivirus software; add an exception. The app does not access the network or write to the registry |
| The app misbehaves | Log file: `%LOCALAPPDATA%\GenshinInstrumentDetector\app.log`; check it when troubleshooting |

**Diagnostic mode**: Set the environment variable `GID_DEBUG=1` before running the EXE; device opening and runtime status are then written to the log for remote troubleshooting.

**Offline analysis of a recording**: `原神乐器演奏检测器.exe --analyze recording.wav [result.txt] [instrument name]`. The result is written by default next to the recording as "<recording name>_分析.txt" (start time, key, duration, gap and end reason for every note, plus BPM, key, boundary-check results and a per-second BPM reading). To extract the audio from someone else's performance video, use ffmpeg first: `ffmpeg -i video.mp4 -vn -ac 1 -ar 48000 recording.wav`.

---

## 7. Technical Notes (Brief)

- **Capture**: WASAPI loopback/microphone dual mode, 48 kHz, 2048 samples per block; **all timestamps use the audio sample clock** (real-time and offline results agree, unaffected by read jitter).
- **Detection**: FFT (4096 + 16384 zero-padding) extracts fundamentals and harmonic structure, tracked key by key; an attack threshold plus harmonic-structure validation rejects background noise; four consecutive frames are required for confirmation.
- **Onset**: log-spectral flux with a 1024-sample window / 256-sample hop (SuperFlux-style) locates the strike; a new note must correspond to an onset peak; hard-cutoff "clicks" (total power drops afterwards) are not onsets; "onset side lobes" that appear together with a stronger note, are more than 6 dB weaker and disappear within 0.25 s are removed.
- **Duration**: the end is located from the note's own level envelope — a rapid cutoff uses the −6 dB half-amplitude point and subtracts a release tail looked up from the cutoff steepness; a same-key re-press (the whole-window level around the onset returns to the "just pressed" level) ends at the new onset; otherwise the note is considered to decay naturally.
- **Noise robustness for durations (1.0.1)**: ambient noise, short sound effects and background music in the game no longer easily cut durations or split them into fragments —
  - starting a new note and detecting a same-key re-press both require the note's own bins to rise and persist like a real keypress (short sound effects fall back within 130 ms; a still-ringing note does not rise; broadband noise raises all bins equally, so the note is not prominent);
  - when the second harmonic is used as evidence of a re-press, the fundamental must move in the same direction (a weak harmonic can "rise" on a little noise); a re-press uses the key's previous "just pressed" level as its reference (Genshin instruments have no velocity, which prevents the reference from drifting upward after a false positive);
  - a note that is already sounding is sustained only by peaks at its exact pitch (semitones in background music cannot keep it alive);
  - when judging "key release/cutoff": the trend line is fitted only from frames after the level peaks; dips caused by interference beating that recover within 0.35 s do not count; when the level fluctuates a lot (beating with neighboring keys/background music), a deeper drop is required; when the fit is unreliable, a cutoff-style rapid drop (faster than 100 dB/s) is required; clicks in noise are used for alignment only if they match the note's drop interval.
- **BPM**: chords are merged into a single onset event → first-, second- and third-order onset intervals are scored with a soft Gaussian kernel over candidate periods (weighted by 1/√k for multiples to suppress half/double periods) → piecewise same-phase grid merging and regression refinement.
- **BPM tempo following (1.0.2)**: switch when the last 6 onsets consistently point to a new tempo, starting a new tempo segment at the change (about 1–1.5 s to catch up; the old version took 4–6 s, or even a dozen seconds when the tempo changed often); within a segment, a weighted estimate with only minor adjustments, so accuracy at a steady tempo is unchanged; when the new and old tempos are integer multiples (which may just be denser/sparser notes), a longer persistence is required to switch (0.8 s faster, 3.2 s slower) to avoid doubling back; for rapid consecutive runs the period floor is lowered from 0.2 s to 0.07 s (readings up to about 850, no longer stuck below 300); when there is a lot of noise and the reading has long lacked support from recent onsets, a 12 s long-window estimate is used instead.
- **Tonality (improved in 1.0.2)**: Krumhansl-Schmuckler key-profile matching over the last 20 s and at least 6 notes; each note is weighted by its "occupied time" (until the next note) rather than its decay length, with extra weight for bass notes and phrase-ending notes (followed by a pause); these Genshin instruments have only white keys, so the candidates are limited to C major / A minor (the app never reports a key that cannot be played on the instrument); confidence = how far the first candidate leads the second, showing "hard to distinguish from X" when they are close; a new key must lead for 2.5 s before the display switches.
- **Chords (improved in 1.0.2)**: only the most recent group of simultaneously pressed notes is considered (previously ringing notes and melody notes played on top of the chord afterwards do not count); arpeggios accumulate from the most recent bass note; a monophonic melody (steps above the bass) is not reported as a chord; common triads/sevenths are preferred, a bass note that is the root gets a bonus, and inversions are shown (e.g., C/E); ghost notes at adjacent frequencies caused by the strike do not participate; a change must persist for 0.15 s before the display switches.
- **Evaluation**: `python test_detection.py` (synthetic-audio regression tests with assertions); `python benchmark_timing.py --old` (timing-accuracy benchmark with ground truth, compared against the git HEAD version); `python benchmark_timing.py --noise --old` (sensitivity comparison of the duration module under background noise/sound effects/music); `python benchmark_timing.py --tempo --old` (how quickly BPM follows frequent tempo changes and whether it jumps at a steady tempo); `python eval_harmony.py` (chord/tonality algorithms compared with the old version); `python eval_screening.py` (boundary check: large-chord counting, script detection and human false positives for long runs, real recordings).

---

## 8. Source Layout

```
├── main.py               Entry point + exception logging + offline analysis (--analyze)
├── app_version.py        Version number (shared by the UI, exe properties and installer)
├── ui_main.py            PySide6 UI
├── audio_capture.py      Audio capture (loopback/microphone)
├── detection.py          Detection engine
├── screening.py          Boundary check (operations beyond human limits)
├── instruments.py        Instrument definitions and key layouts
├── diag.py               Optional diagnostic log (GID_DEBUG=1)
├── test_detection.py     Regression tests (5 synthetic-audio groups + 4 boundary-check groups, with assertions)
├── test_stop_keys.py     Pause/background-noise and key-display regression tests
├── benchmark_timing.py   Timing-accuracy benchmark (onset/duration/BPM vs. ground truth; --old compares with the old version, --noise covers noise scenarios, --tempo covers frequent tempo changes)
├── eval_recordings.py    Old/new comparison on real recordings
├── eval_harmony.py       Chord/tonality algorithm evaluation (known notes, compared with the old version)
├── eval_screening.py     Boundary-check evaluation (large chords, long runs, real recordings)
├── web_test*.wav, v2_lowhigh.wav, score_test.wav   Real recordings used by the evaluation scripts
├── score_seq.json        Note sequence used by the scripted-score benchmark
├── requirements.txt      Runtime dependencies
├── packaging/            Windows packaging: PyInstaller spec, Inno Setup script, icon, one-click build script
├── android_app/          Android app (Kotlin)
└── .github/workflows/    GitHub Actions: pushing a v* tag builds the exe/installer/APK and publishes a Release
```

---

## 9. Building It Yourself

**Windows (exe + installer)**: requires Python 3.10+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```
python -m pip install -r packaging\requirements-build.txt
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The output goes to `dist\`: `原神乐器演奏检测器.exe` (single file), `GenshinInstrumentDetector-<version>-win64-portable.exe`, and `GenshinInstrumentDetector-<version>-win64-setup.exe`.

**Release**: update the version in `app_version.py` and `android_app/app/build.gradle`, then push a tag (for example, `git tag v1.0.1 && git push origin v1.0.1`). GitHub Actions builds the three packages and creates a Release. For a production Android signature, configure `ANDROID_KEYSTORE_BASE64` / `ANDROID_KEYSTORE_PASSWORD` / `ANDROID_KEY_ALIAS` / `ANDROID_KEY_PASSWORD` in the repository Secrets; without them the debug key is used.
