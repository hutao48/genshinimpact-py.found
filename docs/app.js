/* Genshin Instrument Detector — static site */
const I18N = {
  en: {
    skip_link: "Skip to content",
    menu_label: "Open menu",
    menu_close: "Close menu",
    lang_label: "Language",
    nav_features: "Features",
    nav_timeline: "Timeline",
    nav_downloads: "Download",
    nav_security: "Security",
    nav_faq: "FAQ",
    nav_cta: "Download 1.1.5",
    hero_eyebrow: "Windows 1.1.5 / Android 1.1.1",
    hero_h1: 'See the structure<br><span class="hero-accent">inside every note.</span>',
    hero_sub: "Genshin Instrument Detector puts the keys, the BPM and every press and release on one canvas. Not just what you played, but how.",
    hero_cta: "Download for Windows",
    hero_secondary: "See what changed",
    hero_fine: "Free and local. No telemetry. No account.",
    hero_scroll: "Scroll to build",
    stat_instruments: "instruments",
    stat_keys: "keys on the lyre",
    stat_telemetry: "telemetry",
    stat_version: "Windows release",
    stage_canvas: "CANVAS / 01",
    stage_live: "OVERLAY / LIVE",
    stage_auto: "AUTO BUILD",
    stage_hint: "Scroll. The canvas builds itself.",
    stage_status: "Assembling {n} / 3",
    stage_ready: "Canvas ready",
    stage_keys: "Keys",
    stage_bpm: "BPM trend",
    stage_timeline: "Key timeline",
    canvas_mode: "AUTO / 3 LAYERS",
    proof_1: "Six playable instruments",
    proof_2: "Millisecond note timing",
    proof_3: "BPM line and key timeline",
    proof_4: "No account. No telemetry.",
    rail_idea: "THE IDEA",
    statement: "Not a guess at what you played.\nA record of how you played it.",
    statement_note: "Every key, every gap, every tempo change. On one quiet canvas.",
    features_eyebrow: "THREE VIEWS",
    features_title: "One performance.<br>Three ways to see it.",
    features_sub: "The notes are only half of it. See what your hands did, how the tempo moved, and exactly where each key started and stopped.",
    card1_tag: "LIVE KEYS",
    card1_title: "Every key you hold",
    card1_text: "The keyboard lights up in real time, including Ukulele chords and the two row Nightwind Horn layout.",
    card2_tag: "BPM",
    card2_title: "The shape of the tempo",
    card2_text: "A live BPM line with auto scaling ranges and current, average, low and high readouts.",
    card3_tag: "TIMELINE",
    card3_title: "The space between notes",
    card3_text: "Onset, duration, gap and end reason for every note, down to the millisecond.",
    timeline_eyebrow: "KEY TIMELINE / 1.1.5",
    timeline_title: "See how a chord is actually played.",
    timeline_text: "A MIDI editor style timeline. Each bar is a key held down; overlapping lanes are notes played together. Press, release, and everything in between.",
    timeline_li1: "Millisecond press and release positions",
    timeline_li2: "Simultaneous keys line up across lanes",
    timeline_li3: "Ukulele chords and two row horn layouts stay intact",
    timeline_note: "The floating overlay is off by default. Open it from the toolbar whenever you want it.",
    download_eyebrow: "GET THE APP",
    download_title: "Put the next performance on the canvas.",
    download_sub: "Windows 1.1.5 is ready. The installer is per user and needs no administrator rights.",
    win_desc: "Windows 10 or 11, 64 bit. Start the installer and open the app from the Start Menu.",
    win_cta: "Download installer",
    win_portable: "Portable build",
    win_note: "Unsigned exe. SmartScreen may ask you to choose More info, then Run anyway.",
    android_desc: "Android 7.0 and newer. The mobile detector stays on 1.1.1.",
    android_cta: "Get Android 1.1.1",
    android_note: "Unchanged in 1.1.5. Fixed signing since 1.1.0.",
    checksum: "SHA256 checksums",
    release_notes: "Release notes",
    all_releases: "All releases",
    security_eyebrow: "PRIVACY / SECURITY",
    security_title: "Local by default.",
    sec1_title: "No telemetry",
    sec1_text: "Audio never leaves your computer. No analytics, account or cloud processing.",
    sec2_title: "Bounded update check",
    sec2_text: "An optional HTTPS query to GitHub Releases, with a 12 second timeout and hard size limits.",
    sec3_title: "Verified installs",
    sec3_text: "Automatic updates verify the published SHA256 and the PE header before running the installer.",
    faq_eyebrow: "QUESTIONS",
    faq_title: "A few things<br>before you download.",
    faq1_q: "Does the overlay open automatically?",
    faq1_a: "No. It is off by default. Use the toolbar button or enable it in Settings; your choice is remembered.",
    faq2_q: "What changed in 1.1.5?",
    faq2_a: "Export is fixed, the overlay BPM trend refreshes, and the old metric text is replaced by a MIDI style key timeline.",
    faq3_q: "Will Android be updated?",
    faq3_a: "No. Android stays at 1.1.1; the 1.1.5 release is Windows only.",
    faq4_q: "What does Export write?",
    faq4_a: "Three UTF8 CSV files: note durations, BPM history, and boundary checks. A completion dialog can open the folder.",
    faq5_q: "Which instruments are supported?",
    faq5_a: "Windsong Lyre, Floral Zither, Vintage Lyre, Harmonic Keys, Nightwind Horn and Ukulele, with the correct key layouts.",
    faq6_q: "Does it need an internet connection?",
    faq6_a: "No. Detection and export are local. Only the optional update check contacts GitHub.",
    final_eyebrow: "ONE LAST THING",
    final_title: "Hear it. See it.<br>Keep it.",
    final_cta: "Download for Windows 1.1.5",
    final_note: "Windows 1.1.5 · Android 1.1.1 · Local by default",
    footer_tagline: "Independent fan tool. Not affiliated with HoYoverse.",
    footer_guide: "中文使用说明",
    build_label: "PAGE BUILD",
    meta_title: "Genshin Instrument Detector · See the structure inside every performance",
    meta_desc: "A real time Genshin Impact instrument detector for Windows. Keys, chords, BPM and a MIDI style key timeline, on one transparent canvas."
  },
  "zh-CN": {
    skip_link: "跳到主要内容",
    menu_label: "打开菜单",
    menu_close: "关闭菜单",
    lang_label: "语言",
    nav_features: "功能",
    nav_timeline: "时间线",
    nav_downloads: "下载",
    nav_security: "安全",
    nav_faq: "常见问题",
    nav_cta: "下载 1.1.5",
    hero_eyebrow: "Windows 1.1.5 / Android 1.1.1",
    hero_h1: '把演奏，<br><span class="hero-accent">拆成看得见的结构。</span>',
    hero_sub: "原神乐器演奏检测器把琴键、BPM 和每一次起落放上同一张画布。听见的不只是旋律，还有它是怎么被弹出来的。",
    hero_cta: "下载 Windows 版",
    hero_secondary: "看看改了什么",
    hero_fine: "免费、本地运行、无遥测、无账号。",
    hero_scroll: "滚动，开始搭建",
    stat_instruments: "种乐器",
    stat_keys: "键诗琴",
    stat_telemetry: "遥测",
    stat_version: "Windows 版本",
    stage_canvas: "画布 / 01",
    stage_live: "悬浮窗 / 实时",
    stage_auto: "自动搭建",
    stage_hint: "滚动页面，画布会自己搭建。",
    stage_status: "正在搭建 {n} / 3",
    stage_ready: "画布已就绪",
    stage_keys: "琴键",
    stage_bpm: "BPM 走向",
    stage_timeline: "按键时间线",
    canvas_mode: "自动 / 3 个图层",
    proof_1: "六种可演奏乐器",
    proof_2: "毫秒级音符时长",
    proof_3: "BPM 折线与按键时间线",
    proof_4: "无账号，无遥测",
    rail_idea: "设计思路",
    statement: "不是猜你弹了什么。\n是把每个动作，留在时间线上。",
    statement_note: "每个键、每段间隔、每次速度变化，都在这张安静的画面里。",
    features_eyebrow: "三种视角",
    features_title: "一次演奏。<br>三种读法。",
    features_sub: "音符只是其中一半。看见手怎么落下、速度怎么移动，以及每个键从哪里开始、在哪里结束。",
    card1_tag: "实时琴键",
    card1_title: "你按住的每个键",
    card1_text: "琴键实时亮起，悠可琴和弦键与晚风圆号两排布局也完整保留。",
    card2_tag: "BPM",
    card2_title: "速度的形状",
    card2_text: "实时 BPM 折线，支持自动缩放区间，并显示当前、平均、最低和最高值。",
    card3_tag: "时间线",
    card3_title: "音符之间的空隙",
    card3_text: "每个音的起音、时长、间隔和结束方式，精确到毫秒。",
    timeline_eyebrow: "按键时间线 / 1.1.5",
    timeline_title: "看见一个和弦，是怎么被按下的。",
    timeline_text: "MIDI 编辑器风格的时间线。每根横条是一个键按住的时长，重叠的轨道是同时按下的音。按下、放开，以及中间的一切。",
    timeline_li1: "毫秒级按下与放开位置",
    timeline_li2: "同时按下的键在相邻轨道对齐",
    timeline_li3: "悠可琴和弦、圆号两排完整保留",
    timeline_note: "悬浮窗默认关闭，需要时从顶栏打开。",
    download_eyebrow: "获取应用",
    download_title: "把下一次演奏，留在画布上。",
    download_sub: "Windows 1.1.5 已就绪。安装到当前用户，无需管理员权限。",
    win_desc: "Windows 10 或 11，64 位。运行安装程序，从开始菜单打开应用。",
    win_cta: "下载安装程序",
    win_portable: "免安装版",
    win_note: "exe 未做代码签名。SmartScreen 可能提示，选择“更多信息 → 仍要运行”。",
    android_desc: "Android 7.0 及以上。手机端检测器保持 1.1.1。",
    android_cta: "获取 Android 1.1.1",
    android_note: "1.1.5 未更新 Android；1.1.0 起固定签名。",
    checksum: "SHA256 校验和",
    release_notes: "更新说明",
    all_releases: "全部版本",
    security_eyebrow: "隐私 / 安全",
    security_title: "默认本地。",
    sec1_title: "无遥测",
    sec1_text: "音频不会离开你的电脑。没有统计、账号或云端处理。",
    sec2_title: "有边界的更新检查",
    sec2_text: "可选的 GitHub Releases HTTPS 查询，12 秒超时，并限制数据与安装包大小。",
    sec3_title: "校验后安装",
    sec3_text: "自动更新会先校验公开的 SHA256 和 PE 头，再运行安装程序。",
    faq_eyebrow: "常见问题",
    faq_title: "下载前，<br>你可能想知道。",
    faq1_q: "悬浮窗会自动打开吗？",
    faq1_a: "不会，默认关闭。可以从顶栏按钮打开，或在设置里勾选；你的选择会被记住。",
    faq2_q: "1.1.5 更新了什么？",
    faq2_a: "修复导出，修复悬浮窗 BPM 走向不刷新，并把原来的指标文字换成 MIDI 风格按键时间线。",
    faq3_q: "Android 会更新吗？",
    faq3_a: "不会。Android 保持 1.1.1，本次 1.1.5 只更新 Windows。",
    faq4_q: "导出会生成什么？",
    faq4_a: "三个 UTF8 CSV：音符时长、BPM 历史、边界值排查。完成后可以直接打开所在文件夹。",
    faq5_q: "支持哪些乐器？",
    faq5_a: "风物之诗琴、镜花之琴、跃律琴、谐律键琴、晚风圆号和悠可琴，均使用正确键位。",
    faq6_q: "需要联网吗？",
    faq6_a: "不需要。检测与导出都在本地；只有可选的更新检查会访问 GitHub。",
    final_eyebrow: "最后一件事",
    final_title: "听见它。看见它。<br>留下它。",
    final_cta: "下载 Windows 1.1.5",
    final_note: "Windows 1.1.5 · Android 1.1.1 · 默认本地运行",
    footer_tagline: "独立同人工具，与 HoYoverse 无关联。",
    footer_guide: "中文使用说明",
    build_label: "页面搭建",
    meta_title: "原神乐器演奏检测器 · 看见演奏里的结构",
    meta_desc: "Windows 实时原神乐器检测器：琴键、和弦、BPM 和 MIDI 风格按键时间线，都在一张透明画布上。"
  },
  "zh-Hant": {
    skip_link: "跳到主要內容",
    menu_label: "開啟選單",
    menu_close: "關閉選單",
    lang_label: "語言",
    nav_features: "功能",
    nav_timeline: "時間線",
    nav_downloads: "下載",
    nav_security: "安全",
    nav_faq: "常見問題",
    nav_cta: "下載 1.1.5",
    hero_eyebrow: "Windows 1.1.5 / Android 1.1.1",
    hero_h1: '把演奏，<br><span class="hero-accent">拆成看得見的結構。</span>',
    hero_sub: "原神樂器演奏檢測器把琴鍵、BPM 和每一次起落放上同一張畫布。聽見的不只是旋律，還有它是怎麼被彈出來的。",
    hero_cta: "下載 Windows 版",
    hero_secondary: "看看改了什麼",
    hero_fine: "免費、本機執行、無遙測、無帳號。",
    hero_scroll: "捲動，開始搭建",
    stat_instruments: "種樂器",
    stat_keys: "鍵詩琴",
    stat_telemetry: "遙測",
    stat_version: "Windows 版本",
    stage_canvas: "畫布 / 01",
    stage_live: "懸浮窗 / 即時",
    stage_auto: "自動搭建",
    stage_hint: "捲動頁面，畫布會自己搭建。",
    stage_status: "正在搭建 {n} / 3",
    stage_ready: "畫布已就緒",
    stage_keys: "琴鍵",
    stage_bpm: "BPM 走向",
    stage_timeline: "按鍵時間線",
    canvas_mode: "自動 / 3 個圖層",
    proof_1: "六種可演奏樂器",
    proof_2: "毫秒級音符時長",
    proof_3: "BPM 折線與按鍵時間線",
    proof_4: "無帳號，無遙測",
    rail_idea: "設計思路",
    statement: "不是猜你彈了什麼。\n是把每個動作，留在時間線上。",
    statement_note: "每個鍵、每段間隔、每次速度變化，都在這張安靜的畫面裡。",
    features_eyebrow: "三種視角",
    features_title: "一次演奏。<br>三種讀法。",
    features_sub: "音符只是其中一半。看見手怎麼落下、速度怎麼移動，以及每個鍵從哪裡開始、在哪裡結束。",
    card1_tag: "即時琴鍵",
    card1_title: "你按住的每個鍵",
    card1_text: "琴鍵即時亮起，悠可琴和弦鍵與晚風圓號兩排佈局也完整保留。",
    card2_tag: "BPM",
    card2_title: "速度的形狀",
    card2_text: "即時 BPM 折線，支援自動縮放區間，並顯示目前、平均、最低和最高值。",
    card3_tag: "時間線",
    card3_title: "音符之間的空隙",
    card3_text: "每個音的起音、時長、間隔和結束方式，精確到毫秒。",
    timeline_eyebrow: "按鍵時間線 / 1.1.5",
    timeline_title: "看見一個和弦，是怎麼被按下的。",
    timeline_text: "MIDI 編輯器風格時間線。每根橫條是一個鍵按住的時長，重疊的軌道是同時按下的音。按下、放開，以及中間的一切。",
    timeline_li1: "毫秒級按下與放開位置",
    timeline_li2: "同時按下的鍵在相鄰軌道對齊",
    timeline_li3: "悠可琴和弦、圓號兩排完整保留",
    timeline_note: "懸浮窗預設關閉，需要時從頂欄開啟。",
    download_eyebrow: "取得應用程式",
    download_title: "把下一次演奏，留在畫布上。",
    download_sub: "Windows 1.1.5 已就緒。安裝到目前使用者，無需管理員權限。",
    win_desc: "Windows 10 或 11，64 位元。執行安裝程式，從開始功能表開啟應用程式。",
    win_cta: "下載安裝程式",
    win_portable: "免安裝版",
    win_note: "exe 未做程式碼簽章。SmartScreen 可能提示，選擇「更多資訊 → 仍要執行」。",
    android_desc: "Android 7.0 以上。手機端檢測器保持 1.1.1。",
    android_cta: "取得 Android 1.1.1",
    android_note: "1.1.5 未更新 Android；1.1.0 起固定簽章。",
    checksum: "SHA256 校驗和",
    release_notes: "更新說明",
    all_releases: "全部版本",
    security_eyebrow: "隱私 / 安全",
    security_title: "預設本機。",
    sec1_title: "無遙測",
    sec1_text: "音訊不會離開你的電腦。沒有統計、帳號或雲端處理。",
    sec2_title: "有邊界的更新檢查",
    sec2_text: "可選的 GitHub Releases HTTPS 查詢，12 秒逾時，並限制資料與安裝包大小。",
    sec3_title: "校驗後安裝",
    sec3_text: "自動更新會先校驗公開的 SHA256 和 PE 標頭，再執行安裝程式。",
    faq_eyebrow: "常見問題",
    faq_title: "下載前，<br>你可能想知道。",
    faq1_q: "懸浮窗會自動開啟嗎？",
    faq1_a: "不會，預設關閉。可從頂欄按鈕開啟，或在設定裡勾選；你的選擇會被記住。",
    faq2_q: "1.1.5 更新了什麼？",
    faq2_a: "修復匯出，修復懸浮窗 BPM 走向不刷新，並把原本的指標文字換成 MIDI 風格按鍵時間線。",
    faq3_q: "Android 會更新嗎？",
    faq3_a: "不會。Android 保持 1.1.1，本次 1.1.5 只更新 Windows。",
    faq4_q: "匯出會產生什麼？",
    faq4_a: "三個 UTF8 CSV：音符時長、BPM 歷史、邊界值排查。完成後可以直接開啟所在資料夾。",
    faq5_q: "支援哪些樂器？",
    faq5_a: "風物之詩琴、鏡花之琴、躍律琴、諧律鍵琴、晚風圓號和悠可琴，均使用正確鍵位。",
    faq6_q: "需要連網嗎？",
    faq6_a: "不需要。偵測與匯出都在本機；只有可選的更新檢查會存取 GitHub。",
    final_eyebrow: "最後一件事",
    final_title: "聽見它。看見它。<br>留下它。",
    final_cta: "下載 Windows 1.1.5",
    final_note: "Windows 1.1.5 · Android 1.1.1 · 預設本機執行",
    footer_tagline: "獨立同人工具，與 HoYoverse 無關聯。",
    footer_guide: "中文使用說明",
    build_label: "頁面搭建",
    meta_title: "原神樂器演奏檢測器 · 看見演奏裡的結構",
    meta_desc: "Windows 即時原神樂器檢測器：琴鍵、和弦、BPM 和 MIDI 風格按鍵時間線，都在一張透明畫布上。"
  },
  "zh-TW": {
    skip_link: "跳到主要內容",
    menu_label: "開啟選單",
    menu_close: "關閉選單",
    lang_label: "語言",
    nav_features: "功能",
    nav_timeline: "時間軸",
    nav_downloads: "下載",
    nav_security: "安全",
    nav_faq: "常見問題",
    nav_cta: "下載 1.1.5",
    hero_eyebrow: "Windows 1.1.5 / Android 1.1.1",
    hero_h1: '把演奏，<br><span class="hero-accent">拆成看得見的結構。</span>',
    hero_sub: "原神樂器演奏檢測器把琴鍵、BPM 和每一次起落放上同一張畫布。聽見的不只是旋律，還有它是怎麼被彈出來的。",
    hero_cta: "下載 Windows 版",
    hero_secondary: "看看改了什麼",
    hero_fine: "免費、本機執行、無遙測、無帳號。",
    hero_scroll: "捲動，開始搭建",
    stat_instruments: "種樂器",
    stat_keys: "鍵詩琴",
    stat_telemetry: "遙測",
    stat_version: "Windows 版本",
    stage_canvas: "畫布 / 01",
    stage_live: "懸浮視窗 / 即時",
    stage_auto: "自動搭建",
    stage_hint: "捲動頁面，畫布會自己搭建。",
    stage_status: "正在搭建 {n} / 3",
    stage_ready: "畫布已就緒",
    stage_keys: "琴鍵",
    stage_bpm: "BPM 走向",
    stage_timeline: "按鍵時間軸",
    canvas_mode: "自動 / 3 個圖層",
    proof_1: "六種可演奏樂器",
    proof_2: "毫秒級音符時長",
    proof_3: "BPM 折線與按鍵時間軸",
    proof_4: "無帳號，無遙測",
    rail_idea: "設計思路",
    statement: "不是猜你彈了什麼。\n是把每個動作，留在時間軸上。",
    statement_note: "每個鍵、每段間隔、每次速度變化，都在這張安靜的畫面裡。",
    features_eyebrow: "三種視角",
    features_title: "一次演奏。<br>三種讀法。",
    features_sub: "音符只是其中一半。看見手怎麼落下、速度怎麼移動，以及每個鍵從哪裡開始、在哪裡結束。",
    card1_tag: "即時琴鍵",
    card1_title: "你按住的每個鍵",
    card1_text: "琴鍵即時亮起，悠可琴和弦鍵與晚風圓號兩排配置也完整保留。",
    card2_tag: "BPM",
    card2_title: "速度的形狀",
    card2_text: "即時 BPM 折線，支援自動縮放區間，並顯示目前、平均、最低和最高值。",
    card3_tag: "時間軸",
    card3_title: "音符之間的空隙",
    card3_text: "每個音的起音、時長、間隔和結束方式，精確到毫秒。",
    timeline_eyebrow: "按鍵時間軸 / 1.1.5",
    timeline_title: "看見一個和弦，是怎麼被按下的。",
    timeline_text: "MIDI 編輯器風格時間軸。每根橫條是一個鍵按住的時長，重疊的軌道是同時按下的音。按下、放開，以及中間的一切。",
    timeline_li1: "毫秒級按下與放開位置",
    timeline_li2: "同時按下的鍵在相鄰軌道對齊",
    timeline_li3: "悠可琴和弦、圓號兩排完整保留",
    timeline_note: "懸浮視窗預設關閉，需要時從頂欄開啟。",
    download_eyebrow: "取得應用程式",
    download_title: "把下一次演奏，留在畫布上。",
    download_sub: "Windows 1.1.5 已就緒。安裝到目前使用者，無需管理員權限。",
    win_desc: "Windows 10 或 11，64 位元。執行安裝程式，從開始功能表開啟應用程式。",
    win_cta: "下載安裝程式",
    win_portable: "免安裝版",
    win_note: "exe 未做程式碼簽章。SmartScreen 可能提示，選擇「更多資訊 → 仍要執行」。",
    android_desc: "Android 7.0 以上。手機端檢測器保持 1.1.1。",
    android_cta: "取得 Android 1.1.1",
    android_note: "1.1.5 未更新 Android；1.1.0 起固定簽章。",
    checksum: "SHA256 校驗和",
    release_notes: "更新說明",
    all_releases: "全部版本",
    security_eyebrow: "隱私 / 安全",
    security_title: "預設本機。",
    sec1_title: "無遙測",
    sec1_text: "音訊不會離開你的電腦。沒有統計、帳號或雲端處理。",
    sec2_title: "有邊界的更新檢查",
    sec2_text: "可選的 GitHub Releases HTTPS 查詢，12 秒逾時，並限制資料與安裝包大小。",
    sec3_title: "驗證後安裝",
    sec3_text: "自動更新會先驗證公開的 SHA256 和 PE 標頭，再執行安裝程式。",
    faq_eyebrow: "常見問題",
    faq_title: "下載前，<br>你可能想知道。",
    faq1_q: "懸浮視窗會自動開啟嗎？",
    faq1_a: "不會，預設關閉。可從頂欄按鈕開啟，或在設定裡勾選；你的選擇會被記住。",
    faq2_q: "1.1.5 更新了什麼？",
    faq2_a: "修復匯出，修復懸浮視窗 BPM 走向不刷新，並把原本的指標文字換成 MIDI 風格按鍵時間軸。",
    faq3_q: "Android 會更新嗎？",
    faq3_a: "不會。Android 保持 1.1.1，本次 1.1.5 只更新 Windows。",
    faq4_q: "匯出會產生什麼？",
    faq4_a: "三個 UTF8 CSV：音符時長、BPM 歷史、邊界值排查。完成後可以直接開啟所在資料夾。",
    faq5_q: "支援哪些樂器？",
    faq5_a: "風物之詩琴、鏡花之琴、躍律琴、諧律鍵琴、晚風圓號和悠可琴，均使用正確鍵位。",
    faq6_q: "需要連網嗎？",
    faq6_a: "不需要。偵測與匯出都在本機；只有可選的更新檢查會存取 GitHub。",
    final_eyebrow: "最後一件事",
    final_title: "聽見它。看見它。<br>留下它。",
    final_cta: "下載 Windows 1.1.5",
    final_note: "Windows 1.1.5 · Android 1.1.1 · 預設本機執行",
    footer_tagline: "獨立同人工具，與 HoYoverse 無關聯。",
    footer_guide: "中文使用說明",
    build_label: "頁面搭建",
    meta_title: "原神樂器演奏檢測器 · 看見演奏裡的結構",
    meta_desc: "Windows 即時原神樂器檢測器：琴鍵、和弦、BPM 和 MIDI 風格按鍵時間軸，都在一張透明畫布上。"
  },
  ja: {
    skip_link: "本文へ移動",
    menu_label: "メニューを開く",
    menu_close: "メニューを閉じる",
    lang_label: "言語",
    nav_features: "機能",
    nav_timeline: "タイムライン",
    nav_downloads: "ダウンロード",
    nav_security: "セキュリティ",
    nav_faq: "よくある質問",
    nav_cta: "1.1.5 をダウンロード",
    hero_eyebrow: "Windows 1.1.5 / Android 1.1.1",
    hero_h1: '演奏を、<br><span class="hero-accent">見える構造に。</span>',
    hero_sub: "原神楽器演奏検出器は、鍵盤、BPM、押下と離鍵のすべてを一枚のキャンバスに並べます。何を弾いたかだけでなく、どう弾いたかまで。",
    hero_cta: "Windows 版をダウンロード",
    hero_secondary: "変更点を見る",
    hero_fine: "無料、ローカル動作、テレメトリーなし、アカウント不要。",
    hero_scroll: "スクロールして構築",
    stat_instruments: "楽器",
    stat_keys: "鍵のリラ",
    stat_telemetry: "テレメトリー",
    stat_version: "Windows 版",
    stage_canvas: "キャンバス / 01",
    stage_live: "オーバーレイ / LIVE",
    stage_auto: "自動ビルド",
    stage_hint: "スクロールすると、キャンバスが自動で組み上がります。",
    stage_status: "構築中 {n} / 3",
    stage_ready: "キャンバス準備完了",
    stage_keys: "鍵盤",
    stage_bpm: "BPM の推移",
    stage_timeline: "キー・タイムライン",
    canvas_mode: "自動 / 3 レイヤー",
    proof_1: "6 種類の演奏楽器",
    proof_2: "ミリ秒単位の音符タイミング",
    proof_3: "BPM ラインとキー・タイムライン",
    proof_4: "アカウント不要、テレメトリーなし",
    rail_idea: "考え方",
    statement: "何を弾いたかを当てるのではなく。\nどう弾いたかを、時間軸に残す。",
    statement_note: "すべての鍵、すべての間、すべてのテンポ変化を、静かな一枚に。",
    features_eyebrow: "3 つの視点",
    features_title: "1 回の演奏。<br>3 つの見方。",
    features_sub: "音符は半分にすぎません。手がどう動き、テンポがどう変わり、各鍵がどこで始まりどこで終わったかを見ます。",
    card1_tag: "LIVE KEYS",
    card1_title: "押しているすべての鍵",
    card1_text: "ウクレレのコード鍵や、晚風の円号の 2 段配置も含めてリアルタイムに光ります。",
    card2_tag: "BPM",
    card2_title: "テンポの形",
    card2_text: "自動スケールの BPM ライン。現在、平均、最低、最高の値も表示します。",
    card3_tag: "TIMELINE",
    card3_title: "音符の間の余白",
    card3_text: "各音の発音、長さ、間隔、終了理由をミリ秒単位で記録します。",
    timeline_eyebrow: "キー・タイムライン / 1.1.5",
    timeline_title: "コードがどう押されたか、見る。",
    timeline_text: "MIDI エディタ風のタイムライン。横バーは鍵を押していた時間、重なるレーンは同時に弾いた音です。押下、離鍵、その間のすべて。",
    timeline_li1: "ミリ秒単位の押下と離鍵の位置",
    timeline_li2: "同時押しは隣のレーンに並ぶ",
    timeline_li3: "ウクレレのコードと円号の 2 段を維持",
    timeline_note: "フローティングは既定で非表示。ツールバーからいつでも開けます。",
    download_eyebrow: "アプリを入手",
    download_title: "次の演奏を、キャンバスに。",
    download_sub: "Windows 1.1.5 の準備ができました。現在のユーザーにインストールされ、管理者権限は不要です。",
    win_desc: "Windows 10 / 11、64 ビット。インストーラーを実行し、スタートメニューから開きます。",
    win_cta: "インストーラーをダウンロード",
    win_portable: "ポータブル版",
    win_note: "exe はコード署名されていません。SmartScreen が表示された場合は「詳細情報」から実行してください。",
    android_desc: "Android 7.0 以上。モバイル版は 1.1.1 のままです。",
    android_cta: "Android 1.1.1 を入手",
    android_note: "1.1.5 では更新していません。1.1.0 以降は固定署名です。",
    checksum: "SHA256 チェックサム",
    release_notes: "リリースノート",
    all_releases: "すべてのリリース",
    security_eyebrow: "プライバシー / セキュリティ",
    security_title: "既定でローカル。",
    sec1_title: "テレメトリーなし",
    sec1_text: "音声が PC の外へ送られることはありません。解析、アカウント、クラウド処理はありません。",
    sec2_title: "制限された更新確認",
    sec2_text: "任意の GitHub Releases HTTPS 問い合わせ。12 秒のタイムアウトとサイズ上限があります。",
    sec3_title: "検証してからインストール",
    sec3_text: "自動更新は公開 SHA256 と PE ヘッダーを検証してからインストーラーを実行します。",
    faq_eyebrow: "よくある質問",
    faq_title: "ダウンロードの前に。",
    faq1_q: "フローティングは自動で開きますか？",
    faq1_a: "いいえ。既定ではオフです。ツールバーから開くか、設定で有効にしてください。選択は記憶されます。",
    faq2_q: "1.1.5 で何が変わりましたか？",
    faq2_a: "エクスポートを修正し、フローティングの BPM 推移を更新。以前の指標テキストを MIDI 風キー・タイムラインに置き換えました。",
    faq3_q: "Android は更新されますか？",
    faq3_a: "いいえ。Android は 1.1.1 のまま。1.1.5 は Windows のみの更新です。",
    faq4_q: "エクスポートは何を書き出しますか？",
    faq4_a: "UTF8 の CSV を 3 つ。音符の長さ、BPM 履歴、境界チェックです。完了後にフォルダーを開けます。",
    faq5_q: "対応楽器は？",
    faq5_a: "風物の詩琴、鏡花の琴、躍律琴、諧律鍵琴、晩風の円号、悠可琴に対応し、正しい鍵配置を使います。",
    faq6_q: "インターネット接続は必要ですか？",
    faq6_a: "いいえ。検出とエクスポートはローカルです。任意の更新確認だけが GitHub に接続します。",
    final_eyebrow: "最後に",
    final_title: "聴く。見る。<br>残す。",
    final_cta: "Windows 1.1.5 をダウンロード",
    final_note: "Windows 1.1.5 · Android 1.1.1 · 既定でローカル",
    footer_tagline: "非公式のファンツールです。HoYoverse とは無関係です。",
    footer_guide: "中文使用说明",
    build_label: "ページ構築",
    meta_title: "原神楽器演奏検出器 · 演奏の構造を見る",
    meta_desc: "Windows 向けリアルタイム原神楽器検出器。鍵盤、コード、BPM、MIDI 風キー・タイムラインを一枚の透明キャンバスに。"
  }
};

