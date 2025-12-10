import os
import subprocess
import json
import shutil
import threading
import time
from functools import wraps
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = 'seaside_secret_key'

# ================= 配置区 =================
BASE_DIR = "/data"
CONFIG_FILE = os.path.join(BASE_DIR, '.tracker_config.json')

# 从环境变量获取，如果没有设置，则使用默认值
# 这样别人在使用 Docker 部署时，可以通过 -e 参数修改密码
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin') 
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'adminadmin') 
SECRET_KEY = os.environ.get('SECRET_KEY', 'default_insecure_key') # 建议修改

app = Flask(__name__)
app.secret_key = SECRET_KEY
# ==========================================

task_store = {}

def load_default_tracker():
    default_url = "http://udp.opentrackr.org:1337/announce"
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get('tracker_url', default_url)
    except Exception:
        pass
    return default_url

def save_default_tracker(url):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'tracker_url': url}, f)
    except Exception as e:
        print(f"保存配置失败: {e}")

def find_largest_file(start_path):
    if os.path.isfile(start_path):
        return start_path
    largest_file = None
    max_size = 0
    for root, dirs, files in os.walk(start_path):
        for f in files:
            file_path = os.path.join(root, f)
            if 'torrent' in root.split(os.sep): continue
            try:
                size = os.path.getsize(file_path)
                if size > max_size and size > 50 * 1024 * 1024:
                    max_size = size
                    largest_file = file_path
            except OSError:
                continue
    return largest_file

