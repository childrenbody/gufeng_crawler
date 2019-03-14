#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 21:44:06 2019

@author: lufei
"""
import os
import urllib
import re
from bs4 import BeautifulSoup
from functools import wraps
import logging
logging.basicConfig(filename='error.log', format="%(asctime)s - %(message)s", level=logging.INFO)

def log(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(func.__name__)
        return func(*args, **kwargs)
    return wrapper

def bytes_to_strings(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'page' not in kwargs:
            kwargs['page'] = args[1]
            args = args[0],
        if isinstance(kwargs['page'], bytes):
            kwargs['page'] = kwargs['page'].decode('utf-8')
        if not isinstance(kwargs['page'], str):
            raise TypeError('excepted bytes or str, not {}'.format(type(kwargs['page'])))
        return func(*args, **kwargs)
    return wrapper

class UrlGenerate:
    def __init__(self, comic_name):
        self.comic_name = comic_name
        self.host_url = 'https://www.gufengmh8.com/'
        self.comic_url = self.get_comic_name(comic_name)
        self.res_url = 'https://res.gufengmh8.com/'
        
    def get_comic_name(self, comic_name):
        return '{}{}/{}/'.format(self.host_url, 'manhua', comic_name)

    def get_all_chapters_url(self):
        return '{}{}'.format(self.comic_url, '#chapters')
        
    def get_chapters_url(self, chapters_url):
        return urllib.request.urljoin(self.host_url, chapters_url)
        
    def _get_image_url(self, image_path, image_name):
        image_path = urllib.request.urljoin(self.res_url, image_path)
        return '{}{}'.format(image_path, image_name)
    
    def get_image_url(self, images: list, path) -> dict:
        return {i + 1: self._get_image_url(path, img)
                    for i, img in enumerate(images)}

class Preprocess:
    def __init__(self, comic_name):
        self.url_gen = UrlGenerate(comic_name)
        self.comic_name = comic_name
        
    @bytes_to_strings    
    def get_chapters_list(self, page: bytes or str) -> dict:
        soup = BeautifulSoup(page, 'lxml')
        chapters = soup.find(attrs={'id': 'chapter-list-1'})
        chapters = list(set(chapters.contents))
        chapters.remove('\n')
        chapters_dict = {tag.span.text: tag.a.get('href') for tag in chapters}
        return chapters_dict
    
    @bytes_to_strings
    def get_image_list(self, page: bytes or str) -> list:
        def remove_double_quotes(strings):
            return strings[1:-1] if strings[0] == '"' and strings[-1] == '"' else strings
            
        chapter_image = re.search('var chapterImages = \[(.*?)\];', page)
        if chapter_image is None:
            raise Exception("匹配图片链接失败")
        
        images = chapter_image.group(1).split(',')
        images = list(map(lambda x: remove_double_quotes(x), images))
        return images
    
    @bytes_to_strings
    def get_image_path(self, page: bytes or str) -> str:
        path = re.search('var chapterPath = "(.*?)";', page)
        if path is None:
            raise Exception("匹配图片路径失败")
        return path.group(1)
    
    @staticmethod
    def make_save_folder(comic_name, chapter):
        path = os.path.join(comic_name, chapter)
        if not os.path.exists(path):
            os.makedirs(path)
        return path
    
    def image_exist(self, chapter, index):
        jpg = '{}.jpg'.format(index)
        path = self.make_save_folder(self.comic_name, chapter)
        path = os.path.join(path, jpg)
        return path if not os.path.exists(path) else False
    
    def save_jpg(self, jpg: bytes, save_path):
        if not isinstance(jpg, bytes):
            raise TypeError('excepted bytes, not {}'.format(type(jpg)))
        with open(save_path, 'wb') as f:
            f.write(jpg)
        
class Spider:
    def __init__(self, comic_name):
        self.comic_name = comic_name
        self.pre = Preprocess(comic_name)
        self.url_gen = self.pre.url_gen
        
    def get_source_code_from_url(self, url) -> bytes:
        page = urllib.request.urlopen(url)
        return page.read()

    def get_image_url_list(self, chapter_url) -> dict:
        chapter_url = self.url_gen.get_chapters_url(chapter_url)
        chapter_page = self.get_source_code_from_url(chapter_url)
        image = self.pre.get_image_list(chapter_page)
        path = self.pre.get_image_path(chapter_page)
        return self.url_gen.get_image_url(image, path)

    def make_chapter_url_list(self) -> dict:
        chapters_url = self.url_gen.get_all_chapters_url()        
        chapters_page = self.get_source_code_from_url(chapters_url)
        chapters_list = self.pre.get_chapters_list(chapters_page)
        chapters_dict = {chapter: self.get_image_url_list(url)
                            for chapter, url in chapters_list.items()}
        return chapters_dict
    
    def _download_image_and_save(self, url, save_path):
        try:
            image = self.get_source_code_from_url(url)
            self.pre.save_jpg(image, save_path)
            return True
        except urllib.request.HTTPError:
            return False
    
    def download_image_by_chapter(self, chapter, image_url_list):
        self.pre.make_save_folder(self.comic_name, chapter)
        success = 0
        failure = 0
        for i, url in image_url_list.items():
            print(i)
            save_path = self.pre.image_exist(chapter, i)
            if not save_path:
                continue
            if not self._download_image_and_save(url, save_path):
                logging.error('{}: page {} not found'.format(chapter, i))
                failure += 1
            success += 1
        return success, failure
            
    def run(self):
        chapters_dict = self.make_chapter_url_list()
        success = 0
        failure = 0
        for chapter, images_url in chapters_dict.items():
            print(chapter)
            s, f = self.download_image_by_chapter(chapter, images_url)
            success += s
            failure += f
        logging.info('{} 已完成. {}成功, {}失败'.format(self.comic_name, success, failure))
    
if __name__ == '__main__':
    # sp = Spider('wuliandianfeng')
    # sp.run()

    