const LANG_INFO = {
  "zh-CN": { label: "简体中文", flag: "assets/flags/cn.svg", emoji: "🇨🇳" },
  "zh-Hant": { label: "繁體中文（香港）", flag: "assets/flags/hk.svg", emoji: "🇭🇰" },
  "zh-TW": { label: "正體中文（臺灣）", flag: "assets/flags/tw.svg", emoji: "🇹🇼" },
  en: { label: "English", flag: "assets/flags/us.svg", emoji: "🇺🇸" },
  ja: { label: "日本語", flag: "assets/flags/jp.svg", emoji: "🇯🇵" }
};

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let currentLang = "en";

function T(key, vars) {
  const dict = I18N[currentLang] || I18N.en;
  let value = dict[key] !== undefined ? dict[key] : (I18N.en[key] !== undefined ? I18N.en[key] : key);
  if (vars) {
    value = value.replace(/\{(\w+)\}/g, (m, name) => vars[name] !== undefined ? vars[name] : m);
  }
  return value;
}

const langPicker = document.getElementById("lang-picker");
const langButton = document.getElementById("lang-button");
const langMenu = document.getElementById("lang-menu");
const langFlag = document.getElementById("lang-flag");
const langLabel = document.getElementById("lang-label");
const menuToggle = document.getElementById("menu-toggle");
const mobileMenu = document.getElementById("mobile-menu");
const metaDesc = document.querySelector('meta[name="description"]');

