/* Genshin Instrument Detector — editorial site */
const I18N = {
  "zh-CN": {
    skip_link: "跳到主要内容",
    menu_label: "打开菜单",
    menu_close: "关闭菜单",
    lang_label: "语言",
    nav_about: "关于",
    nav_features: "功能",
    nav_downloads: "下载",
    nav_security: "安全",
    nav_faq: "常见问题",
    nav_cta: "下载",
    hero_kicker: "原神乐器演奏记录工具 · Windows 1.1.5",
    hero_line1: "琴声之后，",
    hero_line2: "演奏还在。",
    hero_sub: "它听见你弹下的每个音，也记下按键、节拍和那些细小的停顿。",
    hero_cta: "下载 Windows 版",
    hero_secondary: "看看这次更新",
    hero_note: "免费 · 本地运行 · 无需账号",
    hero_caption: "悬浮窗 · Windows 1.1.5",
    hero_caption_meta: "琴键 / 节拍 / 时间线",
    hero_scroll: "向下",
    about_index: "01 / 关于",
    about_lead: "它不会替你演奏，也不会评价你弹得怎么样。<br>只是在旁边听着，把听到的东西安静地放好。",
    about_body: "琴键、节拍、每个音的长度。你可以边弹边看，也可以在停下来之后，回头看看刚才的演奏。",
    features_index: "02 / 演奏的痕迹",
    features_title: "留下的，不只是音符。",
    features_lede: "还有按下与松开，快与慢，和那些没有写进谱子的细节。",
    feature1_title: "琴键",
    feature1_text: "按下的键会亮起来。和弦与调性，也会跟着出现。",
    feature2_title: "节拍",
    feature2_text: "速度在变，线也在走。快一点，慢一点，都留在曲子里。",
    feature3_title: "时间",
    feature3_text: "每个音从哪里开始，在哪里结束。间隔和余音，都有记录。",
    timeline_index: "03 / 按键时间线",
    timeline_title: "把和弦，摊开来看。",
    timeline_text: "每一条横线，是一个键按住的时间。几条线并排的时候，就是一个和弦。",
    timeline_li1: "按下和松开，都有准确的时间",
    timeline_li2: "同时按下的音，会并排出现",
    timeline_li3: "悠可琴的和弦键、圆号的两排，也都保留",
    timeline_note: "悬浮窗默认关闭，需要时从顶栏打开。",
    download_index: "04 / 下载",
    download_title: "下次弹琴的时候，<br>它会在。",
    download_lede: "Windows 1.1.5 已准备好。Android 仍是 1.1.1。",
    win_desc: "适用于 Windows 10 和 11（64 位）。安装后，从开始菜单打开。",
    win_cta: "下载安装程序",
    win_portable: "免安装版",
    win_note: "安装包没有代码签名。SmartScreen 可能提示，选择“更多信息”后仍可运行。",
    android_desc: "适用于 Android 7.0 及以上。",
    android_cta: "获取 Android 版",
    android_note: "1.1.5 没有更新 Android。",
    checksum: "校验和",
    release_notes: "更新说明",
    all_releases: "所有版本",
    security_index: "05 / 隐私",
    security_title: "声音留在本地。",
    sec1_title: "没有遥测",
    sec1_text: "音频不会离开你的电脑。没有统计、账号，也没有云端处理。",
    sec2_title: "检查更新有边界",
    sec2_text: "只有在需要时，才会访问 GitHub Releases；有超时和大小限制。",
    sec3_title: "安装前会校验",
    sec3_text: "自动更新会先核对 SHA256 和文件头，再运行安装程序。",
    faq_index: "06 / 下载之前",
    faq_title: "可能想先<br>知道这些。",
    faq1_q: "悬浮窗会自动打开吗？",
    faq1_a: "不会。它默认关闭，可以从顶栏按钮或设置里打开。",
    faq2_q: "1.1.5 改了什么？",
    faq2_a: "修好了导出，修好了悬浮窗里 BPM 曲线不显示的问题；原来的文字指标换成了按键时间线。",
    faq3_q: "Android 会更新吗？",
    faq3_a: "这次不会。Android 仍是 1.1.1。",
    faq4_q: "导出会得到什么？",
    faq4_a: "三份 CSV：音符时长、BPM 和排查记录。导出后可以直接打开文件夹。",
    faq5_q: "支持哪些乐器？",
    faq5_a: "风物之诗琴、镜花之琴、跃律琴、谐律键琴、晚风圆号和悠可琴。",
    faq6_q: "需要联网吗？",
    faq6_a: "不需要。检测和导出都在本地，只有检查更新时会访问 GitHub。",
    closing_kicker: "下次见",
    closing_title: "下一次弹奏，<br>让它留得久一点。",
    footer_tagline: "独立同人作品，与 HoYoverse 无关。",
    footer_guide: "中文使用说明",
    meta_title: "原神乐器演奏记录工具 · 琴声之后，演奏还在",
    meta_desc: "一款安静的原神乐器演奏记录工具。它听见你弹下的每个音，也记下按键、节拍和那些细小的停顿。"
  },
  "zh-Hant": {
    skip_link: "跳到主要內容",
    menu_label: "開啟選單",
    menu_close: "關閉選單",
    lang_label: "語言",
    nav_about: "關於",
    nav_features: "功能",
    nav_downloads: "下載",
    nav_security: "安全",
    nav_faq: "常見問題",
    nav_cta: "下載",
    hero_kicker: "原神樂器演奏記錄工具 · Windows 1.1.5",
    hero_line1: "琴聲之後，",
    hero_line2: "演奏還在。",
    hero_sub: "它聽見你彈下的每個音，也記下按鍵、節拍和那些細小的停頓。",
    hero_cta: "下載 Windows 版",
    hero_secondary: "看看這次更新",
    hero_note: "免費 · 本機執行 · 無需帳號",
    hero_caption: "懸浮窗 · Windows 1.1.5",
    hero_caption_meta: "琴鍵 / 節拍 / 時間線",
    hero_scroll: "向下",
    about_index: "01 / 關於",
    about_lead: "它不會替你演奏，也不會評價你彈得怎麼樣。<br>只是在旁邊聽著，把聽到的東西安靜地放好。",
    about_body: "琴鍵、節拍、每個音的長度。你可以邊彈邊看，也可以在停下來之後，回頭看看剛才的演奏。",
    features_index: "02 / 演奏的痕跡",
    features_title: "留下的，不只是音符。",
    features_lede: "還有按下與放開，快與慢，和那些沒有寫進譜子的細節。",
    feature1_title: "琴鍵",
    feature1_text: "按下的鍵會亮起來。和弦與調性，也會跟著出現。",
    feature2_title: "節拍",
    feature2_text: "速度在變，線也在走。快一點，慢一點，都留在曲子裡。",
    feature3_title: "時間",
    feature3_text: "每個音從哪裡開始，在哪裡結束。間隔和餘音，都有記錄。",
    timeline_index: "03 / 按鍵時間線",
    timeline_title: "把和弦，攤開來看。",
    timeline_text: "每一條橫線，是一個鍵按住的時間。幾條線並排的時候，就是一個和弦。",
    timeline_li1: "按下和放開，都有準確的時間",
    timeline_li2: "同時按下的音，會並排出現",
    timeline_li3: "悠可琴的和弦鍵、圓號的兩排，也都保留",
    timeline_note: "懸浮窗預設關閉，需要時從頂欄打開。",
    download_index: "04 / 下載",
    download_title: "下次彈琴的時候，<br>它會在。",
    download_lede: "Windows 1.1.5 已準備好。Android 仍是 1.1.1。",
    win_desc: "適用於 Windows 10 和 11（64 位元）。安裝後，從開始功能表打開。",
    win_cta: "下載安裝程式",
    win_portable: "免安裝版",
    win_note: "安裝包沒有程式碼簽章。SmartScreen 可能提示，選擇「更多資訊」後仍可執行。",
    android_desc: "適用於 Android 7.0 及以上。",
    android_cta: "取得 Android 版",
    android_note: "1.1.5 沒有更新 Android。",
    checksum: "校驗和",
    release_notes: "更新說明",
    all_releases: "所有版本",
    security_index: "05 / 隱私",
    security_title: "聲音留在本機。",
    sec1_title: "沒有遙測",
    sec1_text: "音訊不會離開你的電腦。沒有統計、帳號，也沒有雲端處理。",
    sec2_title: "檢查更新有邊界",
    sec2_text: "只有在需要時，才會存取 GitHub Releases；有逾時和大小限制。",
    sec3_title: "安裝前會校驗",
    sec3_text: "自動更新會先核對 SHA256 和檔案標頭，再執行安裝程式。",
    faq_index: "06 / 下載之前",
    faq_title: "可能想先<br>知道這些。",
    faq1_q: "懸浮窗會自動打開嗎？",
    faq1_a: "不會。它預設關閉，可以從頂欄按鈕或設定裡打開。",
    faq2_q: "1.1.5 改了什麼？",
    faq2_a: "修好了匯出，修好了懸浮窗裡 BPM 曲線不顯示的問題；原本的文字指標換成了按鍵時間線。",
    faq3_q: "Android 會更新嗎？",
    faq3_a: "這次不會。Android 仍是 1.1.1。",
    faq4_q: "匯出會得到什麼？",
    faq4_a: "三份 CSV：音符時長、BPM 和排查記錄。匯出後可以直接打開資料夾。",
    faq5_q: "支援哪些樂器？",
    faq5_a: "風物之詩琴、鏡花之琴、躍律琴、諧律鍵琴、晚風圓號和悠可琴。",
    faq6_q: "需要連網嗎？",
    faq6_a: "不需要。偵測和匯出都在本機，只有檢查更新時會存取 GitHub。",
    closing_kicker: "下次見",
    closing_title: "下一次彈奏，<br>讓它留得久一點。",
    footer_tagline: "獨立同人作品，與 HoYoverse 無關。",
    footer_guide: "中文使用說明",
    meta_title: "原神樂器演奏記錄工具 · 琴聲之後，演奏還在",
    meta_desc: "一款安靜的原神樂器演奏記錄工具。它聽見你彈下的每個音，也記下按鍵、節拍和那些細小的停頓。"
  },
  "zh-TW": {
    skip_link: "跳到主要內容",
    menu_label: "開啟選單",
    menu_close: "關閉選單",
    lang_label: "語言",
    nav_about: "關於",
    nav_features: "功能",
    nav_downloads: "下載",
    nav_security: "安全",
    nav_faq: "常見問題",
    nav_cta: "下載",
    hero_kicker: "原神樂器演奏記錄工具 · Windows 1.1.5",
    hero_line1: "琴聲之後，",
    hero_line2: "演奏還在。",
    hero_sub: "它聽見你彈下的每個音，也記下按鍵、節拍和那些細小的停頓。",
    hero_cta: "下載 Windows 版",
    hero_secondary: "看看這次更新",
    hero_note: "免費 · 本機執行 · 無需帳號",
    hero_caption: "懸浮視窗 · Windows 1.1.5",
    hero_caption_meta: "琴鍵 / 節拍 / 時間軸",
    hero_scroll: "向下",
    about_index: "01 / 關於",
    about_lead: "它不會替你演奏，也不會評價你彈得怎麼樣。<br>只是在旁邊聽著，把聽到的東西安靜地放好。",
    about_body: "琴鍵、節拍、每個音的長度。你可以邊彈邊看，也可以在停下來之後，回頭看看剛才的演奏。",
    features_index: "02 / 演奏的痕跡",
    features_title: "留下的，不只是音符。",
    features_lede: "還有按下與放開，快與慢，和那些沒有寫進譜子的細節。",
    feature1_title: "琴鍵",
    feature1_text: "按下的鍵會亮起來。和弦與調性，也會跟著出現。",
    feature2_title: "節拍",
    feature2_text: "速度在變，線也在走。快一點，慢一點，都留在曲子裡。",
    feature3_title: "時間",
    feature3_text: "每個音從哪裡開始，在哪裡結束。間隔和餘音，都有記錄。",
    timeline_index: "03 / 按鍵時間軸",
    timeline_title: "把和弦，攤開來看。",
    timeline_text: "每一條橫線，是一個鍵按住的時間。幾條線並排的時候，就是一個和弦。",
    timeline_li1: "按下和放開，都有準確的時間",
    timeline_li2: "同時按下的音，會並排出現",
    timeline_li3: "悠可琴的和弦鍵、圓號的兩排，也都保留",
    timeline_note: "懸浮視窗預設關閉，需要時從頂欄打開。",
    download_index: "04 / 下載",
    download_title: "下次彈琴的時候，<br>它會在。",
    download_lede: "Windows 1.1.5 已準備好。Android 仍是 1.1.1。",
    win_desc: "適用於 Windows 10 和 11（64 位元）。安裝後，從開始功能表打開。",
    win_cta: "下載安裝程式",
    win_portable: "免安裝版",
    win_note: "安裝包沒有程式碼簽章。SmartScreen 可能提示，選擇「更多資訊」後仍可執行。",
    android_desc: "適用於 Android 7.0 以上。",
    android_cta: "取得 Android 版",
    android_note: "1.1.5 沒有更新 Android。",
    checksum: "校驗和",
    release_notes: "更新說明",
    all_releases: "所有版本",
    security_index: "05 / 隱私",
    security_title: "聲音留在本機。",
    sec1_title: "沒有遙測",
    sec1_text: "音訊不會離開你的電腦。沒有統計、帳號，也沒有雲端處理。",
    sec2_title: "檢查更新有邊界",
    sec2_text: "只有在需要時，才會存取 GitHub Releases；有逾時和大小限制。",
    sec3_title: "安裝前會驗證",
    sec3_text: "自動更新會先核對 SHA256 和檔案標頭，再執行安裝程式。",
    faq_index: "06 / 下載之前",
    faq_title: "可能想先<br>知道這些。",
    faq1_q: "懸浮視窗會自動打開嗎？",
    faq1_a: "不會。它預設關閉，可以從頂欄按鈕或設定裡打開。",
    faq2_q: "1.1.5 改了什麼？",
    faq2_a: "修好了匯出，修好了懸浮視窗裡 BPM 曲線不顯示的問題；原本的文字指標換成了按鍵時間軸。",
    faq3_q: "Android 會更新嗎？",
    faq3_a: "這次不會。Android 仍是 1.1.1。",
    faq4_q: "匯出會得到什麼？",
    faq4_a: "三份 CSV：音符時長、BPM 和排查記錄。匯出後可以直接打開資料夾。",
    faq5_q: "支援哪些樂器？",
    faq5_a: "風物之詩琴、鏡花之琴、躍律琴、諧律鍵琴、晚風圓號和悠可琴。",
    faq6_q: "需要連網嗎？",
    faq6_a: "不需要。偵測和匯出都在本機，只有檢查更新時會存取 GitHub。",
    closing_kicker: "下次見",
    closing_title: "下一次彈奏，<br>讓它留得久一點。",
    footer_tagline: "獨立同人作品，與 HoYoverse 無關。",
    footer_guide: "中文使用說明",
    meta_title: "原神樂器演奏記錄工具 · 琴聲之後，演奏還在",
    meta_desc: "一款安靜的原神樂器演奏記錄工具。它聽見你彈下的每個音，也記下按鍵、節拍和那些細小的停頓。"
  },
  en: {
    skip_link: "Skip to content",
    menu_label: "Open menu",
    menu_close: "Close menu",
    lang_label: "Language",
    nav_about: "About",
    nav_features: "Features",
    nav_downloads: "Download",
    nav_security: "Privacy",
    nav_faq: "FAQ",
    nav_cta: "Download",
    hero_kicker: "A quiet record of Genshin instrument performances · Windows 1.1.5",
    hero_line1: "After the music,",
    hero_line2: "the performance remains.",
    hero_sub: "It listens while you play, and keeps the keys, the tempo, and the small pauses in between.",
    hero_cta: "Download for Windows",
    hero_secondary: "See 1.1.5",
    hero_note: "Free · Runs locally · No account",
    hero_caption: "Floating window · Windows 1.1.5",
    hero_caption_meta: "Keys / tempo / timeline",
    hero_scroll: "Scroll",
    about_index: "01 / About",
    about_lead: "It will not play for you, or judge how you played.<br>It only listens, and quietly keeps what it hears beside you.",
    about_body: "The keys, the tempo, the length of each note. You can watch while you play, or come back to it afterwards.",
    features_index: "02 / Traces",
    features_title: "More than the notes.",
    features_lede: "The press and release, the faster and slower, the details that never make it into the score.",
    feature1_title: "The keys",
    feature1_text: "The keys you press light up. The chord and the key follow.",
    feature2_title: "The tempo",
    feature2_text: "The line moves as the speed changes. Faster, slower, it all stays with the piece.",
    feature3_title: "The time",
    feature3_text: "Where each note begins, where it ends. The gaps and the ring are kept too.",
    timeline_index: "03 / Key timeline",
    timeline_title: "A chord, opened up.",
    timeline_text: "Each line is a key held down. When several lines sit side by side, that is a chord.",
    timeline_li1: "Press and release, both in time",
    timeline_li2: "Notes played together appear side by side",
    timeline_li3: "Ukulele chords and both horn rows are kept",
    timeline_note: "The floating window is off by default. Open it from the toolbar when you want it.",
    download_index: "04 / Download",
    download_title: "For the next time<br>you play.",
    download_lede: "Windows 1.1.5 is ready. Android is still 1.1.1.",
    win_desc: "For Windows 10 and 11, 64 bit. Install it, then open it from the Start Menu.",
    win_cta: "Download installer",
    win_portable: "Portable build",
    win_note: "The installer is not code signed. SmartScreen may ask you to choose More info, then Run anyway.",
    android_desc: "For Android 7.0 and newer.",
    android_cta: "Get Android",
    android_note: "Not updated in 1.1.5.",
    checksum: "Checksums",
    release_notes: "Release notes",
    all_releases: "All releases",
    security_index: "05 / Privacy",
    security_title: "Your sound stays on your computer.",
    sec1_title: "No telemetry",
    sec1_text: "Audio never leaves your computer. There is no analytics, account or cloud processing.",
    sec2_title: "A small update check",
    sec2_text: "The optional check contacts GitHub Releases only. It has a timeout and a size limit.",
    sec3_title: "Checked before install",
    sec3_text: "Automatic updates check the published SHA256 and the file header before running the installer.",
    faq_index: "06 / Before you download",
    faq_title: "A few things<br>you may want to know.",
    faq1_q: "Does the floating window open automatically?",
    faq1_a: "No. It is off by default. You can open it from the toolbar or turn it on in Settings.",
    faq2_q: "What changed in 1.1.5?",
    faq2_a: "Export is fixed, and the BPM curve in the floating window now refreshes. The old text readouts were replaced by the key timeline.",
    faq3_q: "Is Android getting an update?",
    faq3_a: "Not this time. Android stays at 1.1.1; 1.1.5 is for Windows only.",
    faq4_q: "What does export create?",
    faq4_a: "Three CSV files: note lengths, BPM history and the boundary check. When it finishes, you can open the folder directly.",
    faq5_q: "Which instruments are supported?",
    faq5_a: "Windsong Lyre, Floral Zither, Vintage Lyre, Harmonic Keys, Nightwind Horn and Ukulele.",
    faq6_q: "Does it need a connection?",
    faq6_a: "No. Detection and export are local. Only the optional update check visits GitHub.",
    closing_kicker: "Until next time",
    closing_title: "Next time you play,<br>let it stay a little longer.",
    footer_tagline: "An independent fan tool. Not affiliated with HoYoverse.",
    footer_guide: "中文使用说明",
    meta_title: "Genshin Instrument Detector · A quiet record of your performance",
    meta_desc: "A quiet desktop companion for Genshin Impact instruments. It listens while you play and keeps the keys, the tempo and the shape of each note."
  },
  ja: {
    skip_link: "本文へ移動",
    menu_label: "メニューを開く",
    menu_close: "メニューを閉じる",
    lang_label: "言語",
    nav_about: "このツール",
    nav_features: "機能",
    nav_downloads: "ダウンロード",
    nav_security: "プライバシー",
    nav_faq: "よくある質問",
    nav_cta: "ダウンロード",
    hero_kicker: "原神の楽器演奏を記録するツール · Windows 1.1.5",
    hero_line1: "演奏が終わっても、",
    hero_line2: "その演奏は残る。",
    hero_sub: "弾いている音を聴きながら、押した鍵、テンポ、そして小さな間を記録します。",
    hero_cta: "Windows 版をダウンロード",
    hero_secondary: "1.1.5 を見る",
    hero_note: "無料 · ローカル動作 · アカウント不要",
    hero_caption: "フローティングウィンドウ · Windows 1.1.5",
    hero_caption_meta: "鍵盤 / テンポ / タイムライン",
    hero_scroll: "下へ",
    about_index: "01 / このツール",
    about_lead: "代わりに弾くことも、上手い下手を決めることもありません。<br>ただ聴いて、聴こえたものを静かにそばに置いておきます。",
    about_body: "鍵盤、テンポ、ひとつひとつの音の長さ。弾きながら眺めても、弾き終わってから振り返ってもかまいません。",
    features_index: "02 / 演奏の痕跡",
    features_title: "残るのは、音符だけではありません。",
    features_lede: "押して離すこと、速さと遅さ、譜面には残らない細かなところ。",
    feature1_title: "鍵盤",
    feature1_text: "押した鍵が光ります。コードと調性も、それに続いて現れます。",
    feature2_title: "テンポ",
    feature2_text: "速度が変われば、線も動きます。速くても遅くても、曲の中に残ります。",
    feature3_title: "時間",
    feature3_text: "それぞれの音がどこで始まり、どこで終わるのか。間も余韻も記録します。",
    timeline_index: "03 / キー・タイムライン",
    timeline_title: "コードを、広げて見る。",
    timeline_text: "横線は、鍵を押していた時間です。いくつかの線が並ぶとき、それがコードになります。",
    timeline_li1: "押した時刻と離した時刻",
    timeline_li2: "同時に弾いた音は並んで現れる",
    timeline_li3: "ウクレレのコードと、円号の 2 段もそのまま",
    timeline_note: "フローティングは既定で非表示です。必要なときにツールバーから開けます。",
    download_index: "04 / ダウンロード",
    download_title: "次に弾くとき、<br>そばに置いてください。",
    download_lede: "Windows 1.1.5 の準備ができました。Android は 1.1.1 のままです。",
    win_desc: "Windows 10 / 11（64 ビット）用。インストール後、スタートメニューから開けます。",
    win_cta: "インストーラーをダウンロード",
    win_portable: "ポータブル版",
    win_note: "インストーラーはコード署名されていません。SmartScreen が表示された場合は「詳細情報」から実行してください。",
    android_desc: "Android 7.0 以上用。",
    android_cta: "Android 版を入手",
    android_note: "1.1.5 では更新していません。",
    checksum: "チェックサム",
    release_notes: "リリースノート",
    all_releases: "すべてのリリース",
    security_index: "05 / プライバシー",
    security_title: "音は、あなたの PC の中に。",
    sec1_title: "テレメトリーなし",
    sec1_text: "音声が PC の外へ送られることはありません。解析、アカウント、クラウド処理はありません。",
    sec2_title: "更新確認にも境界",
    sec2_text: "必要なときだけ GitHub Releases に問い合わせます。タイムアウトとサイズ上限があります。",
    sec3_title: "インストール前に確認",
    sec3_text: "自動更新は公開された SHA256 とファイルヘッダーを確認してからインストーラーを実行します。",
    faq_index: "06 / ダウンロードの前に",
    faq_title: "先に知っておきたいこと。",
    faq1_q: "フローティングは自動で開きますか？",
    faq1_a: "いいえ。既定ではオフです。ツールバーから開くか、設定で有効にできます。",
    faq2_q: "1.1.5 で何が変わりましたか？",
    faq2_a: "エクスポートを修正し、フローティングの BPM 曲線が更新されるようになりました。以前の文字表示はキー・タイムラインに替わりました。",
    faq3_q: "Android は更新されますか？",
    faq3_a: "今回はありません。Android は 1.1.1 のまま、1.1.5 は Windows のみです。",
    faq4_q: "エクスポートで何が作られますか？",
    faq4_a: "CSV が 3 つ。音符の長さ、BPM の履歴、境界チェックです。完了後にフォルダーを開けます。",
    faq5_q: "対応している楽器は？",
    faq5_a: "風物の詩琴、鏡花の琴、躍律琴、諧律鍵琴、晩風の円号、悠可琴です。",
    faq6_q: "接続は必要ですか？",
    faq6_a: "いいえ。検出とエクスポートはローカルです。任意の更新確認だけが GitHub に接続します。",
    closing_kicker: "また今度",
    closing_title: "次に弾くとき、<br>もう少し長く残るように。",
    footer_tagline: "非公式のファンツールです。HoYoverse とは無関係です。",
    footer_guide: "中文使用说明",
    meta_title: "原神楽器演奏記録ツール · 演奏が終わったあとも",
    meta_desc: "原神の楽器演奏のための静かな記録ツール。弾いている音を聴き、押した鍵、テンポ、音の長さを残します。"
  }
};

