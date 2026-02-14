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
    try:
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
            results = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    results.append({"url": parts[0].strip(), "status": parts[1].strip()})
            return results
    except: pass
    return None

def get_driver_options(width, height):
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--window-position=0,0')
    opts.add_argument('--kiosk')
    opts.add_argument('--force-device-scale-factor=1')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--incognito')
    opts.add_argument('--disable-cache')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    return opts

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"🟢 مراقب البث {stream_id} نشط الآن...")
    
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name
    env_vars['PULSE_LATENCY_MSEC'] = '20'

    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    driver = None
    ffmpeg_process = None
    current_url = ""

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
                if ffmpeg_process:
                    print(f"🛑 إغلاق البث {stream_id}")
                    ffmpeg_process.terminate()
                    ffmpeg_process = None
                if driver:
                    driver.quit()
                    driver = None
                current_url = ""

            # --- حالة التشغيل (1) ---
            elif target_status == "1":
                if not target_url.lower().startswith("http"):
                    time.sleep(10)
                    continue

                # تشغيل المتصفح إذا لم يكن يعمل
                if driver is None:
                    driver = webdriver.Chrome(options=get_driver_options(width, height))

                # إذا تغير الرابط: نقوم بالتبديل السلس
                if target_url != current_url:
                    print(f"🔄 جاري تحميل: {target_url} (البث لن ينقطع)")
                    
                    try:
                        # حذف البيانات قبل التحميل
                        driver.delete_all_cookies()
                        
                        # تحميل الرابط الجديد مباشرة دون مسح الصفحة يدوياً (لتجنب الشاشة السوداء)
                        driver.get(target_url)
                        current_url = target_url
                        
                        # انتظار كافٍ للتحميل (زدنا المدة لضمان ظهور الموقع)
                        time.sleep(10) 
                        
                        # تطبيق التنسيقات بعد التحميل
                        driver.execute_script("""
                            var style = document.createElement('style');
                            style.innerHTML = 'body { background: black !important; overflow: hidden !important; }';
                            document.head.appendChild(style);
                            // محرك الحركة لمنع السكون
                            if(!window.moveInterval){
                                window.moveInterval = setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);
                            }
                        """)
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء تحميل الصفحة: {e}")

                # تشغيل البث إذا لم يكن يعمل (أو إذا تعثر سابقاً)
                if ffmpeg_process is None:
                    print(f"📡 فتح اتصال RTMP للبث {stream_id}")
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

            time.sleep(10)
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        if driver: driver.quit()
        disp.stop()

if __name__ == "__main__":
    R1, R2 = os.environ.get('R1'), os.environ.get('R2')
    if R1 and R2:
        p1 = Process(target=start_stream, args=(1, R1, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2, "Sink2"))
        p1.start(); p2.start()
        p1.join(); p2.join()
