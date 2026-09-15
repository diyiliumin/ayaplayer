#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import sys

class VideoNode:
    """视频树节点"""
    def __init__(self, title, bv=None, link=None, level=1):
        self.title = title
        self.bv = bv
        self.link = link
        self.level = level
        self.children = []
        self.parent = None
    
    def add_child(self, child):
        child.parent = self
        self.children.append(child)
        return child
    
    def to_dict(self):
        return {
            'title': self.title,
            'bv': self.bv,
            'link': self.link,
            'level': self.level,
            'children': [child.to_dict() for child in self.children]
        }
    
    def print_tree(self, prefix="", is_last=True):
        if self.level == 1:
            connector = "├── " if not is_last else "└── "
        else:
            connector = "│   " + ("├── " if not is_last else "└── ")
        
        info = f"[L{self.level}] {self.title}"
        if self.bv:
            info += f" (BV: {self.bv})"
        if self.link:
            info += f" [链接: {self.link}]"
        
        print(prefix + connector + info)
        
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(self.children):
            child.print_tree(child_prefix, i == len(self.children) - 1)

def get_video_pod_tree(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')


        root_nodes = []
        level1_nodes = []
        level2_nodes = []
        level3_nodes = []

        # 第一级
        video_pod = soup.find(class_="video-pod video-pod")
        if not video_pod:
            video_pod = soup.find(class_="video-pod")
            if video_pod:
                header = video_pod.find(class_="video-pod__header")
                if header:
                    title_elems = header.find_all(class_="title jumpable")
                    if title_elems:
                        for title_elem in title_elems:
                            title_text = title_elem.get_text(strip=True)
                            link = title_elem.get('href') if title_elem.name == 'a' else None
                            if not link:
                                parent_a = title_elem.find_parent('a')
                                if parent_a:
                                    link = parent_a.get('href')
                            
                            node = VideoNode(title_text, link=link, level=1)
                            level1_nodes.append(node)
                            root_nodes.append(node)
                        
                        print(f"第一级视频数量: {len(level1_nodes)}")
                        body = video_pod.find(class_="video-pod__body")
                        if not body:
                            print("警告: 未找到 video-pod__body")
                            body = video_pod
                
                        # 第二级和第三级
                        pod_items = body.find_all(class_="pod-item video-pod__item simple")
                        if not pod_items:
                            pod_items = body.find_all(class_="pod-item")
                        
                        # 建立层级关系
                        for item in pod_items:
                            bv_id = item.get('data-key')
                            if not bv_id:
                                continue
                            
                            main_title = ""
                            head = item.find(class_="simple-base-item")
                            if head:
                                title_elem = head.find(class_="title")
                                if title_elem:
                                    main_title = title_elem.get_text(strip=True)
                            
                            level2_node = VideoNode(main_title, bv=bv_id, level=2)
                            level2_nodes.append(level2_node)
                            
                            # 第三级子视频
                            sub_items_head = item.find(class_=["page-list", "simple"])
                            if sub_items_head:
                                sub_items = sub_items_head.find_all(class_=["simple-base-item", "page-item", "sub"])
                                for sub in sub_items:
                                    sub_title = ""
                                    title_elem = sub.find('div', class_="title-txt")
                                    if title_elem:
                                        sub_title = title_elem.get_text(strip=True)
                                    
                                    if sub_title:
                                        level3_node = VideoNode(sub_title, bv=bv_id, level=3)
                                        level3_nodes.append(level3_node)
                                        level2_node.add_child(level3_node)
                    else:
                        title_elems_not_heji = header.find_all(class_="title")
                        if title_elems_not_heji:
                            meta_tag = soup.find('meta', property='og:url')
                            if meta_tag:
                                og_url = meta_tag.get('content')
                                bv_id = str(og_url).rstrip('/').split('/')[-1]
                                print(f"og:url的内容是: {og_url}")
                                top_title=''
                                top_title_cont = soup.find(class_="video-info-title-inner")
                                if top_title_cont:
                                    top_title= top_title_cont.get_text(strip=True)
                                node = VideoNode(top_title, link=og_url, level=1)
                                level1_nodes.append(node)
                                root_nodes.append(node)
                                body = video_pod.find(class_="video-pod__body")
                                if body:
                                    p_elems = body.find_all(class_=["simple-base-item", "video-pod__item" ,"normal"])
                                    for p_elem in p_elems:
                                        title_elem =p_elem.find(class_=["title"])
                                        if title_elem:
                                            main_title = title_elem.get_text(strip=True)
                                            level2_node = VideoNode(main_title, bv=bv_id, level=2)
                                            level2_nodes.append(level2_node)
        
            else:
                meta_tag = soup.find('meta', property='og:url')
                if meta_tag:
                    og_url = meta_tag.get('content')
                    bv_id = str(og_url).rstrip('/').split('/')[-1]
                    print(f"og:url的内容是: {og_url}")
                    top_title=''
                    top_title_cont = soup.find(class_="video-info-title-inner")
                    if top_title_cont:
                        top_title= top_title_cont.get_text(strip=True)
                    node = VideoNode(top_title, link=og_url, level=1)
                    level1_nodes.append(node)
                    root_nodes.append(node)
        # 将第二级节点添加到第一级
        if level1_nodes and level2_nodes:
            # 简单分配：所有第二级节点作为第一个第一级节点的子节点
            level1_nodes[0].children = level2_nodes
            for child in level2_nodes:
                child.parent = level1_nodes[0]

        return root_nodes

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        return []
    except Exception as e:
        print(f"解析过程中发生错误: {e}")
        return []

def print_video_tree(root_nodes):
    if not root_nodes:
        print("未获取到数据")
        return
    
    print("\n" + "=" * 80)
    print("B站视频列表 - 树形结构")
    print("=" * 80)
    
    for i, node in enumerate(root_nodes):
        if i > 0:
            print()
        node.print_tree(is_last=(i == len(root_nodes) - 1))
    
    print("\n" + "=" * 80)

video_url = sys.argv[1]

print("正在构建B站视频树...")
print(f"URL: {video_url}\n")

tree = get_video_pod_tree(video_url)
print_video_tree(tree)