const LANG_INFO = {
  "zh-CN": { label: "简体中文", flag: "assets/flags/cn.svg", emoji: "🇨🇳" },
  "zh-Hant": { label: "繁體中文（香港）", flag: "assets/flags/hk.svg", emoji: "🇭🇰" },
  "zh-TW": { label: "正體中文（臺灣）", flag: "assets/flags/tw.svg", emoji: "🇹🇼" },
  en: { label: "English", flag: "assets/flags/us.svg", emoji: "🇺🇸" },
  ja: { label: "日本語", flag: "assets/flags/jp.svg", emoji: "🇯🇵" }
};

let currentLang = "zh-CN";
const langButton = document.getElementById("lang-button");
const langLabel = document.getElementById("lang-label");
const langFlag = document.getElementById("lang-flag");
const langMenu = document.getElementById("lang-menu");
const langPicker = document.getElementById("lang-picker");
const menuToggle = document.getElementById("menu-toggle");
const mobileMenu = document.getElementById("mobile-menu");
const metaDesc = document.querySelector('meta[name="description"]');

function T(key) {
  const dict = I18N[currentLang] || I18N.en;
  return dict[key] !== undefined ? dict[key] : (I18N.en[key] !== undefined ? I18N.en[key] : key);
}

function closeLangMenu() {
  langMenu.classList.remove("open");
  langButton.setAttribute("aria-expanded", "false");
}