function closeLangMenu() {
  langMenu.classList.remove("open");
  langButton.setAttribute("aria-expanded", "false");
}

function applyLanguage(lang) {
  if (!I18N[lang]) lang = "en";
  currentLang = lang;
  const dict = I18N[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = T(key);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    el.innerHTML = T(key);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    const key = el.getAttribute("data-i18n-aria");
    el.setAttribute("aria-label", T(key));
  });
  document.title = dict.meta_title || I18N.en.meta_title;
  if (metaDesc) metaDesc.setAttribute("content", dict.meta_desc || I18N.en.meta_desc);
  const info = LANG_INFO[lang];
  langFlag.src = info.flag;
  langFlag.alt = info.emoji;
  langLabel.textContent = info.label;
  langButton.setAttribute("aria-label", info.emoji + " " + info.label);
  document.querySelectorAll(".lang-option").forEach((el) => {
    el.setAttribute("aria-selected", el.getAttribute("data-lang") === lang ? "true" : "false");
  });
  if (menuToggle) {
    menuToggle.setAttribute("aria-label", document.body.classList.contains("menu-open") ? T("menu_close") : T("menu_label"));
  }
  renderStatement();
  updateStageStatus();
  try { localStorage.setItem("gid-lang", lang); } catch (e) {}
}

