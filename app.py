import os
import subprocess
import json
import shutil
import threading
import zipfile
import sys
from functools import wraps
# 核心修正：引入 unquote_plus 处理 URL 中的空格和特殊字符
from urllib.parse import unquote, unquote_plus
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, jsonify

app = Flask(__name__)

# ================= 配置区 =================
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin') 
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'password123') 
SECRET_KEY = os.environ.get('SECRET_KEY', 'seaside_secret_key')

BASE_DIR = "/data"
CONFIG_FILE = os.path.join(BASE_DIR, '.tracker_config.json')

app.secret_key = SECRET_KEY
task_store = {}
# ==========================================

def load_default_tracker():
    default_url = "http://udp.opentrackr.org:1337/announce"
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get('tracker_url', default_url)
    except Exception: pass
    return default_url

def save_default_tracker(url):
    try:
        with open(CONFIG_FILE, 'w') as f: json.dump({'tracker_url': url}, f)
    except Exception as e: print(f"保存配置失败: {e}")

def find_largest_file(start_path):
    if os.path.isfile(start_path): return start_path
    largest_file = None; max_size = 0
    for root, dirs, files in os.walk(start_path):
        for f in files:
            file_path = os.path.join(root, f)
            if 'torrent' in root.split(os.sep): continue
            try:
                size = os.path.getsize(file_path)
                if size > max_size and size > 50 * 1024 * 1024:
                    max_size = size; largest_file = file_path
            except OSError: continue
    return largest_file