function closeMobileMenu() {
  document.body.classList.remove("menu-open");
  mobileMenu.setAttribute("aria-hidden", "true");
  menuToggle.setAttribute("aria-expanded", "false");
  menuToggle.setAttribute("aria-label", T("menu_label"));
}

function openMobileMenu() {
  document.body.classList.add("menu-open");
  mobileMenu.setAttribute("aria-hidden", "false");
  menuToggle.setAttribute("aria-expanded", "true");
  menuToggle.setAttribute("aria-label", T("menu_close"));
}

function applyLanguage(lang) {
  if (!I18N[lang]) lang = "zh-CN";
  currentLang = lang;
  const dict = I18N[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = T(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = T(el.getAttribute("data-i18n-html"));
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", T(el.getAttribute("data-i18n-aria")));
  });
  document.title = dict.meta_title || I18N.en.meta_title;
  if (metaDesc) metaDesc.setAttribute("content", dict.meta_desc || I18N.en.meta_desc);
  const info = LANG_INFO[lang];
  langLabel.textContent = info.label;
  langFlag.src = info.flag;
  langFlag.alt = info.emoji;
  langButton.setAttribute("aria-label", info.emoji + " " + info.label);
  document.querySelectorAll(".lang-option").forEach((el) => {
    el.setAttribute("aria-selected", el.getAttribute("data-lang") === lang ? "true" : "false");
  });
  if (document.body.classList.contains("menu-open")) menuToggle.setAttribute("aria-label", T("menu_close"));
  else menuToggle.setAttribute("aria-label", T("menu_label"));
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
  const browser = (navigator.language || "zh-CN").toLowerCase();
  if (browser.startsWith("ja")) return "ja";
  if (browser === "zh-tw" || browser === "zh-hk" || browser.includes("hant")) return "zh-TW";
  if (browser.startsWith("zh")) return "zh-CN";
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

menuToggle.addEventListener("click", () => {
  if (document.body.classList.contains("menu-open")) closeMobileMenu();
  else openMobileMenu();
});
mobileMenu.querySelectorAll("a").forEach((a) => a.addEventListener("click", closeMobileMenu));

const header = document.getElementById("site-header");
let headerTick = false;
function updateHeader() {
  header.classList.toggle("scrolled", window.scrollY > 12);
  headerTick = false;
}
window.addEventListener("scroll", () => {
  if (!headerTick) {
    headerTick = true;
    requestAnimationFrame(updateHeader);
  }
}, { passive: true });
updateHeader();

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const revealItems = document.querySelectorAll(".reveal");
if (reduceMotion) {
  revealItems.forEach((el) => el.classList.add("in"));
} else {
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in");
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
  revealItems.forEach((el) => revealObserver.observe(el));
}

applyLanguage(initialLanguage());