function initialLanguage() {
  try {
    const query = new URLSearchParams(location.search).get("lang");
    if (query && I18N[query]) return query;
  } catch (e) {}
  try {
    const saved = localStorage.getItem("gid-lang");
    if (saved && I18N[saved]) return saved;
  } catch (e) {}
  const nav = (navigator.language || "en").toLowerCase();
  if (nav.startsWith("ja")) return "ja";
  if (nav === "zh-tw" || nav === "zh-hk" || nav.includes("hant")) return "zh-TW";
  if (nav.startsWith("zh")) return "zh-CN";
  return "en";
}

langButton.addEventListener("click", () => {
  const open = langMenu.classList.toggle("open");
  langButton.setAttribute("aria-expanded", open ? "true" : "false");
});
langMenu.querySelectorAll(".lang-option").forEach((el) => {
  el.addEventListener("click", () => {
    applyLanguage(el.getAttribute("data-lang"));
    closeLangMenu();
    langButton.focus();
  });
});
document.addEventListener("click", (e) => {
  if (!langPicker.contains(e.target)) closeLangMenu();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeLangMenu();
    closeMobileMenu();
  }
});

/* mobile menu */
function openMobileMenu() {
  document.body.classList.add("menu-open");
  mobileMenu.setAttribute("aria-hidden", "false");
  menuToggle.setAttribute("aria-expanded", "true");
  menuToggle.setAttribute("aria-label", T("menu_close"));
}
function closeMobileMenu() {
  document.body.classList.remove("menu-open");
  mobileMenu.setAttribute("aria-hidden", "true");
  menuToggle.setAttribute("aria-expanded", "false");
  menuToggle.setAttribute("aria-label", T("menu_label"));
}
if (menuToggle) {
  menuToggle.addEventListener("click", () => {
    if (document.body.classList.contains("menu-open")) closeMobileMenu();
    else openMobileMenu();
  });
  mobileMenu.querySelectorAll("a").forEach((a) => a.addEventListener("click", closeMobileMenu));
}

