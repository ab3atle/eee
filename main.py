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
    """
    هذه الوظيفة تقوم بتنفيذ أي تغييرات تريدها على تصميم الموقع
    بمجرد تحميل الصفحة.
    """
    try:
        # كود JavaScript لتعديل التنسيقات (CSS)
        # مثال: تغيير خلفية الصفحة وإخفاء عناصر معينة
        script = """
        var style = document.createElement('style');
        style.innerHTML = `
            /* ضع هنا أي تنسيقات CSS تريدها */
            body { 
                background-color: black !important; 
            }
            /* مثال لإخفاء إعلانات أو أزرار غير مرغوبة */
            .ads-container, #footer-id { 
                display: none !important; 
            }
        `;
        document.head.appendChild(style);
        
        // يمكنك أيضاً تنفيذ أوامر JS أخرى هنا
        console.log('Custom styles applied!');
        """
        driver.execute_script(script)
    except Exception as e:
        print(f"⚠️ فشل تطبيق التنسيقات: {e}")

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"📡 انطلاق البث {stream_id} - نظام عدم الحفظ والتنسيق المخصص")
    
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
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--kiosk')
    
    # --- 🔒 إعدادات منع حفظ البيانات ---
    opts.add_argument('--incognito') # تفعيل وضع التخفي
    opts.add_argument('--disable-cache') # تعطيل الكاش
    opts.add_argument('--disk-cache-size=1') # جعل حجم الكاش أصغر ما يمكن
    opts.add_argument('--media-cache-size=1')
    
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

                if status == "0":
                    if is_streaming:
                        if ffmpeg_process: ffmpeg_process.terminate()
                        is_streaming = False
                else:
                    # إذا تغير الرابط أو بدأت عملية بث جديدة
                    if not is_streaming or target_url != current_url:
                        # حذف الكوكيز قبل الدخول للرابط لضمان "نظافة" الجلسة
                        driver.delete_all_cookies() 
                        
                        driver.get(target_url)
                        current_url = target_url
                        
                        # --- 🎨 تطبيق التغييرات فور التحميل ---
                        time.sleep(2) # انتظار بسيط للتأكد من تحميل الـ DOM
                        apply_custom_changes(driver)
                        
                        if not is_streaming:
                            driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")
                            
                            ffmpeg_cmd = [
                                'ffmpeg', '-y',
                                '-fflags', 'nobuffer+genpts',
                                '-thread_queue_size', '8192',
                                '-f', 'x11grab',
                                '-draw_mouse', '0',
                                '-framerate', '60',
                                '-video_size', f'{width}x{height}',
                                '-i', f":{disp.display}",
                                '-f', 'pulse', 
                                '-thread_queue_size', '8192',
                                '-i', f"{sink_name}.monitor",
                                '-c:v', 'libx264',
                                '-preset', 'ultrafast',
                                '-tune', 'zerolatency',
                                '-r', '60',
                                '-g', '120',
                                '-b:v', '4000k',
                                '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac',
                                '-b:a', '128k',
                                '-ar', '44100',
                                '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
                                '-vsync', '1',
                                '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                            is_streaming = True
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
