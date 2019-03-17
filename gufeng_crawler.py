#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 21:44:06 2019

@author: childrenbody
"""
import os
import urllib
import re
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import logging

def get_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)
    fh = logging.FileHandler(filename='error.log')
    fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(fh)
    return logger

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
        ul = re.search('<ul id="chapter-list-1" data-sort="asc">(.*?)</ul>', page, re.S).group(1)
        url_list = re.findall('<a href="(.*?)"', ul)
        title_list = re.findall('<span>(.*?)</span>', ul)
        chapters_dict = dict(zip(title_list, url_list))
        return chapters_dict
    
    @bytes_to_strings
    def get_image_list(self, page: bytes or str) -> list:
        def remove_double_quotes(strings):
            return strings[1:-1] if strings[0] == '"' and strings[-1] == '"' else strings
            
        chapter_image = re.search('var chapterImages = \[(.*?)\];', page)
        if chapter_image is None:
            raise Exception("matching image link failed.")
        
        images = chapter_image.group(1).split(',')
        images = list(map(lambda x: remove_double_quotes(x), images))
        return images
    
    @bytes_to_strings
    def get_image_path(self, page: bytes or str) -> str:
        path = re.search('var chapterPath = "(.*?)";', page)
        if path is None:
            raise Exception("matching image path failed.")
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
        
class Crawler:
    def __init__(self, comic_name):
        self.comic_name = comic_name
        self.pre = Preprocess(comic_name)
        self.url_gen = self.pre.url_gen
        self.MAX_WORKER = 10
        self.logger = get_logger()
        
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
        self.file_sum = sum([len(v) for k, v in chapters_dict.items()])
        return chapters_dict
    
    def _download_image_and_save(self, url, save_path):
        try:
            image = self.get_source_code_from_url(url)
            self.pre.save_jpg(image, save_path)
            print(save_path)
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
                self.logger.error('{}: page {} not found'.format(chapter, i))
                failure += 1
            success += 1
        return success, failure
    
    def single_threading(self, chapter_images):
        self.pre.make_save_folder(self.comic_name, chapter_images['title'])
        for i, url in chapter_images['images'].items():
            save_path = self.pre.image_exist(chapter_images['title'], i)
            if not save_path:
                continue
            print(chapter_images['title'])
            if not self._download_image_and_save(url, save_path):
                self.logger.error('{}: page {} not found'.format(chapter_images['title'], i))
    
    def multithreading(self):
        chapters_dict = self.make_chapter_url_list()
        chapters_list = [dict(title = chapter, images = images)
                            for chapter, images in chapters_dict.items()]
        
        with ThreadPoolExecutor(max_workers=self.MAX_WORKER) as pool:
            list(pool.map(self.single_threading, chapters_list))
    
    def run(self):
        '''Sequential execution'''
        chapters_dict = self.make_chapter_url_list()
        success = 0
        failure = 0
        for chapter, images_url in chapters_dict.items():
            print(chapter)
            s, f = self.download_image_by_chapter(chapter, images_url)
            success += s
            failure += f
        self.logger.info('{} has completed! {} successes, {} failures'.format(self.comic_name, success, failure))
    
    def jpg_count(self):
        self.jpg_sum = sum([len(os.listdir(os.path.join('wuliandianfeng', chapter)))
                                for chapter in os.listdir('wuliandianfeng')])
    
if __name__ == '__main__':
    sp = Crawler('wuliandianfeng')
    sp.multithreading()
