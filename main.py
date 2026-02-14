import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from multiprocessing import Process

CONTROL_URL = "https://meja.do.am/asd/url2.txt"

def get_control_data():
    try:
        # إضافة t لمنع الكاش وجلب البيانات اللحظية
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
            results = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    results.append({"url": parts[0], "status": parts[1]})
            return results
    except: pass
    return None

def start_stream(stream_id, rtmp_key, sink_name, width=720, height=1280):
    print(f"🟢 بدأ تشغيل مراقب البث {stream_id}")
    
    env_vars = os.environ.copy()
    env_vars['PULSE_SINK'] = sink_name
    env_vars['PULSE_LATENCY_MSEC'] = '20' # قيمة متوازنة لمنع تقطيع الصوت

    disp = Display(visible=0, size=(width, height), backend='xvfb')
    disp.start()
    env_vars['DISPLAY'] = f":{disp.display}"

    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--window-position=0,0')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--kiosk')
    opts.add_argument('--start-fullscreen')
    opts.add_argument('--force-device-scale-factor=1') # لضمان عدم وجود هوامش
    opts.add_argument('--no-first-run')
    opts.add_argument('--no-default-browser-check')
    opts.add_argument('--disable-notifications')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
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
                time.sleep(5)
                continue

            config = controls[stream_id-1]
            target_url = config['url']
            target_status = config['status']

            # حالة الإيقاف (0)
            if target_status == "0":
                if is_streaming:
                    print(f"🛑 إيقاف البث {stream_id} بناءً على طلب التحكم.")
                    if ffmpeg_process:
                        ffmpeg_process.terminate()
                        ffmpeg_process = None
                    driver.get("about:blank")
                    is_streaming = False
                    current_url = ""

            # حالة التشغيل (1)
            elif target_status == "1":
                # لا تشغل البث إلا إذا كان متوقفاً أو الرابط تغير
                if not is_streaming or target_url != current_url:
                    print(f"🔄 تحديث/تشغيل البث {stream_id} على: {target_url}")
                    
                    if ffmpeg_process:
                        ffmpeg_process.terminate()
                        ffmpeg_process = None

                    # تنظيف الجلسة
                    driver.delete_all_cookies()
                    driver.get(target_url)
                    current_url = target_url
                    
                    # انتظار تحميل الموقع وتطبيق التنسيقات
                    time.sleep(6)
                    driver.execute_script("""
                        var style = document.createElement('style');
                        style.innerHTML = 'body { background: black !important; overflow: hidden !important; }';
                        document.head.appendChild(style);
                        setInterval(() => { window.scrollBy(0,1); window.scrollBy(0,-1); }, 50);
                    """)

                    # أمر FFmpeg المطور للاستقرار (Bitrate 3500k لتجنب التقطيع)
                    ffmpeg_cmd = [
                        'ffmpeg', '-y',
                        '-thread_queue_size', '4096',
                        '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '30',
                        '-video_size', f'{width}x{height}', '-i', f":{disp.display}",
                        '-f', 'pulse', '-thread_queue_size', '4096', '-i', f"{sink_name}.monitor",
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                        '-b:v', '3500k', '-maxrate', '3500k', '-bufsize', '7000k',
                        '-pix_fmt', 'yuv420p', '-g', '60',
                        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                        '-af', 'aresample=async=1',
                        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
                    ]
                    
                    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, env=env_vars)
                    is_streaming = True

            time.sleep(10)
    finally:
        if ffmpeg_process: ffmpeg_process.terminate()
        driver.quit()
        disp.stop()

if __name__ == "__main__":
    R1 = os.environ.get('R1')
    R2 = os.environ.get('R2')
    
    if R1 and R2:
        p1 = Process(target=start_stream, args=(1, R1, "Sink1"))
        p2 = Process(target=start_stream, args=(2, R2, "Sink2"))
        p1.start(); p2.start()
        p1.join(); p2.join()
    else:
        print("❌ تأكد من وجود المتغيرات البيئية R1 و R2")
