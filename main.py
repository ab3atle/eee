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
    """جلب الرابط وحالة التشغيل من ملف التكست"""
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
    except:
        pass
    return None

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    """دالة تشغيل البث الواحد مع عزل كامل للصوت والعرض"""
    print(f"🎬 بدء البث {stream_id} - القناة الصوتية: {sink_name}")
    
    # إعداد متغيرات البيئة لهذه العملية فقط
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name  # إجبار المتصفح على هذه القناة

    # 1. شاشة وهمية فريدة لكل بث
    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    # 2. إعدادات الكروم
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--kiosk')

    # تمرير متغيرات البيئة للكروم لضمان عزل الصوت
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
                target_url = config['url']
                status = config['status'] # "1" تشغيل، "0" إيقاف

                if status == "0":
                    if is_streaming:
                        print(f"🛑 إيقاف البث {stream_id} بناءً على التحكم")
                        if ffmpeg_process: ffmpeg_process.terminate()
                        is_streaming = False
                else:
                    if not is_streaming or target_url != current_url:
                        print(f"📡 البث {stream_id} -> تحديث الرابط: {target_url}")
                        driver.get(target_url)
                        current_url = target_url
                        
                        if not is_streaming:
                            # سكريبت الهز لمنع السكون
                            driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")
                            
                            # أمر FFmpeg لسحب الصوت من القناة المخصصة فقط
                            ffmpeg_cmd = [
                                'ffmpeg', '-y',
                                '-f', 'x11grab', '-draw_mouse', '0',
                                '-framerate', '30', # خفض الفريمات لـ 30 لضمان استقرار المعالج
                                '-video_size', f'{width}x{height}',
                                '-i', f":{disp.display}",
                                '-f', 'pulse', '-i', f"{sink_name}.monitor", # مراقبة القناة المخصصة فقط
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-b:v', '2500k',
                                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                                '-af', 'aresample=async=1',
                                '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                            is_streaming = True

            time.sleep(15) # الفحص كل 15 ثانية
    except Exception as e:
        print(f"❌ حدث خطأ في البث {stream_id}: {e}")
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    # استلام مفاتيح البث من الـ Environment Variables
    R1_KEY = os.environ.get('R1')
    R2_KEY = os.environ.get('R2')

    if not R1_KEY or not R2_KEY:
        print("⚠️ خطأ: تأكد من إضافة R1 و R2 في GitHub Secrets")
    else:
        # تشغيل عمليتين متوازيتين (كل بث في قناة صوتية وعرض مستقلة)
        p1 = Process(target=start_stream, args=(1, R1_KEY, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2_KEY, "Sink2"))
        
        p1.start()
        p2.start()
        
        p1.join()
        p2.join()
