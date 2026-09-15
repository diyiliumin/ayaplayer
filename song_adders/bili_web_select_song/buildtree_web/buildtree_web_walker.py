#!/usr/bin/env python3

import subprocess
import json
import time
import sys
import re
import os

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def read_urls_from_file(filename):
    """读取URL文件，自动提取URL"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = []
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 自动提取URL（从文本中提取）
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    urls.append(url_match.group(0))
                else:
                    urls.append(line)  # 整行当作URL
        return urls
    except FileNotFoundError:
        print(f"❌ 文件不存在: {filename}")
        return []

def process_url(url, max_attempts=5):
    """处理单个URL，失败重试"""
    clean_url = re.sub(r'\?.*$', '', url)
    
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            wait_time = 2 ** (attempt - 1)
            print(f"  ⏳ 重试 {attempt}/{max_attempts} (等待 {wait_time}s)...")
            time.sleep(wait_time)
        
        try:
            result = subprocess.run(
                ['./buildtree_web_json.py', clean_url],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            # 检查是否被block
            if "未找到包含 __INITIAL_STATE__ 的 script 标签" in stdout:
                print(f"  🚫 被拦截 (尝试 {attempt}/{max_attempts})")
                if attempt < max_attempts:
                    continue
                else:
                    return None
            
            # 尝试从stdout提取JSON
            try:
                start = stdout.find('{')
                end = stdout.rfind('}') + 1
                if start != -1 and end > start:
                    json_str = stdout[start:end]
                    data = json.loads(json_str)
                    return data
            except:
                pass
            
            # 检查是否有"数据已保存到"
            if "数据已保存到" in stdout:
                filename_match = re.search(r'数据已保存到\s+([^\s]+)', stdout)
                if filename_match:
                    json_filename = filename_match.group(1)
                    if os.path.exists(json_filename):
                        with open(json_filename, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        os.remove(json_filename)
                        return data
            
            return None
            
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            if attempt < max_attempts:
                continue
            else:
                return None
    
    return None

def main():
    # 检查输入
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    input_file = os.path.join(script_dir, "urls.txt")
    
    # 检查程序是否存在（在脚本目录下）
    target_script = os.path.join(script_dir, 'buildtree_web_json.py')
    if not os.path.exists(target_script):
        print(f"❌ 找不到 {target_script}")
        return
    
    # 读取URL
    urls = read_urls_from_file(input_file)
    if not urls:
        print("❌ 没有找到URL")
        return
    
    print(f"📚 共 {len(urls)} 个URL")
    print("=" * 60)
    
    # 处理每个URL
    results = []
    success_count = 0
    
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] {url}")
        data = process_url(url)
        
        if data is not None:
            results.append(data)
            success_count += 1
            print(f"  ✅ 成功")
        else:
            print(f"  ❌ 失败")
    
    # 保存结果
    print("\n" + "=" * 60)
    print(f"✅ 成功: {success_count}/{len(urls)}")
    
    if results:
        output_file = "results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    else:
        print("❌ 没有成功数据")

if __name__ == "__main__":
    main()
