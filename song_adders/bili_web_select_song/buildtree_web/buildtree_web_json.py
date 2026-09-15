#!/usr/bin/env python3
import requests
import json
import re
import sys
from bs4 import BeautifulSoup

def extract_video_info(url):
    """
    Extract video information from a B站 video page URL
    """
    # 1. Get the page
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    
    response = requests.get(url, headers=headers)
    
    # 2. Create soup
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 3. Find script tag containing __INITIAL_STATE__
    script_tag = soup.find('script', string=re.compile(r'window\.__INITIAL_STATE__'))
    
    if not script_tag:
        print("未找到包含 __INITIAL_STATE__ 的 script 标签")
        return None
    
    # 4. Get script content
    script_content = script_tag.get_text()
    
    # 5. Extract JSON
    pattern = r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;'
    match = re.search(pattern, script_content, re.DOTALL)
    
    if not match:
        print("无法提取 JSON")
        return None
    
    json_str = match.group(1)
    data = json.loads(json_str)
    
    # 6. Extract video data
    video_data = data.get('videoData', {})
    result = {}
    
    # Check if it's a series/season (multi-video)
    video_list = video_data.get('ugc_season', {})
    
    if video_list:
        # It's a series/season
        # print(f"系列标题: {video_list.get('title', '无标题')}")
        
        
        sections = video_list.get('sections', [])
        result = {
                'name': video_list.get('title', 'n'),
                'titles':[]
                }
        if sections:
            episodes = sections[0].get('episodes', [])
            
            # Extract all videos in the series
            for episode in episodes:
                # print(f"BV号: {episode.get('bvid', '无')}")
                bvid = episode.get('bvid', 'n')
                title = {
                        'name':episode.get('title', ''),
                        'tabs':[]
                        }
                for entry in episode.get("pages", []):
                    tab = {
                            'name':entry.get('part', ''),
                            'items':[]
                            }
                    tab['items'] = [{
                        'bvid': bvid,
                        'cid': entry.get('cid', '无'),
                        'tab_name': entry.get('part', '无'),
                        'duration': entry.get('duration', 0),
                        'p': entry.get('page', 0),
                        'group_title':video_list.get('title', 'n'),
                        'title':episode.get('title', ''),
                        'pic':episode.get('arc', '').get('pic', ''),
                        'scheme':"biliweb"
                    }]
                    title['tabs'].append(tab)
                result['titles'].append(title)
                
                # print(f"\n视频标题: {video_info['title']}")
                # print(f"BV号: {video_info['bvid']}")
                # for page in video_info['pages']:
                #     print(f"  cid: {page['cid']}")
                #     print(f"  分P标题: {page['part']}")
                #     print(f"  时长: {page['duration']}秒")
                # print("=" * 50)
    else:
        # It's a series/season
        # print(f"系列标题: {video_list.get('title', '无标题')}")
        
        # Single video
        video_info = {
            'title': video_data.get('title', '无标题'),
            'bvid': video_data.get('bvid', '无'),
            'pages': []
        }
        
        for entry in video_data.get("pages", []):
            video_info['pages'].append({
                'cid': entry.get('cid', '无'),
                'part': entry.get('part', '无'),
                'duration': entry.get('duration', 0),
                'page': entry.get('page', 0)
            })
        
        result = {
                'name': video_data.get('title', '无标题'),
                'titles':[]
                }
        bvid = video_data.get('bvid', '无')
        title = {
                'name':video_data.get('title', ''),
                'tabs':[]
                }
        for entry in video_data.get("pages", []):
            tab = {
                    'name':entry.get('part', ''),
                    'items':[]
                    }
            tab['items'] = [{
                'bvid': bvid,
                'cid': entry.get('cid', '无'),
                'tab_name': entry.get('part', '无'),
                'duration': entry.get('duration', 0),
                'p': entry.get('page', 0),
                'group_title':video_data.get('title', ''),
                'title':video_data.get('title', ''),
                'pic':video_data.get('pic', ''),
                'scheme':"biliweb"
            }]
            title['tabs'].append(tab)
        result['titles'].append(title)
        
        # print(f"\n视频标题: {video_info['title']}")
        # print(f"BV号: {video_info['bvid']}")
        # for page in video_info['pages']:
        #     print(f"  cid: {page['cid']}")
        #     print(f"  分P标题: {page['part']}")
        #     print(f"  时长: {page['duration']}秒")
        # print("=" * 50)
    
    return result

def main():
    # Check if URL is provided as command line argument
    url = sys.argv[1]
    # else:
        # Default URL if no argument provided
        # url = "https://www.bilibili.com/video/BV15HgE6TER4/"
        # print(f"未提供URL，使用默认URL: {url}")
    
    # print(f"正在处理: {url}")
    # print("=" * 60)
    
    # Extract video information
    video_data = extract_video_info(url)
    
    # Optionally save to JSON file
    # if video_data:
    #     # Save to JSON file
    #     filename = "video_info.json"
    #     with open(filename, 'w', encoding='utf-8') as f:
    #         json.dump(video_data, f, ensure_ascii=False, indent=2)
    #     print(f"\n数据已保存到 {filename}\n")
    if video_data:
        print(json.dumps(video_data, indent=2, ensure_ascii=False))
        return 0
    else:
        print("blocked")
    return 1

if __name__ == "__main__":
    main()