def get_video_duration(video_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        val = result.stdout.strip()
        return float(val) if val else 0
    except: return 0

# === 截图生成逻辑（扁平化版） ===
def generate_screenshots(video_path, output_base_path, mode, quality):
    temp_dir = "/tmp/temp_thumbs_processing"
    
    settings_grid = {
        'small':  (320, 15), 
        'medium': (640, 5),
        'large':  (1280, 2)
    }
    settings_full = {
        'medium': (1920, 1, ["-qmin", "1", "-qmax", "1"]), 
        'large':  (0, 1, ["-qmin", "1", "-qmax", "1"])
    }

    try:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        duration = get_video_duration(video_path)
        if duration < 60: return "success", "视频太短，跳过截图"

        result_file = None 
        preview_data = None 

        # output_base_path 例如: /data/Movie/torrent/MovieName
        # 我们需要直接在这个路径基础上加后缀，不创建子文件夹
        
        # 基础目录 (用于存放 ZIP)
        base_dir = os.path.dirname(output_base_path)
        # 文件名前缀
        base_name = os.path.basename(output_base_path)

        if mode == 'grid':
            width, q_val = settings_grid.get(quality, (640, 5))
            
            # 直接生成 Name_Thumb.jpg
            output_jpg = output_base_path + "_Thumb.jpg"
            blank_img = os.path.join(temp_dir, "blank.jpg")
            
            subprocess.run(["ffmpeg", "-f", "lavfi", "-i", f"color=c=black:s={width}x{int(width*9/16)}", "-frames:v", "1", "-y", blank_img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            interval = duration / 16
            for i in range(16):
                timestamp = (i * interval) + (interval / 2)
                img_path = os.path.join(temp_dir, f"img_{i:02d}.jpg")
                cmd = ["ffmpeg", "-ss", str(timestamp), "-y", "-i", video_path, "-frames:v", "1", "-qscale:v", str(q_val), "-vf", f"scale={width}:-1", img_path]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                    shutil.copy(blank_img, img_path)

            cmd_tile = ["ffmpeg", "-y", "-i", os.path.join(temp_dir, "img_%02d.jpg"), "-vf", "tile=4x4:padding=5:color=white", "-qscale:v", str(q_val), output_jpg]
            subprocess.run(cmd_tile, capture_output=True)
            
            if os.path.exists(output_jpg):
                result_file = output_jpg
                preview_data = output_jpg 
            else:
                return "error", "拼图生成失败"

        else:
            # 全屏模式：生成 Name_shot_1.jpg, Name_shot_2.jpg 等
            target_width, q_val, extra_flags = settings_full.get(quality, (1920, 1, []))
            image_list = [] 
            steps = 7 
            for i in range(1, steps): 
                timestamp = duration * (i / steps)
                img_path = f"{output_base_path}_shot_{i}.jpg"
                
                cmd = ["ffmpeg", "-ss", str(timestamp), "-y", "-i", video_path, "-frames:v", "1", "-qscale:v", str(q_val)]
                cmd.extend(extra_flags)
                if target_width > 0: cmd.extend(["-vf", f"scale={target_width}:-1"])
                cmd.append(img_path)
                
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                    image_list.append(img_path)

            # 打包 ZIP
            zip_path = output_base_path + "_Screenshots.zip"
            if image_list:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for img in image_list:
                        zipf.write(img, os.path.basename(img))
                result_file = zip_path
                # 预览只取第一张图
                preview_data = image_list[0] if len(image_list) > 0 else None
            else:
                return "error", "截图失败"

        return "success", {"file": result_file, "preview": preview_data}

    except Exception as e:
        return "error", str(e)
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

def background_process(tracker_url, is_private, comment, piece_size, full_source_path, output_folder, task_id, shot_mode, shot_quality):
    task_store[task_id] = {'status': 'running', 'msg': '初始化...', 'files': {}}
    try:
        if not os.path.exists(output_folder): os.makedirs(output_folder, exist_ok=True)
        base_name = os.path.basename(full_source_path.rstrip('/')) if os.path.isdir(full_source_path) else os.path.basename(full_source_path)

        f_torrent = os.path.join(output_folder, f"{base_name}.torrent")
        f_info = os.path.join(output_folder, f"{base_name}_MediaInfo.txt")
        # 这是生成截图文件名的基础前缀：/data/.../torrent/Name
        f_shot_base = os.path.join(output_folder, base_name) 

        # === 清理逻辑：删除旧文件 ===
        # 1. 删除 torrent 和 info
        for f in [f_torrent, f_info]:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass
        
        # 2. 删除 ZIP
        zip_file = f_shot_base + "_Screenshots.zip"
        if os.path.exists(zip_file):
            try: os.remove(zip_file)
            except: pass

        # 3. 删除旧的 JPG 图片 (精确匹配前缀)
        if os.path.exists(output_folder):
            for fname in os.listdir(output_folder):
                # 只有当文件以 base_name 开头 且 是 jpg 时才删除，防止误删
                if fname.startswith(base_name) and fname.lower().endswith(('.jpg', '.jpeg')):
                    try: os.remove(os.path.join(output_folder, fname))
                    except: pass
        
        # 4. 删除旧版本的 _Screenshots 文件夹 (如果有遗留)
        old_dir = f_shot_base + "_Screenshots"
        if os.path.exists(old_dir): shutil.rmtree(old_dir)
        # ============================

        task_store[task_id]['msg'] = '正在生成种子...'
        cmd = ["mktorrent", "-v", "-l", piece_size, "-a", tracker_url]
        if is_private: cmd.append("-p")
        if comment: cmd.extend(["-c", comment])
        cmd.extend(["-o", f_torrent])
        cmd.append(full_source_path)
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(f_torrent): task_store[task_id]['files']['torrent'] = f_torrent

        task_store[task_id]['msg'] = '扫描视频文件...'
        target_media_file = find_largest_file(full_source_path)
        
        if target_media_file:
            task_store[task_id]['msg'] = '生成 MediaInfo...'
            subprocess.run(["mediainfo", target_media_file, f"--LogFile={f_info}"], stdout=subprocess.DEVNULL)
            if os.path.exists(f_info): task_store[task_id]['files']['info'] = f_info
            
            task_store[task_id]['msg'] = f'正在截图 ({shot_mode}/{shot_quality})...'
            status, res = generate_screenshots(target_media_file, f_shot_base, shot_mode, shot_quality)
            
            if status == "success":
                 if res.get('file'): task_store[task_id]['files']['shot_download'] = res['file']
                 if res.get('preview'): task_store[task_id]['files']['shot_preview'] = res['preview']
                 task_store[task_id]['msg'] = '✅ 全部成功'
            else:
                 task_store[task_id]['msg'] = f"⚠️ 截图失败: {res}"
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
    if task_id:
        if task_id in task_store: return jsonify(task_store[task_id])
        elif task_id.replace(' ', '+') in task_store: return jsonify(task_store[task_id.replace(' ', '+')])
        elif unquote(task_id) in task_store: return jsonify(task_store[unquote(task_id)])
    return jsonify({'status': 'unknown'})

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    current_tracker = load_default_tracker()
    raw_task_id = request.args.get('task_id')
    
    download_link = None
    mediainfo_link = None
    shot_download_link = None 
    shot_preview_link = None  
    mediainfo_content = ""
    error_msg = None
    
    target_task_id = None
    if raw_task_id:
        if raw_task_id in task_store: target_task_id = raw_task_id
        elif raw_task_id.replace(' ', '+') in task_store: target_task_id = raw_task_id.replace(' ', '+')
        elif unquote(raw_task_id) in task_store: target_task_id = unquote(raw_task_id)
    
    if target_task_id:
        task_data = task_store[target_task_id]
        if task_data['status'] == 'done':
            if "失败" in task_data['msg']: error_msg = task_data['msg']
            files = task_data['files']
            
            if 'torrent' in files: download_link = files['torrent']
            if 'info' in files and os.path.exists(files['info']):
                mediainfo_link = files['info']
                try: 
                    with open(files['info'], 'r') as f: mediainfo_content = f.read()
                except: pass
            if 'shot_download' in files: shot_download_link = files['shot_download']
            
            # === 图片查找逻辑 ===
            img_path = None
            
            # 1. 优先使用 Task 中的记录
            if 'shot_preview' in files:
                p = files['shot_preview']
                # 无论是字符串还是列表，只取第一个有效文件
                if isinstance(p, str) and os.path.exists(p):
                    img_path = p
                elif isinstance(p, list) and len(p) > 0 and os.path.exists(p[0]):
                    img_path = p[0]
            
            # 2. 如果记录失效，进行目录扫描
            if not img_path and 'info' in files:
                info_path = files['info']
                base_dir = os.path.dirname(info_path)
                if os.path.exists(base_dir):
                    # 获取 base_name (不含后缀)
                    base_name = os.path.basename(info_path).replace('_MediaInfo.txt', '')
                    candidates = []
                    for f in sorted(os.listdir(base_dir)):
                        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                            full_p = os.path.join(base_dir, f)
                            if base_name in f:
                                candidates.insert(0, full_p) # 匹配文件名的排前面
                            else:
                                candidates.append(full_p)
                    
                    if candidates:
                        img_path = candidates[0]

            # 3. 生成 URL (单图)
            if img_path:
                shot_preview_link = url_for('view_image', path=img_path)

    if request.method == 'POST':
        rel_path = request.form.get('path', '').strip()
        tracker_url = request.form.get('tracker', '').strip()
        save_default = request.form.get('save_default')
        is_private = request.form.get('private')
        comment = request.form.get('comment', '').strip()
        piece_size = request.form.get('piece_size', '24')
        shot_mode = request.form.get('shot_mode', 'grid')
        shot_quality = request.form.get('shot_quality', 'medium')

        if save_default and tracker_url:
            save_default_tracker(tracker_url)
            current_tracker = tracker_url

        full_source_path = os.path.join(BASE_DIR, rel_path.strip('/'))
        
        if not os.path.exists(full_source_path):
            flash(f"路径不存在: {full_source_path}", "danger")
        else:
            output_folder = os.path.join(full_source_path, "torrent") if os.path.isdir(full_source_path) else os.path.join(os.path.dirname(full_source_path), "torrent")
            task_id = full_source_path
            
            t = threading.Thread(target=background_process, args=(
                tracker_url, is_private, comment, piece_size, 
                full_source_path, output_folder, task_id,
                shot_mode, shot_quality
            ))
            t.start()
            return redirect(url_for('index', task_id=task_id))

    return render_template('index.html', 
                           default_tracker=current_tracker,
                           download_path=download_link,
                           mediainfo_link=mediainfo_link,
                           shot_download_link=shot_download_link,
                           shot_preview_link=shot_preview_link,
                           mediainfo_content=mediainfo_content,
                           error_msg=error_msg)

@app.route('/download')
@login_required
def download_file():
    file_path = request.args.get('file')
    if file_path:
        decoded = unquote(file_path)
        if os.path.exists(decoded): return send_file(decoded, as_attachment=True)
    return "文件未找到"

# === 核心：图片查看路由 ===
@app.route('/view_image')
@login_required
def view_image():
    file_path = request.args.get('path')
    if not file_path:
        return "No path provided", 400
    
    # 优先尝试 unquote_plus (处理空格变+号的情况)
    decoded_path = unquote_plus(file_path)
    if os.path.exists(decoded_path) and decoded_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        return send_file(decoded_path, mimetype='image/jpeg')
    
    # 备选：尝试普通 unquote
    decoded_fallback = unquote(file_path)
    if os.path.exists(decoded_fallback) and decoded_fallback.lower().endswith(('.jpg', '.jpeg', '.png')):
        return send_file(decoded_fallback, mimetype='image/jpeg')
        
    print(f"DEBUG: 无法找到图片。原始: {file_path}, 解码1: {decoded_path}, 解码2: {decoded_fallback}")
    return "Image not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)