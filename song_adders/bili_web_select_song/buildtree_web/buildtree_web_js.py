import requests
import json
import re
from bs4 import BeautifulSoup

# 1. 获取页面
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}
url = "https://www.bilibili.com/video/BV1gM411z7pz/"
# url = "https://www.bilibili.com/video/BV1kD54zPEZQ/"
# url = "https://www.bilibili.com/video/BV15HgE6TER4/"
response = requests.get(url, headers=headers)

# 2. 创建 soup
soup = BeautifulSoup(response.text, 'html.parser')

# 3. 查找包含 __INITIAL_STATE__ 的 script 标签
script_tag = soup.find('script', string=re.compile(r'window\.__INITIAL_STATE__'))

if script_tag:
    # 4. 获取脚本内容（确保是字符串）
    # print(script_tag)
    script_content = script_tag.get_text()
    
    # json_str = re.sub(r'^window\.__INITIAL_STATE__\s*=\s*', '', script_content)
    # json_str = re.sub(r';$', '', json_str)
    
    pattern = r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;'
    match = re.search(pattern, script_content, re.DOTALL)
    # print(match)
    if match:
        json_str = match.group(1)
        data = json.loads(json_str)
        
        print(json.dumps(data, indent=2, ensure_ascii=False))
        # 6. 提取 availableVideoList
        video_data = data.get('videoData', {})
        video_list = video_data.get('ugc_season', {})
        # print(video_list)

        if video_list:
            print(f"视频标题: {video_list.get('title', '无标题')}")
    
            sections = video_list.get('sections', 'n')
            episodes = sections[0].get('episodes', 'n')
    
            # 7. 遍历所有视频和分P
            for episode in episodes:
                print(f"视频标题: {episode.get('title', '无标题')}")
                print(f"BV号: {episode.get('bvid', '无')}")
                
                for entry in episode.get("pages", []):
                    print(f"cid: {entry.get('cid', '无')}")
                    print(f"视频标题: {entry.get('part', '无')}")
                print("=" * 50)
        else:
            print(f"视频标题: {video_data.get('title', '无标题')}")
    
            print(f"BV号: {video_data.get('bvid', '无')}")
            
            for entry in video_data.get("pages", []):
                print(f"cid: {entry.get('cid', '无')}")
                print(f"视频标题: {entry.get('part', '无')}")
            print("=" * 50)
    else:
        print("无法提取 JSON")
else:
    print("未找到包含 __INITIAL_STATE__ 的 script 标签")