/* nav state */
const nav = document.getElementById("nav");
let navTicking = false;
function updateNav() {
  nav.classList.toggle("scrolled", window.scrollY > 16);
  navTicking = false;
}
window.addEventListener("scroll", () => {
  if (!navTicking) {
    navTicking = true;
    requestAnimationFrame(updateNav);
  }
}, { passive: true });
updateNav();

/* statement word reveal */
let wordObserver = null;
function tokenize(line) {
  if (/[\u3040-\u30ff\u3400-\u9fff]/.test(line)) return Array.from(line);
  return line.split(/(\s+)/).filter(Boolean);
}
function renderStatement() {
  const target = document.getElementById("statement-text");
  if (!target) return;
  const lines = T("statement").split("\n");
  target.innerHTML = "";
  lines.forEach((line, lineIndex) => {
    const lineEl = document.createElement("span");
    lineEl.className = "statement-line" + (lineIndex === lines.length - 1 ? " accent" : "");
    tokenize(line).forEach((token) => {
      if (/^\s+$/.test(token)) {
        lineEl.append(document.createTextNode(token));
      } else {
        const span = document.createElement("span");
        span.className = "w";
        span.textContent = token;
        lineEl.append(span);
      }
    });
    target.append(lineEl);
  });
  if (wordObserver) wordObserver.disconnect();
  const words = target.querySelectorAll(".w");
  if (reduceMotion) {
    words.forEach((w) => w.classList.add("lit"));
    return;
  }
  wordObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("lit");
        wordObserver.unobserve(entry.target);
      }
    });
  }, { rootMargin: "-24% 0px -48% 0px", threshold: 0 });
  words.forEach((w) => wordObserver.observe(w));
}

