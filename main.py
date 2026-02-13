import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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
    print(f"🎬 تهيئة البث رقم {stream_id} على القناة الصوتية {sink_name}...")
    
    # إعداد بيئة مستقلة لكل بث لضمان عدم تداخل الصوت أو العرض
    env = os.environ.copy()
    env['PULSE_SINK'] = sink_name  # إجبار الكروم على إخراج الصوت في هذه القناة فقط

    # 1. شاشة وهمية فريدة
    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env['DISPLAY'] = f":{disp.display}"

    # 2. إعدادات الكروم
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--kiosk')
    opts.add_argument(f'--display=:{disp.display}')

    driver = webdriver.Chrome(options=opts)
    ffmpeg_process = None
    current_url = ""
    is_streaming = False

    try:
        while True:
            controls = get_control_data()
            if controls and len(controls) >= stream_id:
                config = controls[stream_id-1]
                target_url = config['url']
                status = config['status']

                if status == "0":
                    if is_streaming:
                        print(f"🛑 إيقاف البث {stream_id}...")
                        if ffmpeg_process: ffmpeg_process.terminate()
                        is_streaming = False
                else:
                    if not is_streaming or target_url != current_url:
                        print(f"📡 البث {stream_id} -> تحديث: {target_url}")
                        driver.get(target_url)
                        current_url = target_url
                        
                        if not is_streaming:
                            driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")
                            
                            # FFmpeg يسحب الصوت من القناة المخصصة (sink_name.monitor)
                            ffmpeg_cmd = [
                                'ffmpeg', '-y', '-f', 'x11grab', '-draw_mouse', '0',
                                '-framerate', '60', '-video_size', f'{width}x{height}',
                                '-i', f":{disp.display}",
                                '-f', 'pulse', '-i', f"{sink_name}.monitor", # مصدر الصوت المستقل
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                                '-b:v', '3500k', '-pix_fmt', 'yuv420p', '-g', '120',
                                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                                '-af', 'aresample=async=1',
                                '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env)
                            is_streaming = True
            
            time.sleep(15)
    except Exception as e:
        print(f"❌ خطأ في البث {stream_id}: {e}")
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    R1 = os.environ.get('R1')
    R2 = os.environ.get('R2')

    if not R1 or not R2:
        print("❌ خطأ في المفاتيح R1 أو R2!")
    else:
        # تمرير اسم القناة الصوتية (Sink) لكل عملية
        p1 = Process(target=start_stream, args=(1, R1, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2, "Sink2"))
        
        p1.start()
        p2.start()
        
        p1.join()
        p2.join()
