import os
import subprocess
import time
import requests
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- 🛠️ إعدادات التحكم والروابط ---
CONTROL_URL = "https://meja.do.am/asd/url2.txt" 
DEFAULT_URL = "https://meja.do.am/asd/obs1.html"

def get_control_content():
    try:
        # جلب محتوى الملف بالكامل (سواء كان رابط أو أوامر)
        response = requests.get(f"{CONTROL_URL}?t={int(time.time())}", timeout=5)
        if response.status_code == 200:
            return response.text.strip()
    except: pass
    return None

# 1. تشغيل الشاشة الوهمية
WIDTH, HEIGHT = 720, 1280 
disp = Display(visible=0, size=(WIDTH, HEIGHT), backend='xvfb')
disp.start()
os.environ['DISPLAY'] = ":" + str(disp.display)

# 2. إعدادات الكروم
opts = Options()
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--disable-gpu')
opts.add_argument(f'--window-size={WIDTH},{HEIGHT}')
opts.add_argument('--autoplay-policy=no-user-gesture-required')
opts.add_argument('--hide-scrollbars')
opts.add_argument('--kiosk') 
opts.add_argument('--disable-features=CalculateNativeWinOcclusion')
opts.add_argument('--force-color-profile=srgb')

driver = webdriver.Chrome(options=opts)

# الدخول المبدئي
initial_content = get_control_content()
current_url = initial_content if (initial_content and initial_content.startswith("http")) else DEFAULT_URL
driver.get(current_url)
last_content = initial_content

print("🌐 اللعبة تعمل.. نظام التحديث الحي نشط...")

# سكريبت الهز لمنع السكون
driver.execute_script("""
    setInterval(() => {
        window.scrollBy(0, 1);
        window.scrollBy(0, -1);
    }, 50);
""")

RTMP_KEY = os.environ.get('RTMP_KEY')

# 3. محرك البث (FFmpeg)
ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-thread_queue_size', '4096',
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
    '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0',
    '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{RTMP_KEY}"
]

process = subprocess.Popen(ffmpeg_cmd)

# --- 🚀 وظائف التحديث الحي (بدون ريفريش) ---

def hot_reload_assets():
    """تحديث ملفات CSS و JS الخارجية بدون إعادة تحميل الصفحة"""
    script = """
    // تحديث ملفات CSS
    var links = document.getElementsByTagName('link');
    for (var i = 0; i < links.length; i++) {
        if (links[i].rel === 'stylesheet') {
            var href = links[i].href.split('?')[0];
            links[i].href = href + '?v=' + new Date().getTime();
        }
    }
    // يمكن إضافة تحديث للصور أو العناصر هنا
    console.log('Assets Hot-Reloaded');
    """
    driver.execute_script(script)

def inject_custom_style(css_code):
    """حقن كود CSS مخصص مباشرة"""
    script = f"""
    var style = document.createElement('style');
    style.innerHTML = `{css_code}`;
    document.head.appendChild(style);
    """
    driver.execute_script(script)

try:
    while True:
        new_content = get_control_content()
        
        if new_content and new_content != last_content:
            # 1. إذا كان المحتوى عبارة عن رابط جديد تماماً (مختلف عن الحالي)
            if new_content.startswith("http") and new_content != current_url:
                print(f"🔄 تغيير الرابط بالكامل: {new_content}")
                driver.get(new_content)
                current_url = new_content
            
            # 2. إذا كتبت كلمة "RELOAD" في الملف
            elif new_content == "RELOAD":
                print("♻️ تحديث ملفات التنسيق (Hot Reload)...")
                hot_reload_assets()
            
            # 3. إذا كتبت "CSS:" متبوعة بكود تنسيق
            elif new_content.startswith("CSS:"):
                css = new_content.replace("CSS:", "")
                print("🎨 حقن تنسيق CSS جديد...")
                inject_custom_style(css)
            
            # تحديث الذاكرة لعدم تكرار الأمر
            last_content = new_content
            
        time.sleep(10)

except KeyboardInterrupt:
    print("🛑 إيقاف...")
finally:
    process.terminate()
    driver.quit()
    disp.stop()
