# pyxunlei
基于Docker版本的[Xunlei API Client](https://github.com/cnk3x/xunlei)，可作为 [NAStool](https://github.com/NAStool/nas-tools) 的下载器插件使用。

## 支持版本
python@3.10
迅雷Docker@3.21.0

## 安装方法

### 通过 PyPI 安装
```bash
pip install pyxunlei-for-nastool
```

### 从源码安装
```bash
poetry shell
poetry install
```

## 使用方法
```python
from pyxunlei import XunleiClient

#  初始化时支持以下参数:
#  host (str): 域名或IP
#  port (int): 端口号
#  ssl (bool): 是否启动HTTPS
#  device_name (str): 设备名称，当同一个账号下绑定了多个远程迅雷，可指定设备名称，设备名称可在迅雷APP查看
#      例如：群晖-xunlei
#      device_name为空时使用第一个设备.
#  download_root_dir(str): 下载根目录的目录名称，可以在web页面上查看，如不填写则默认选择第一个(一般是迅雷下载)
xunlei_client = XunLeiClient(
        '192.168.1.21', 2345, device_name="群晖-xunlei-")

# 获取已完成任务列表
completed_tasks = xunlei_client.completed_tasks()

# 获取未完成任务列表
uncompleted_tasks = xunlei_client.uncompleted_tasks()

# 提交磁力链接
magnetic_link = "磁力链接"
sub_dir = "子目录"  # 为空时则不创建子目录
preprocess_file = xunlei_client.filter_file_by_size  # 指定预处理文件函数，可使用内置的filter_file_by_size过滤掉小于500M以及大于40G的文件
xunlei_client.download_magnetic(magnetic_link, sub_dir, preprocess_file)

# 提交种子链接
torrent_file_path = "your.torrent"  # 种子文件路径
xunlei_client.download_torrent(torrent_file_path, sub_dir, preprocess_file)

# 任务管理
task_id = "任务ID"  # 创建任务时会返回task_id

# 暂停任务
xunlei_client.pause_task(task_id)

# 开始/继续任务
xunlei_client.start_task(task_id)

# 删除任务
xunlei_client.delete_task(task_id)
```

## 注意事项
1. 需要先安装并运行 [Docker版迅雷](https://github.com/cnk3x/xunlei)
2. 默认使用admin/admin作为登录凭证，如有修改请更新代码中的认证信息
3. 可以拿来作为集成到NAStool下载器插件使用
```