def get_video_duration(video_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        val = result.stdout.strip()
        return float(val) if val else 0
    except: return 0

def generate_thumbnail_optimized(video_path, output_img_path):
    temp_dir = "/tmp/temp_thumbs_processing"
    try:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        duration = get_video_duration(video_path)
        if duration < 10: return "视频时长过短 (<10s)"

        # 制作黑底图备用
        blank_img = os.path.join(temp_dir, "blank.jpg")
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x180", "-frames:v", "1", "-y", blank_img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        interval = duration / 16
        for i in range(16):
            timestamp = (i * interval) + (interval / 2)
            img_name = f"img_{i:02d}.jpg"
            img_path = os.path.join(temp_dir, img_name)
            cmd_extract = ["ffmpeg", "-ss", str(timestamp), "-y", "-i", video_path, "-frames:v", "1", "-q:v", "5", "-vf", "scale=320:-1", img_path]
            subprocess.run(cmd_extract, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                shutil.copy(blank_img, img_path)

        cmd_tile = ["ffmpeg", "-y", "-i", os.path.join(temp_dir, "img_%02d.jpg"), "-vf", "tile=4x4:padding=5:color=white", output_img_path]
        result = subprocess.run(cmd_tile, capture_output=True, text=True)
        
        if result.returncode != 0: return f"FFmpeg 拼图失败: {result.stderr[-200:]}"
        if not os.path.exists(output_img_path) or os.path.getsize(output_img_path) == 0: return "未生成图片文件"

        return "success"
    except Exception as e:
        return f"Python 异常: {str(e)}"
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

def background_process(tracker_url, is_private, comment, piece_size, full_source_path, output_folder, task_id):
    task_store[task_id] = {'status': 'running', 'msg': '初始化...', 'files': {}}
    
    try:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        if os.path.isdir(full_source_path):
            base_name = os.path.basename(full_source_path.rstrip('/'))
        else:
            base_name = os.path.basename(full_source_path)

        f_torrent = os.path.join(output_folder, f"{base_name}.torrent")
        f_info = os.path.join(output_folder, f"{base_name}_MediaInfo.txt")
        f_thumb = os.path.join(output_folder, f"{base_name}_Thumb.jpg")

        # === 核心修改：强制删除旧文件，实现“静默覆盖” ===
        if os.path.exists(f_torrent): 
            try: os.remove(f_torrent)
            except: pass
        if os.path.exists(f_info):
            try: os.remove(f_info)
            except: pass
        if os.path.exists(f_thumb):
            try: os.remove(f_thumb)
            except: pass

        # 1. 种子
        task_store[task_id]['msg'] = '正在生成种子...'
        cmd = ["mktorrent", "-v", "-l", piece_size, "-a", tracker_url]
        if is_private: cmd.append("-p")
        if comment: cmd.extend(["-c", comment])
        cmd.extend(["-o", f_torrent])
        cmd.append(full_source_path)
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(f_torrent):
            task_store[task_id]['files']['torrent'] = f_torrent

        # 2. 找文件
        task_store[task_id]['msg'] = '扫描视频文件...'
        target_media_file = find_largest_file(full_source_path)
        
        if target_media_file:
            # 3. MediaInfo
            task_store[task_id]['msg'] = '生成 MediaInfo...'
            subprocess.run(["mediainfo", target_media_file, f"--LogFile={f_info}"], stdout=subprocess.DEVNULL)
            if os.path.exists(f_info):
                task_store[task_id]['files']['info'] = f_info
            
            # 4. 缩略图
            task_store[task_id]['msg'] = '生成预览图...'
            res = generate_thumbnail_optimized(target_media_file, f_thumb)
            
            if res == "success":
                 task_store[task_id]['files']['thumb'] = f_thumb
                 task_store[task_id]['msg'] = '✅ 全部成功'
            else:
                 task_store[task_id]['msg'] = f"⚠️ 种子成功，截图失败: {res}"
        else:
            task_store[task_id]['msg'] = '⚠️ 完成 (无视频)'
        
        task_store[task_id]['status'] = 'done'

    except Exception as e:
        task_store[task_id]['status'] = 'error'
        task_store[task_id]['msg'] = f"系统错误: {str(e)}"

# ================= 路由 =================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('错误', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/status')
@login_required
def check_status():
    task_id = request.args.get('task_id')
    if task_id and task_id in task_store:
        return jsonify(task_store[task_id])
    return jsonify({'status': 'unknown'})

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    current_tracker = load_default_tracker()
    last_task_id = request.args.get('task_id')
    
    download_link = None
    mediainfo_link = None
    thumbnail_link = None
    mediainfo_content = ""
    error_msg = None
    
    if last_task_id and last_task_id in task_store:
        task_data = task_store[last_task_id]
        if task_data['status'] == 'done':
            if "失败" in task_data['msg']: error_msg = task_data['msg']
            
            files = task_data['files']
            if 'torrent' in files: download_link = files['torrent']
            if 'info' in files:
                mediainfo_link = files['info']
                try:
                    with open(files['info'], 'r') as f: mediainfo_content = f.read()
                except: pass
            if 'thumb' in files: thumbnail_link = files['thumb']

    if request.method == 'POST':
        rel_path = request.form.get('path', '').strip()
        tracker_url = request.form.get('tracker', '').strip()
        save_default = request.form.get('save_default')
        is_private = request.form.get('private')
        comment = request.form.get('comment', '').strip()
        piece_size = request.form.get('piece_size', '24')
        
        if save_default and tracker_url:
            save_default_tracker(tracker_url)
            current_tracker = tracker_url

        full_source_path = os.path.join(BASE_DIR, rel_path.strip('/'))
        
        if not os.path.exists(full_source_path):
            flash(f"路径不存在: {full_source_path}", "danger")
        else:
            if os.path.isdir(full_source_path):
                output_folder = os.path.join(full_source_path, "torrent")
            else:
                output_folder = os.path.join(os.path.dirname(full_source_path), "torrent")
            
            task_id = full_source_path
            t = threading.Thread(target=background_process, args=(
                tracker_url, is_private, comment, piece_size, 
                full_source_path, output_folder, task_id
            ))
            t.start()
            return redirect(url_for('index', task_id=task_id))

    return render_template('index.html', 
                           default_tracker=current_tracker,
                           download_path=download_link,
                           mediainfo_link=mediainfo_link,
                           thumbnail_link=thumbnail_link,
                           mediainfo_content=mediainfo_content,
                           error_msg=error_msg)

@app.route('/download')
@login_required
def download_file():
    file_path = request.args.get('file')
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "文件未找到"

@app.route('/view_image')
@login_required
def view_image():
    file_path = request.args.get('file')
    if file_path and os.path.exists(file_path):
        return send_file(file_path, mimetype='image/jpeg')
    return "图片未找到"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)