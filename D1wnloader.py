# coding: utf-8
from urllib import request
from urllib import parse
import urllib3
import requests
import threading
import os
import hashlib
import time
import sys
# 在手机上跑 Pythonista 引入 clipboard 比较方便
# import clipboard

# 忽略警告
urllib3.disable_warnings()

class D1wnloader:
    def __init__(self, url, download_dir="./", blocks_num=5, max_retry_times=5):
        self.url = url
        filename = self.url.split("/")[-1]
        filename = parse.unquote(filename)
        self.filename = filename
        self.download_dir = download_dir
        self.blocks_num = blocks_num
        self.max_retry_times = max_retry_times
        self.retry_times = 0
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
        sys.stdout.write("----- D1wnloader [v1.0] -----\n[url] %s\n[path] %s\t[size] %s\n" % 
                        (self.url, self.download_dir + self.filename, readable_size))

    def get_size(self):
        with request.urlopen(self.url) as req:
            content_length = req.headers["Content-Length"]
            return int(content_length)

    def get_readable_size(self, size):
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        unit_index = 0
        K = 1024.0
        while size >= K:
            size = size / K
            unit_index += 1
        return "%.1f %s" % (size, units[unit_index])

    def get_ranges(self):
        ranges = []
        offset = int(self.file_size / self.blocks_num)
        for i in range(self.blocks_num):
            if i == self.blocks_num - 1:
                ranges.append((i * offset, self.file_size - 1))
            else:
                ranges.append((i * offset, (i + 1) * offset - 1))
        return ranges

    def start(self):
        if self.retry_times <= self.max_retry_times:
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
        else:
            sys.stdout.write("I tried, now, tired\n")

    def download(self, start, end, event_num):
        cache_filename = self.cache_dir + self.filename + ".part_" + str(event_num) + "_" + str(self.blocks_num)
        total_size = end - start + 1
        if os.path.exists(cache_filename):
            now_size = os.path.getsize(cache_filename)
        else:
            now_size = 0
        if total_size - now_size > 0:
            headers = {'Range': 'Bytes=%d-%s' % (now_size+int(start), end), 'Accept-Encoding': '*'}
            sys.stdout.write("[part%d] from %d to %s\n" % (event_num, now_size+int(start), end))
            req = requests.get(self.url, stream=True, verify=False, headers=headers)
            with open(cache_filename, "ab") as cache:
                for chunk in req.iter_content(chunk_size=4096):
                    if chunk:
                        now_size += len(chunk)
                        cache.write(chunk)

    def calculate_download_speed(self):
        # 开始统计文件大小，计时，并计算速度
        lag_count = 10 # 计算过去 lag_count 次测量的平均速度
        file_list = [self.cache_dir + self.filename + ".part_" + str(i) + "_" + str(self.blocks_num) for i in range(self.blocks_num)]
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
                sys.stdout.write("\r[status] %.2f%% @ %.2fKB/s          " % (percentage, speed))
                sys.stdout.flush()
            time.sleep(1)
        # sys.stdout.write("\r[status] the Beatles: all together now\n")
        sys.stdout.flush()

    def sew_together(self):
        # 进入缝合阶段说明下载完成，因为之前一步有 .join() 卡着
        complete_flag = True # 用于标记最后是否计算 SHA-256
        self.done = True
        full_filename = self.download_dir + self.filename
        if os.path.exists(full_filename):
            os.remove(full_filename)
        ranges = self.get_ranges()
        with open(full_filename, "ab") as file:
            for i in range(self.blocks_num):
                cache_filename = self.cache_dir + self.filename + ".part_" + str(i) + "_" + str(self.blocks_num)
                start, end = ranges[i]
                tiger = end - start + 1 # 理想
                cat = os.path.getsize(cache_filename) # 现实
                if cat != tiger: # 照猫画虎：画的不一样
                    sys.stdout.write("\r[status] oops... retry now\n")
                    complete_flag = False
                    self.retry_times += 1
                    self.start()
                    break
                with open(cache_filename, "rb") as part:
                    file.write(part.read())
        if complete_flag:
            sys.stdout.write("\r[SHA-256] %s\nDownload complete.\n" % self.sha256())

    def sha256(self):
        full_filename = self.download_dir+self.filename
        if os.path.exists(full_filename):
            with open(full_filename, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        else:
            return "File not found."


if __name__ == "__main__":
    url = "https://qd.myapp.com/myapp/qqteam/pcqq/QQ9.0.8_3.exe"
    d = D1wnloader(url)
    d.start()
