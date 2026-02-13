import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- 🛠️ إعدادات التحكم والروابط ---
CONTROL_URL = "https://meja.do.am/asd/url2.txt" # رابط التحكم الخاص بك
DEFAULT_URL = "https://meja.do.am/asd/obs1.html"

def get_live_url():
    try:
        # إضافة t لمنع الكاش وجلب الرابط اللحظي
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            link = response.text.strip()
            if link.startswith("http"): return link
    except: pass
    return None

# 1. تشغيل الشاشة الوهمية (مقاس عمودي 720x1280)
# لو عايز أفقر غير المقاس لـ 1280x720
WIDTH, HEIGHT = 720, 1280 
disp = Display(visible=0, size=(WIDTH, HEIGHT), backend='xvfb')
disp.start()
os.environ['DISPLAY'] = ":" + str(disp.display)

# 2. إعدادات الكروم الاحترافية
opts = Options()
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--disable-gpu')
opts.add_argument(f'--window-size={WIDTH},{HEIGHT}')
opts.add_argument('--autoplay-policy=no-user-gesture-required')
opts.add_argument('--hide-scrollbars')
# وضع الكشك لإخفاء شريط العنوان تماماً
opts.add_argument('--kiosk') 
# إعدادات كسر السواد وإجبار الرندر
opts.add_argument('--disable-features=CalculateNativeWinOcclusion')
opts.add_argument('--force-color-profile=srgb')

driver = webdriver.Chrome(options=opts)

# الدخول للموقع
current_url = get_live_url() or DEFAULT_URL
driver.get(current_url)

print("🌐 الموقع فتح.. تشغيل محرك الهز لمنع السكون...")
time.sleep(20)

# 🚀 سكريبت الهز الذكي لضمان استمرار الرندر والصوت
driver.execute_script("""
    setInterval(() => {
        window.scrollBy(0, 1);
        window.scrollBy(0, -1);
    }, 50);
""")

RTMP_KEY = os.environ.get('RTMP_KEY')

# 3. محرك البث (FFmpeg) مع ضبط التزامن (Sync)
# الإضافات الجديدة: -use_wallclock_as_timestamps و -af aresample
ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-thread_queue_size', '4096', # رفعنا الكيوي لامتصاص ضغط البيانات
    '-f', 'x11grab', 
    '-draw_mouse', '0',
    '-framerate', '60', 
    '-video_size', f'{WIDTH}x{HEIGHT}', 
    '-i', os.environ['DISPLAY'],
    
    '-f', 'pulse', 
    '-thread_queue_size', '4096',
    '-i', 'default',
    
    '-c:v', 'libx264', 
    '-preset', 'ultrafast', 
    '-tune', 'zerolatency', 
    '-b:v', '5000k', 
    '-maxrate', '5000k', 
    '-bufsize', '10000k',
    '-pix_fmt', 'yuv420p', 
    '-g', '120', 
    
    '-c:a', 'aac', 
    '-b:a', '128k', 
    '-ar', '44100',
    # أهم أمر للمزامنة: يجبر الصوت على اللحاق بالصورة إذا حدث تأخير
    '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
    
    '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{RTMP_KEY}"
]

print(f"📡 بدأ البث المباشر (وضع ملئ الشاشة + تزامن صوتي)...")
process = subprocess.Popen(ffmpeg_cmd)

try:
    while True:
        # فحص الرابط من موقعك كل 10 ثوانٍ للتحكم الفوري
        new_url = get_live_url()
        if new_url and new_url != current_url:
            print(f"🔄 تغيير الرابط فورياً إلى: {new_url}")
            driver.get(new_url)
            current_url = new_url
        
        time.sleep(10)
except KeyboardInterrupt:
    print("🛑 إيقاف...")
finally:
    process.terminate()
    driver.quit()
    disp.stop()
