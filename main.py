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
    """جلب البيانات مع تنظيفها من الفراغات لمنع إعادة التحميل العشوائي"""
    try:
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            results = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    # استخدام .strip() هنا هو السر في استقرار البث
                    results.append({
                        "url": parts[0].strip(), 
                        "status": parts[1].strip()
                    })
            return results
    except Exception as e:
        print(f"⚠️ خطأ في جلب البيانات: {e}")
    return None

def apply_custom_changes(driver):
    """حقن التنسيقات وإخفاء العناصر غير المرغوبة"""
    try:
        script = """
        var style = document.createElement('style');
        style.innerHTML = `
            /* منع ظهور شريط التمرير وتغيير الخلفية */
            body { 
                background-color: #000 !important; 
                overflow: hidden !important; 
            }
            /* يمكنك إضافة كود لإخفاء عناصر محددة هنا */
            #header, .ads-layer { display: none !important; }
        `;
        document.head.appendChild(style);
        """
        driver.execute_script(script)
    except: pass

def clear_browser_data(driver):
    """مسح شامل للبيانات ليبدأ الموقع كأول مرة"""
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        print("🧹 تم تصفير بيانات المتصفح بنجاح.")
    except: pass

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"📡 بدأ مراقب البث رقم {stream_id}")
    
    # إعدادات الصوت والبيئة
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name
    env_vars['PULSE_LATENCY_MSEC'] = '1'

    # شاشة وهمية مطابقة للمقاس المطلوب
    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--window-position=0,0') # التأكد من محاذاة النافذة للصفر
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--kiosk') # وضع ملء الشاشة القسري
    
    # إعدادات الخصوصية ومنع ظهور شريط التحكم
    opts.add_argument('--incognito')
    opts.add_argument('--disable-cache')
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

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

                # الحالة 0: إيقاف تام وتنظيف
                if status == "0":
                    if is_streaming:
                        print(f"⏹️ إيقاف البث {stream_id}...")
                        if ffmpeg_process: ffmpeg_process.terminate()
                        driver.get("about:blank")
                        is_streaming = False
                        current_url = "" # تصفير الرابط لضمان التنظيف عند العودة

                # الحالة 1: تشغيل مع تنظيف البيانات
                elif status == "1":
                    if not is_streaming or target_url != current_url:
                        print(f"🚀 تشغيل نظيف للبث {stream_id} على الرابط: {target_url}")
                        
                        # التنظيف العميق قبل تحميل الصفحة
                        driver.get(target_url)
                        clear_browser_data(driver)
                        driver.refresh()
                        
                        current_url = target_url # تحديث الرابط فوراً لمنع التكرار
                        
                        time.sleep(5) # انتظار التحميل
                        apply_custom_changes(driver)
                        driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")

                        if not is_streaming:
                            ffmpeg_cmd = [
                                'ffmpeg', '-y', '-fflags', 'nobuffer+genpts',
                                '-thread_queue_size', '8192',
                                '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '60',
                                '-video_size', f'{width}x{height}', '-i', f":{disp.display}",
                                '-f', 'pulse', '-thread_queue_size', '8192', '-i', f"{sink_name}.monitor",
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                                '-r', '60', '-g', '120', '-b:v', '4500k', '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                                '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
                                '-vsync', '1', '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                            is_streaming = True

            time.sleep(10) # فحص ملف التحكم كل 10 ثوانٍ
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    # تأكد من تعيين R1 و R2 في بيئة العمل (Environment Variables)
    R1 = os.environ.get('R1')
    R2 = os.environ.get('R2')
    
    if R1 and R2:
        p1 = Process(target=start_stream, args=(1, R1, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2, "Sink2"))
        p1.start()
        p2.start()
        p1.join()
        p2.join()
    else:
        print("❌ خطأ: لم يتم العثور على مفاتيح البث R1 أو R2 في المتغيرات.")
