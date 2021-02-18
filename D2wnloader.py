#-*- coding: utf-8 -*- 
import threading, time
from urllib import request, parse
import requests
import os, sys, glob
import hashlib

class DLWorker:
    def __init__(self, name:str, url:str, range_start, range_end, cache_dir, finish_callback):
        self.name = name
        self.url = url
        self.cache_filename = os.path.join(cache_dir, name + ".d2l")
        self.range_start = range_start # 固定不动
        self.range_end = range_end # 固定不动
        self.range_curser = range_start # curser 所指尚未开始
        self.finish_callback = finish_callback # 通知调用 DLWorker 的地方
        self.terminate_flag = False # 该标志用于终结自己
        self.FINISH_TYPE = "" # DONE 完成工作, HELP 需要帮忙, RETIRE 不干了

    def __run(self):
        chunk_size = 1*1024 # 1 kb
        headers = {'Range': f'Bytes={self.range_curser}-{self.range_end}', 'Accept-Encoding': '*'}
        req = requests.get(self.url, stream=True, headers=headers)
        with open(self.cache_filename, "wb") as cache:
            for chunk in req.iter_content(chunk_size=chunk_size):
                # self.continue_event.wait()
                if self.terminate_flag:
                    break
                cache.write(chunk)
                self.range_curser += len(chunk)
        if not self.terminate_flag: # 只有正常退出才能标记 DONE，但是三条途径都经过此处
            self.FINISH_TYPE = "DONE"
        self.finish_callback(self) # 执行回调函数，根据 FINISH_TYPE 结局不同

    def start(self):
        threading.Thread(target=self.__run).start()

    def help(self):
        self.FINISH_TYPE = "HELP"
        self.terminate_flag = True

    def retire(self):
        self.FINISH_TYPE = "RETIRE"
        self.terminate_flag = True

    def __lt__(self, another):
        """用于排序"""
        return self.range_start < another.range_start

    def get_progress(self):
        """获得进度"""
        _progress = {
            "curser": self.range_curser,
            "start": self.range_start,
            "end": self.range_end
        }
        return _progress

