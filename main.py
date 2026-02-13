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

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"📡 بدء البث {stream_id} - قناة: {sink_name}")
    
    # إعداد البيئة الصوتية والعرض
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name

    # شاشة وهمية برقم فريد لكل بث لضمان عدم التداخل
    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    # إعدادات الكروم الاحترافية + إزالة شريط التحكم الآلي
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--kiosk')
    opts.add_argument('--force-color-profile=srgb')
    
    # --- إزالة إشعار "Chrome is being controlled" ---
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
                    if not is_streaming or target_url != current_url:
                        driver.get(target_url)
                        current_url = target_url
                        if not is_streaming:
                            driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")
                            
                            # --- نظام المزامنة الخاص بك (من الكود المرجعي) ---
                            ffmpeg_cmd = [
                                'ffmpeg', '-y',
                                '-thread_queue_size', '4096',
                                '-f', 'x11grab',
                                '-draw_mouse', '0',
                                '-framerate', '60',
                                '-video_size', f'{width}x{height}',
                                '-i', f":{disp.display}",
                                
                                '-f', 'pulse', 
                                '-thread_queue_size', '4096',
                                '-i', f"{sink_name}.monitor", # السحب من القناة المعزولة
                                
                                '-c:v', 'libx264',
                                '-preset', 'ultrafast',
                                '-tune', 'zerolatency',
                                '-b:v', '4000k', # معدل البث المطلوب
                                '-maxrate', '4000k',
                                '-bufsize', '8000k',
                                '-pix_fmt', 'yuv420p',
                                '-g', '120',
                                
                                '-c:a', 'aac',
                                '-b:a', '128k',
                                '-ar', '44100',
                                # فلتر المزامنة الأصلي الخاص بك
                                '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
                                
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
