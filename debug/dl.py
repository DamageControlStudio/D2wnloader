from D2wnloader import D2wnloader

# zero.file md5 should be 1f5039e50bd66b290c56684d8550c6c2

url = "http://zero.local:37213/dl/zero.file"
d2l = D2wnloader(url=url, blocks_num=5)
d2l.start()


""" 下载到了奇怪的东西，应该判断 response code
<html>
<head><title>502 Bad Gateway</title></head>
<body bgcolor="white">
<center><h1>502 Bad Gateway</h1></center>
<hr><center>nginx/1.14.2</center>
</body>
</html>
"""