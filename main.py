# coding: utf-8
from urllib import request
from urllib import parse
import requests
import threading
import os
import hashlib
import time
import sys
# 在手机上跑 Pythonista ，引入 clipboard 比较方便
# import clipboard

requests.packages.urllib3.disable_warnings()

class Downloader:
    def __init__(self, url, download_dir="./", blocks_num=5):
        self.url = url
        filename = self.url.split("/")[-1]
        filename = parse.unquote(filename)
        self.filename = filename
        self.download_dir = download_dir
        self.blocks_num = blocks_num
        # 建立下载目录
        if not os.path.exists(self.download_dir):
            os.mkdir(self.download_dir)
        elif os.path.isfile(self.download_dir):
            os.remove(self.download_dir)
            os.mkdir(self.download_dir)
        # 建立缓存目录
        self.cache_dir = "./cache/"
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)
        elif os.path.isfile(self.cache_dir):
            os.remove(self.cache_dir)
            os.mkdir(self.cache_dir)
        self.file_size = self.get_size()
        # 用于测速的停止信号和计量变量
        self.done = False
        self.downloaded_size = []
        self.downloaded_time = []
        # 显示基本信息
        readable_size = self.get_readable_size(self.file_size)
        print("---------- UTOPIA Downloader ----------\n[url] %s\n[path] %s\n[size] %s" %
              (self.url, self.download_dir + self.filename, readable_size))

    def get_size(self):
        with request.urlopen(self.url) as req:
            content_length = req.headers["Content-Length"]
            return int(content_length)

    def get_readable_size(self, size):
        units = ["Byte", "KB", "MB", "GB", "TB", "PB"]
        unit_index = 0
        while size >= 1024:
            size = size / 1024
            unit_index += 1
        return "%.2f %s" % (size, units[unit_index])

    def get_ranges(self):
        ranges = []
        offset = int(self.file_size / self.blocks_num)
        for i in range(self.blocks_num):
            if i == self.blocks_num - 1:
                ranges.append((i * offset, self.file_size))
            else:
                ranges.append((i * offset, (i + 1) * offset - 1))
        return ranges

    def start(self):
        thread_arr = []
        n = 0
        for (start, end) in self.get_ranges():
            thread = threading.Thread(target=self.download, args=(start, end, n))
            thread_arr.append(thread)
            thread.start()
            n += 1
        speed_thread = threading.Thread(target=self.calculate_download_speed, args=())
        speed_thread.start()
        for t in thread_arr:
            t.join()
        self.sew_together()

    def download(self, start, end, event_num):
        cache_filename = self.cache_dir + self.filename + ".part" + str(event_num)
        total_size = end - start + 1
        if os.path.exists(cache_filename):
            now_size = os.path.getsize(cache_filename)
        else:
            now_size = 0
        if now_size < total_size:
            headers = {'Range': 'Bytes=%d-%s' % (now_size+int(start), end), 'Accept-Encoding': '*'}
            print("[part%d]: from %d to %s" % (event_num, now_size+int(start), end))
            req = requests.get(self.url, stream=True, verify=False, headers=headers)
            with open(cache_filename, "ab") as cache:
                for chunk in req.iter_content(chunk_size=4096):
                    if chunk:
                        now_size += len(chunk)
                        cache.write(chunk)

    def calculate_download_speed(self):
        # 开始统计文件大小，计时，并计算速度
        lag_count = 5 # 计算过去 lag_count 次测量的平均速度
        file_list = [self.cache_dir + self.filename + ".part" + str(i) for i in range(self.blocks_num)]
        while not self.done:
            dwn_size = 0
            for f in file_list:
                try:
                    dwn_size += os.path.getsize(f)
                except:
                    pass
            self.downloaded_size.append(dwn_size)
            if len(self.downloaded_size) == lag_count:
                self.downloaded_size.pop(0)
            self.downloaded_time.append(time.time())
            if len(self.downloaded_time) == lag_count:
                self.downloaded_time.pop(0)
            s = self.downloaded_size[-1] - self.downloaded_size[0]
            t = self.downloaded_time[-1] - self.downloaded_time[0]
            if not t == 0:
                speed = s/1024/t
                percentage = self.downloaded_size[-1] / self.file_size * 100
                sys.stdout.write("\r[status] %.2f%% @ %.2fKB/s" % (percentage, speed))
            time.sleep(1)
        sys.stdout.write("\r[status] 100%\n")

    def sew_together(self):
        # 进入缝合阶段说明下载完成，因为之前一步有 .join() 卡着
        self.done = True
        with open(self.download_dir + self.filename, "ab") as file:
            for i in range(self.blocks_num):
                cache_filename = self.cache_dir + self.filename + ".part" + str(i)
                with open(cache_filename, "rb") as part:
                    file.write(part.read())
        print("the Beatles: all together now\nDownload complete.")

    def sha256(self):
        full_filename = self.download_dir+self.filename
        if os.path.exists(full_filename):
            with open(full_filename, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        else:
            return "File not found."


if __name__ == "__main__":
    # url = clipboard.get()
    # 剪贴板里什么都有，所以最好先判断一下 :-)
    # if url.startswith('http'):
    #     d = Downloader(url)
    #     d.start()

    url = "https://qd.myapp.com/myapp/qqteam/pcqq/QQ9.0.8_3.exe"
    d = Downloader(url, blocks_num=5)
    d.start()
