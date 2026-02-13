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
            lines = response.text.strip().split('\n')
            results = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    results.append({"url": parts[0], "status": parts[1]})
            return results
    except: pass
    return None

def apply_custom_changes(driver):
    """حقن التنسيقات المخصصة فور تحميل الصفحة"""
    try:
        script = """
        var style = document.createElement('style');
        style.innerHTML = `
            body { background-color: #000 !important; }
            /* أضف أي تنسيقات CSS إضافية هنا */
        `;
        document.head.appendChild(style);
        console.log('Applied custom styles and reset scripts.');
        """
        driver.execute_script(script)
    except: pass

def clear_browser_data(driver):
    """تنظيف شامل للكوكيز، التخزين المحلي، وجلسة العمل"""
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        print("🧹 تم مسح جميع البيانات القديمة بنجاح.")
    except Exception as e:
        print(f"⚠️ خطأ أثناء التنظيف: {e}")

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"📡 مراقب البث {stream_id} يعمل الآن...")
    
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name
    env_vars['PULSE_LATENCY_MSEC'] = '1'

    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--incognito') # وضع التخفي
    opts.add_argument('--disable-cache')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(env=env_vars)
    driver = webdriver.Chrome(service=service, options=opts)

    ffmpeg_process = None
    current_url = ""
    is_streaming = False

    try:
        while True:
            controls = get_control_data()
            if controls and len(controls) >= stream_id:
                config = controls[stream_id-1]
                target_url, status = config['url'], config['status']

                # حالة الإيقاف (0)
                if status == "0":
                    if is_streaming:
                        print(f"⏹️ تم إيقاف البث {stream_id} من التحكم.")
                        if ffmpeg_process: ffmpeg_process.terminate()
                        driver.get("about:blank") # العودة لصفحة فارغة لتوفير الموارد
                        is_streaming = False
                        current_url = "" # تصفير الرابط لضمان إعادة التحميل عند العودة للعمل

                # حالة التشغيل (1)
                elif status == "1":
                    # إذا كان البث متوقفاً أو تغير الرابط، نبدأ عملية "البداية النظيفة"
                    if not is_streaming or target_url != current_url:
                        print(f"🚀 بدء/إعادة تشغيل البث {stream_id}...")
                        
                        # 1. التنظيف العميق قبل تحميل الصفحة
                        driver.get(target_url) 
                        clear_browser_data(driver)
                        driver.refresh() # إعادة تحميل لضمان تطبيق التنظيف
                        
                        # 2. تطبيق التنسيقات بعد التحميل
                        time.sleep(3) 
                        apply_custom_changes(driver)
                        
                        # 3. تشغيل FFmpeg إذا لم يكن يعمل
                        if not is_streaming:
                            ffmpeg_cmd = [
                                'ffmpeg', '-y', '-fflags', 'nobuffer+genpts',
                                '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '60',
                                '-video_size', f'{width}x{height}', '-i', f":{disp.display}",
                                '-f', 'pulse', '-i', f"{sink_name}.monitor",
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                                '-b:v', '4000k', '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                                '-af', 'aresample=async=1', '-vsync', '1',
                                '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                            is_streaming = True
                            current_url = target_url

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