/* hero stage automatic build */
const stage = document.getElementById("stage");
const stageReveals = document.getElementById("stage-reveals");
const stageStatus = document.getElementById("stage-status");
const stageMarquee = document.getElementById("stage-marquee");
const stageMarqueeLabel = document.getElementById("stage-marquee-label");
const stageCursor = document.getElementById("stage-cursor");
const stageRegions = [
  { key: "keys", x: 0.016, y: 0.13, w: 0.56, h: 0.76 },
  { key: "bpm", x: 0.60, y: 0.13, w: 0.38, h: 0.38 },
  { key: "timeline", x: 0.60, y: 0.56, w: 0.38, h: 0.33 }
];
let stageBuiltCount = 0;
let stageRunning = false;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function updateStageStatus() {
  if (!stageStatus) return;
  stageStatus.textContent = T("stage_status", { n: stageBuiltCount });
}

function positionStageReveal(el, region) {
  if (!stage) return;
  const sw = stage.clientWidth;
  const sh = stage.clientHeight;
  el.style.left = (region.x * 100) + "%";
  el.style.top = (region.y * 100) + "%";
  el.style.width = (region.w * 100) + "%";
  el.style.height = (region.h * 100) + "%";
  const img = el.querySelector("img");
  if (img) {
    img.style.width = sw + "px";
    img.style.height = sh + "px";
    img.style.left = (-region.x * sw) + "px";
    img.style.top = (-region.y * sh) + "px";
  }
}

