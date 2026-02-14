import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from multiprocessing import Process

# --- 🛠️ إعدادات التحكم ---
CONTROL_URL = "https://meja.do.am/asd/url2.txt"

def get_control_data():
    """جلب وتنظيف البيانات من الملف لمنع التكرار بسبب المسافات"""
    try:
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            # تنظيف الأسطر من أي مسافات زائدة
            lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
            results = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    results.append({"url": parts[0].strip(), "status": parts[1].strip()})
            return results
    except: pass
    return None

def apply_custom_changes(driver):
    """حقن التنسيقات وإخفاء العناصر غير المرغوبة"""
    try:
        script = """
        var style = document.createElement('style');
        style.innerHTML = `
            body { background-color: #000 !important; overflow: hidden !important; }
            #header, .ads-layer { display: none !important; }
        `;
        document.head.appendChild(style);
        """
        driver.execute_script(script)
    except: pass

def clear_browser_data(driver):
    """مسح شامل للبيانات لبدء جلسة نظيفة"""
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
    except: pass

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"🟢 بدأ مراقب البث {stream_id} (نظام الحماية نشط)")
    
    # إعدادات الصوت والبيئة
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name
    env_vars['PULSE_LATENCY_MSEC'] = '20'

    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--window-position=0,0')
    opts.add_argument('--kiosk')
    opts.add_argument('--start-fullscreen')
    opts.add_argument('--force-device-scale-factor=1')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--incognito')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=opts)

    ffmpeg_process = None
    current_url = ""
    is_streaming = False

    try:
        while True:
            controls = get_control_data()
            if not controls or len(controls) < stream_id:
                time.sleep(10)
                continue

            config = controls[stream_id-1]
            target_url = config['url']
            target_status = config['status']

            # --- حالة الإيقاف (0) ---
            if target_status == "0":
                if is_streaming:
                    print(f"🛑 إيقاف البث {stream_id}...")
                    if ffmpeg_process:
                        ffmpeg_process.terminate()
                        ffmpeg_process = None
                    try: driver.get("about:blank")
                    except: pass
                    is_streaming = False
                    current_url = ""

            # --- حالة التشغيل (1) ---
            elif target_status == "1":
                # فحص صحة الرابط (يجب أن يبدأ بـ http)
                if not target_url.lower().startswith("http"):
                    print(f"⚠️ تجاهل رابط غير صالح: {target_url}")
                    time.sleep(10)
                    continue

                if not is_streaming or target_url != current_url:
                    print(f"🚀 محاولة تشغيل/تحديث البث {stream_id}...")
                    
                    try:
                        if ffmpeg_process:
                            ffmpeg_process.terminate()
                            ffmpeg_process = None

                        # التنظيف والفتح مع حماية من الأخطاء
                        clear_browser_data(driver)
                        driver.get(target_url) 
                        
                        current_url = target_url # تحديث الرابط فوراً لمنع التكرار
                        time.sleep(6) 
                        
                        apply_custom_changes(driver)
                        driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")

                        # أمر FFmpeg المتزن (30 فريم لمنع التقطيع)
                        ffmpeg_cmd = [
                            'ffmpeg', '-y', '-thread_queue_size', '4096',
                            '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '30',
                            '-video_size', f'{width}x{height}', '-i', f":{disp.display}",
                            '-f', 'pulse', '-thread_queue_size', '4096', '-i', f"{sink_name}.monitor",
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                            '-b:v', '3500k', '-maxrate', '3500k', '-bufsize', '7000k',
                            '-pix_fmt', 'yuv420p', '-g', '60',
                            '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                            '-af', 'aresample=async=1', '-vsync', '1',
                            '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                        ]
                        
                        ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                        is_streaming = True
                        
                    except Exception as e:
                        print(f"❌ فشل فتح الرابط بسبب خطأ في العنوان: {e}")
                        is_streaming = False
                        current_url = "" # إعادة التصفير للمحاولة مرة أخرى

            time.sleep(10)
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    R1, R2 = os.environ.get('R1'), os.environ.get('R2')
    if R1 and R2:
        p1 = Process(target=start_stream, args=(1, R1, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2, "Sink2"))
        p1.start(); p2.start()
        p1.join(); p2.join()
    else:
        print("❌ تأكد من ضبط R1 و R2 في البيئة.")
