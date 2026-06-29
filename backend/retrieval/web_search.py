"""网络搜索模块 — 封装国内搜索引擎 (360搜索)"""
from typing import List, Dict
from loguru import logger
import requests
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures

def search_web(query: str, max_results: int = 3) -> List[Dict]:
    """
    使用 360 搜索 (so.com)，并封装成类似本地 Chunk 的格式。
    返回的 Dict 结构形如:
    {
        "content": "摘要内容...",
        "filename": "网页: [标题]",
        "course": "网络搜索",
        "score": 1.0,
        "metadata": {"url": "..."}
    }
    """
    def _do_search():
        """"360 搜索请求：抓取 HTML 并用 BeautifulSoup 解析标题摘要。"""
        chunks = []
        url = f"https://www.so.com/s?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=3)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.find_all('li', class_='res-list')
        
        for item in items:
            if len(chunks) >= max_results:
                break
                
            title_a = item.find('h3')
            if not title_a:
                continue
                
            title = title_a.text.strip()
            link_tag = title_a.find('a')
            url_href = link_tag['href'] if link_tag and 'href' in link_tag.attrs else url
            
            abstract = ""
            p = item.find('p', class_='res-desc')
            if p:
                abstract = p.text.strip()
                
            if not abstract:
                continue
                
            chunk = {
                "content": f"【网页标题】{title}\n【网页内容摘要】{abstract}",
                "filename": f"{url_href}",
                "course": "网络搜索",
                "score": 0.9,
                "metadata": {"url": url_href}
            }
            chunks.append(chunk)
        return chunks

    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            results = future.result(timeout=4)  # 强制 4 秒超时
        logger.info("网络搜索 '{}' 获取到 {} 条结果", query, len(results))
    except concurrent.futures.TimeoutError:
        logger.warning(f"网络搜索超时，跳过搜索: {query}")
    except Exception as e:
        logger.error(f"网络搜索失败: {e}")
        
    return results
