import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from multiprocessing import Process

# --- 🛠️ إعدادات التحكم والروابط ---
CONTROL_URL = "https://meja.do.am/asd/url2.txt"

def get_control_data():
    """جلب الرابط وحالة التشغيل (0 أو 1) لكل بث"""
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

def start_stream(stream_id, rtmp_key, width=720, height=1280):
    """وظيفة البث المستقلة لكل محرك"""
    print(f"🎬 تهيئة البث رقم {stream_id}...")
    
    # 1. شاشة وهمية فريدة لكل عملية لتجنب التداخل
    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    os.environ['DISPLAY'] = f":{disp.display}"

    # 2. إعدادات الكروم
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--hide-scrollbars')
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
                status = config['status'] # "1" للتشغيل، "0" للإيقاف

                # حالة الإيقاف
                if status == "0":
                    if is_streaming:
                        print(f"🛑 إيقاف البث {stream_id}...")
                        if ffmpeg_process: ffmpeg_process.terminate()
                        is_streaming = False
                
                # حالة التشغيل أو تغيير الرابط
                else:
                    if not is_streaming or target_url != current_url:
                        print(f"📡 البث {stream_id} -> تحديث الرابط: {target_url}")
                        driver.get(target_url)
                        current_url = target_url
                        
                        if not is_streaming:
                            # سكريبت الهز لمنع السكون
                            driver.execute_script("setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);")
                            
                            ffmpeg_cmd = [
                                'ffmpeg', '-y', '-f', 'x11grab', '-draw_mouse', '0',
                                '-framerate', '60', '-video_size', f'{width}x{height}',
                                '-i', f":{disp.display}",
                                '-f', 'pulse', '-i', 'default',
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                                '-b:v', '3500k', '-pix_fmt', 'yuv420p', '-g', '120',
                                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                                '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
                                '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                            ]
                            if ffmpeg_process: ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(ffmpeg_cmd)
                            is_streaming = True
            
            time.sleep(15) # فحص التحديثات كل 15 ثانية
    except Exception as e:
        print(f"❌ خطأ في البث {stream_id}: {e}")
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    # استدعاء المفاتيح من الـ Secrets بأسماء R1 و R2
    R1 = os.environ.get('R1')
    R2 = os.environ.get('R2')

    if not R1 or not R2:
        print("❌ خطأ: مفاتيح R1 أو R2 غير موجودة في الـ Secrets!")
    else:
        # تشغيل البثين في عمليات متوازية
        p1 = Process(target=start_stream, args=(1, R1))
        p2 = Process(target=start_stream, args=(2, R2))
        
        p1.start()
        p2.start()
        
        p1.join()
        p2.join()