function makeStageReveal(region) {
  const div = document.createElement("div");
  div.className = "stage-reveal";
  div.dataset.region = region.key;
  const img = document.createElement("img");
  img.src = "assets/overlay.png";
  img.alt = "";
  img.setAttribute("aria-hidden", "true");
  div.append(img);
  stageReveals.append(div);
  positionStageReveal(div, region);
  return div;
}

function addStageReveal(region, animate) {
  const div = makeStageReveal(region);
  if (!animate) {
    div.classList.add("visible");
    return;
  }
  requestAnimationFrame(() => div.classList.add("visible"));
}

async function selectStageRegion(region) {
  if (!stage) return;
  const sw = stage.clientWidth;
  const sh = stage.clientHeight;
  const x = region.x * sw;
  const y = region.y * sh;
  const w = region.w * sw;
  const h = region.h * sh;
  stageCursor.style.transform = "translate(" + Math.max(0, x - 16) + "px," + Math.max(0, y - 18) + "px)";
  stageCursor.classList.add("on");
  await wait(300);
  stageMarquee.style.left = x + "px";
  stageMarquee.style.top = y + "px";
  stageMarquee.style.width = w + "px";
  stageMarquee.style.height = h + "px";
  stageMarqueeLabel.textContent = Math.round(w) + " × " + Math.round(h);
  void stageMarquee.offsetWidth;
  stageMarquee.classList.add("draw");
  await wait(560);
  stageMarquee.classList.remove("draw");
  stageCursor.classList.remove("on");
  await wait(160);
}