class D2wnloader:
    def __init__(self, url:str, download_dir:str=f".{os.sep}d2l{os.sep}", blocks_num:int=8):
        assert 0 <= blocks_num <= 32
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
        self.cache_dir = f".{os.sep}.d2lcache{os.sep}"
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)
        elif os.path.isfile(self.cache_dir):
            os.remove(self.cache_dir)
            os.mkdir(self.cache_dir)
        # 分块下载
        self.startdlsince = time.time()
        self.file_size = self.__get_size()
        self.workers = [] # 装载 DLWorker
        self.AAEK = self.__get_AAEK_from_cache() # 需要确定 self.file_size 和 self.block_num
        # 测速
        self.__done = threading.Event()
        self.__download_record = []
        threading.Thread(target=self.__supervise).start()
        # 显示基本信息
        readable_size = self.__get_readable_size(self.file_size)
        pathfilename = self.download_dir + self.filename
        sys.stdout.write(f"----- D2wnloader [v2.0.b6] -----\n[url] {self.url}\n[path] {pathfilename}\n[size] {readable_size}\n")
    
    def __get_size(self):
        with request.urlopen(self.url) as req:
            content_length = req.headers["Content-Length"]
            return int(content_length)

    def __get_readable_size(self, size):
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        unit_index = 0
        K = 1024.0
        while size >= K:
            size = size / K
            unit_index += 1
        return "%.1f %s" % (size, units[unit_index])

    def __get_cache_filenames(self):
        return glob.glob(f"{self.cache_dir}{self.filename}.*.d2l")

    def __get_ranges_from_cache(self):
        # 形如 ./cache/filename.1120.d2l
        ranges = []
        for filename in self.__get_cache_filenames():
            size = os.path.getsize(filename)
            if size > 0:
                cache_start = int(filename.split(".")[-2])
                cache_end = cache_start + size - 1
                ranges.append((cache_start, cache_end))
        ranges.sort(key = lambda x: x[0]) # 排序
        return ranges

    def __get_AAEK_from_cache(self):
        ranges = self.__get_ranges_from_cache() # 缓存文件里的数据
        AAEK = [] # 根据 ranges 和 self.file_size 生成 AAEK
        if len(ranges) == 0:
            AAEK.append((0, self.file_size - 1))
        else:
            for i, (start, end) in enumerate(ranges):
                if i == 0:
                    if start > 0:
                        AAEK.append((0, start - 1))
                next_start = self.file_size if i == len(ranges) - 1 else ranges[i+1][0]
                if end < next_start - 1:
                    AAEK.append((end + 1, next_start - 1))
        return AAEK

    def __increase_ranges_slice(self, ranges:list, minimum_size=1024*1024):
        """增加分块数目，小于 minimum_size 就不再分割了"""
        assert len(ranges) > 0
        block_size = [end - start + 1 for start, end in ranges]
        index_of_max = block_size.index(max(block_size))
        start, end = ranges[index_of_max]
        halfsize = block_size[index_of_max] // 2
        if halfsize >= minimum_size:
            new_ranges = [x for i,x in enumerate(ranges) if i != index_of_max]
            new_ranges.append((start, start+halfsize))
            new_ranges.append((start+halfsize+1, end))
        else:
            new_ranges = ranges
        return new_ranges

    def __ask_for_work(self, worker_num:int):
        """申请工作，返回 [work_range]，从 self.AAEK 中扣除。没工作的话返回 []。"""
        assert worker_num > 0
        task = []
        aaek_num = len(self.AAEK)
        if aaek_num == 0: # 没任务了
            # TODO 这里挑 size 大的 DLWorker 调用 help
            self.__share_the_burdern()
            return []
        if aaek_num >= worker_num: # 数量充足，直接拿就行了
            for _ in range(worker_num):
                task.append(self.AAEK.pop(0))
        else: # 数量不足，需要切割
            slice_num = worker_num - aaek_num # 需要分割几次
            task = self.AAEK # 这个时候 task 就不可能是 [] 了
            self.AAEK = []
            for _ in range(slice_num):
                task = self.__increase_ranges_slice(task)
        task.sort(key=lambda x: x[0])
        return task

    def __share_the_burdern(self, minimum_size=1024*1024):
        """找出工作最繁重的 worker，调用他的 help。回调函数中会将他的任务一分为二。"""
        max_size = 0
        max_size_name = ""
        for w in self.workers:
            p = w.get_progress()
            size = p["end"] - p["curser"] + 1
            if size > max_size:
                max_size = size
                max_size_name = w.name
        if max_size >= minimum_size:
            for w in self.workers:
                if w.name == max_size_name:
                    w.help()
                    break

    def __give_back_work(self, worker:DLWorker):
        """接纳没干完的工作。需要按 size 从小到大排序。"""
        progress = worker.get_progress()
        curser = progress["curser"]
        end = progress["end"]
        if curser <= end: # 校验一下是否是合理值
            self.AAEK.append((curser, end))
            self.AAEK.sort(key=lambda x: x[0])

    def __give_me_a_worker(self, start, end):
        worker = DLWorker(name=f"{self.filename}.{start}", 
                          url=self.url, range_start=start, range_end=end, cache_dir=self.cache_dir,
                          finish_callback=self.__on_dlworker_finish)
        return worker

    def __whip(self, worker:DLWorker):
        """鞭笞新来的 worker，让他去工作"""
        self.workers.append(worker)
        self.workers.sort()
        worker.start()

    def __on_dlworker_finish(self, worker:DLWorker):
        assert worker.FINISH_TYPE != ""
        self.workers.remove(worker)
        if worker.FINISH_TYPE == "HELP": # 外包
            self.__give_back_work(worker)
            self.workaholic(2)
        elif worker.FINISH_TYPE == "DONE": # 完工
            # 再打一份工，也可能打不到
            self.workaholic(1)
        elif worker.FINISH_TYPE == "RETIRE": # 撂挑子
            # 把工作添加回 AAEK，离职不管了。
            self.__give_back_work(worker)
        # 下载齐全，开始组装
        if self.workers == [] and self.__get_AAEK_from_cache() == []:
            self.__sew()

    def start(self):
        # TODO 尝试整理缓存文件夹内的相关文件
        # 召集 worker
        for start, end in self.__ask_for_work(self.blocks_num):
            worker = self.__give_me_a_worker(start, end)
            self.__whip(worker)

    def stop(self):
        for w in self.workers:
            w.retire()
        while len(self.workers) != 0:
            time.sleep(0.5)

    def workaholic(self, n=1):
        """九九六工作狂。如果能申请到，就地解析；申请不到，__give_me_a_worker 会尝试将一个 worker 的工作一分为二；"""
        for s, e in self.__ask_for_work(n):
            worker = self.__give_me_a_worker(s, e)
            self.__whip(worker)

    def restart(self):
        self.stop()
        self.start()

    def __supervise(self):
        """万恶的督导：监视下载速度、进程数；提出整改意见；"""
        REFRESH_INTERVAL = 1 # 每多久输出一次监视状态
        LAG_COUNT = 10 # 计算过去多少次测量的平均速度
        WAIT_TIMES_BEFORE_RESTART = 30 # 乘以时间就是等待多久执行一次 restart
        SPEED_DEGRADATION_PERCENTAGE = 0.5 # 速度下降百分比
        self.__download_record = []
        maxspeed = 0
        wait_times = WAIT_TIMES_BEFORE_RESTART
        while not self.__done.is_set():
            dwn_size = sum([os.path.getsize(cachefile) for cachefile in self.__get_cache_filenames()])
            self.__download_record.append({"timestamp": time.time(), "size": dwn_size})
            if len(self.__download_record) > LAG_COUNT:
                self.__download_record.pop(0)
            s = self.__download_record[-1]["size"] - self.__download_record[0]["size"]
            t = self.__download_record[-1]["timestamp"] - self.__download_record[0]["timestamp"]
            if not t == 0:
                speed = s / t
                readable_speed = self.__get_readable_size(speed) # 变成方便阅读的样式
                percentage = self.__download_record[-1]["size"] / self.file_size * 100
                status_msg = f"\r[info] {percentage:.1f} % | {readable_speed}/s | {len(self.workers)}/{threading.active_count()} {(time.time()-self.startdlsince):.0f}s          "
                sys.stdout.write(status_msg)
                # 监测下载速度下降
                maxspeed = max(maxspeed, speed)
                # 当满足：该监测了 + 未完成 + 速度下降百分比达到了阈值 + 速度低于 1 MB/s
                if wait_times < 0 and not self.__done.is_set() and (maxspeed - speed) / maxspeed > SPEED_DEGRADATION_PERCENTAGE and speed < 1024*1024:
                    sys.stdout.write("\n[info] Speed degradation is detected\n[TODO] Restarting, please wait...\n")
                    self.restart()
                    maxspeed = 0
                    wait_times = WAIT_TIMES_BEFORE_RESTART
                else:
                    wait_times -= 1
            time.sleep(REFRESH_INTERVAL)

    def __sew(self):
        chunk_size = 10*1024*1024
        with open(f"{self.download_dir}{self.filename}", "wb") as f:
            for start, _ in self.__get_ranges_from_cache():
                cache_filename = f"{self.cache_dir}{self.filename}.{start}.d2l"
                with open(cache_filename, "rb") as cache_file:
                    data = cache_file.read(chunk_size)
                    while data:
                        f.write(data)
                        f.flush()
                        data = cache_file.read(chunk_size)
        self.clear()
        self.__done.set()
        sys.stdout.write(f"\n[md5] {self.md5()}\n[info] D2wnloaded\n")
    
    def md5(self):
        chunk_size = 1024*1024
        filename = f"{self.download_dir}{self.filename}"
        md5 = hashlib.md5()
        with open(filename, "rb") as f:
            data = f.read(chunk_size)
            while data:
                md5.update(data)
                data = f.read(chunk_size)
        return md5.hexdigest()

    def clear(self, all_cache=False):
        if all_cache: # TODO 需要交互提醒即将删除的文件夹 [Y]/N 确认。由于不安全，先不打算实现。
            pass
        else:
            for filename in self.__get_cache_filenames():
                os.remove(filename)

if __name__ == "__main__":
    # url = "https://mirrors.tuna.tsinghua.edu.cn/linuxmint-cd/stable/20.1/linuxmint-20.1-cinnamon-64bit.iso"
    url = "https://qd.myapp.com/myapp/qqteam/pcqq/QQ9.0.8_3.exe"
    d2l = D2wnloader(url)
    d2l.start()