async function autoBuildStage() {
  if (!stage || stageRunning) return;
  stageRunning = true;
  if (reduceMotion) {
    stageRegions.forEach((region) => {
      addStageReveal(region, false);
      document.querySelector('[data-bp="' + region.key + '"]')?.classList.add("built");
    });
    stageBuiltCount = stageRegions.length;
    updateStageStatus();
    stage.classList.add("complete");
    return;
  }
  await wait(500);
  for (const region of stageRegions) {
    await selectStageRegion(region);
    addStageReveal(region, true);
    document.querySelector('[data-bp="' + region.key + '"]')?.classList.add("built");
    stageBuiltCount += 1;
    updateStageStatus();
    await wait(260);
  }
  await wait(360);
  stage.classList.add("complete");
}

window.addEventListener("resize", () => {
  stageReveals.querySelectorAll(".stage-reveal").forEach((el) => {
    const region = stageRegions.find((r) => r.key === el.dataset.region);
    if (region) positionStageReveal(el, region);
  });
});

/* page automatic build */
const buildSections = Array.from(document.querySelectorAll("[data-build]"));
const buildMeter = document.getElementById("build-meter");
const buildCount = document.getElementById("build-count");
const buildFill = document.getElementById("build-fill");
const autoCursor = document.getElementById("auto-cursor");
const autoMarquee = document.getElementById("auto-marquee");
const autoSize = document.getElementById("auto-size");
const totalBuilds = buildSections.length;
let builtSections = 0;
let buildBusy = false;
const buildQueue = [];
const queued = new Set();
let cursorPoint = { x: window.innerWidth * 0.72, y: window.innerHeight * 0.78 };

function updateBuildMeter() {
  if (!buildMeter) return;
  buildMeter.style.display = totalBuilds ? "flex" : "none";
  if (buildCount) buildCount.textContent = String(builtSections).padStart(2, "0") + " / " + String(totalBuilds).padStart(2, "0");
  if (buildFill) buildFill.style.transform = "scaleX(" + (totalBuilds ? builtSections / totalBuilds : 0) + ")";
}

function markBuilt(section) {
  if (!section || section.classList.contains("built")) return;
  section.classList.add("built");
  builtSections += 1;
  updateBuildMeter();
}

function autoRectFor(target) {
  const rect = target.getBoundingClientRect();
  const margin = 16;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = Math.max(margin, rect.left - 10);
  let top = Math.max(78, rect.top - 10);
  let right = Math.min(vw - margin, rect.right + 10);
  let bottom = Math.min(vh - margin, rect.bottom + 10);
  if (right - left < 60) right = Math.min(vw - margin, left + 60);
  if (bottom - top < 40) bottom = Math.min(vh - margin, top + 40);
  return { left, top, width: Math.max(24, right - left), height: Math.max(24, bottom - top) };
}

async function autoSelectSection(section) {
  const target = section.querySelector(section.dataset.target || "") || section.querySelector("h2") || section;
  const mobile = window.matchMedia("(max-width: 760px)").matches;
  if (mobile || reduceMotion) {
    markBuilt(section);
    return;
  }
  const initialRect = target.getBoundingClientRect();
  if (initialRect.bottom < 96 || initialRect.top > window.innerHeight - 48) {
    markBuilt(section);
    return;
  }
  const rect = autoRectFor(target);
  const startX = cursorPoint.x;
  const startY = cursorPoint.y;
  autoCursor.style.transform = "translate(" + (startX - 2) + "px," + (startY - 2) + "px)";
  autoCursor.classList.add("on");
  await wait(340);
  autoCursor.style.transform = "translate(" + (rect.left + rect.width + 12) + "px," + (rect.top + rect.height + 12) + "px)";
  await wait(260);
  autoMarquee.style.left = rect.left + "px";
  autoMarquee.style.top = rect.top + "px";
  autoMarquee.style.width = rect.width + "px";
  autoMarquee.style.height = rect.height + "px";
  autoSize.textContent = Math.round(rect.width) + " × " + Math.round(rect.height);
  void autoMarquee.offsetWidth;
  autoMarquee.classList.add("draw");
  await wait(520);
  markBuilt(section);
  await wait(260);
  autoMarquee.classList.remove("draw");
  autoCursor.classList.remove("on");
  cursorPoint = { x: rect.left + rect.width + 12, y: rect.top + rect.height + 12 };
  await wait(180);
}

async function pumpBuildQueue() {
  if (buildBusy) return;
  if (!buildQueue.length) {
    updateBuildMeter();
    return;
  }
  buildBusy = true;
  buildQueue.sort((a, b) => a.offsetTop - b.offsetTop);
  const section = buildQueue.shift();
  if (section && !section.classList.contains("built")) {
    await autoSelectSection(section);
  }
  buildBusy = false;
  pumpBuildQueue();
}

const buildObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    const section = entry.target;
    if (queued.has(section) || section.classList.contains("built")) return;
    queued.add(section);
    buildQueue.push(section);
    pumpBuildQueue();
  });
}, { threshold: 0.15, rootMargin: "0px 0px -25% 0px" });

buildSections.forEach((section) => {
  if (reduceMotion) markBuilt(section);
  else buildObserver.observe(section);
});
updateBuildMeter();

/* ordinary scroll reveals */
const revealTargets = document.querySelectorAll(".proof-grid, .security-grid, .faq-list, .final-inner");
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add("in");
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });
revealTargets.forEach((el) => {
  el.classList.add("reveal");
  if (reduceMotion) el.classList.add("in");
  else revealObserver.observe(el);
});

/* start */
applyLanguage(initialLanguage());
window.addEventListener("load", () => {
  autoBuildStage();
}, { once: true });
