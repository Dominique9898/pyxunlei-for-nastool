from datetime import datetime
import hashlib
from io import BufferedReader, BytesIO
import json
import sys
import time
from typing import List
from urllib.parse import quote
from loguru import logger
from pydantic import BaseModel
import requests
from torrentool.api import Torrent
import re

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")


class TaskInfo(BaseModel):
    name: str
    file_name: str
    file_size: int
    updated_time: datetime
    progress: int
    real_path: str   # 路径
    speed: int
    created_time: datetime
    origin: dict  # api原始返回内容


class TaskFile(BaseModel):
    index: int
    file_name: str
    file_size: int


class NotLoginXunLeiAccount(Exception):
    pass


class PanAuthInvalid(Exception):
    pass


class XunLeiClient():
    def __init__(self, host: str, port: int, ssl: bool = False, device_name: str = '', download_root_dir: str = ''):
        """初始化迅雷客户端
        
        Args:
            host (str): 域名或IP
            port (int): 端口号
            ssl (bool): 是否启用HTTPS
            device_name (str): 设备名称，为空时使用第一个设备
            download_root_dir (str): 下载根目录名称，为空时使用第一个目录 例如: /downloads 则下载目录为 downloads
        """
        self._device_id = None
        self._token_str = None
        self._token_time = 0
        self.device_name = device_name
        self.http_endpoint = f"{'https' if ssl else 'http'}://{host}:{port}"
        
        # 创建session并测试连接
        self._session = self._create_session()
        # 获取device_id
        self.get_device_id()
        # 初始化下载目录
        self._init_download_directory(download_root_dir)

    @property
    def headers(self):
        return {
            'pan-auth': self.get_pan_auth(),
            'DNT': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'device-space': '',
            'content-type': 'application/json',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }

    def is_connected(self) -> bool:
        """测试与迅雷服务的连接是否正常"""
        try:
            logger.info("正在测试与迅雷服务的连接...")
            self._device_id = self.get_device_id()
            if not hasattr(self, '_parent_folder_id'):
                self._init_download_directory('')
            logger.info(f"初始化完成，设备ID: {self._device_id}")
            return True
        except Exception as e:
            logger.error(f"连接测试失败，错误信息: {str(e)}")
            return False

    def get_pan_auth(self):
        if self._token_str is not None and self._token_time + 600 > int(time.time()):
            return self._token_str
            
        try:
            url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/"
            logger.info(f"正在请求认证信息: {url}")
            
            resp = self._session.get(url, timeout=30)
            
            if resp.status_code != 200:
                logger.error(f"响应内容: {resp.text}")
                return ""
                
            uiauth = r'function uiauth\(value\){ return "(.*)" }'
            matches = re.findall(uiauth, resp.text)
            
            if matches:
                self._token_str = matches[0]
                self._token_time = int(time.time())
                return self._token_str
            else:
                logger.error(f"在响应中未找到令牌模式")
                return ""
            
        except Exception as e:
            logger.error(f"获取认证信息时出错: {e}")
            return ""

    def get_device_id(self, url_encode: bool = False) -> str:
        if self._device_id is not None:
            logger.debug(f"使用缓存的设备ID: {self._device_id}")
            return self._device_id
        
        try:
            logger.info("正在从服务器获取设备ID...")
            info_watch = "/webman/3rdparty/pan-xunlei-com/index.cgi/device/info/watch"
            token = self.get_pan_auth()
            
            if not token:
                raise ValueError("获取认证令牌失败")
            
            logger.debug(f"正在请求 {info_watch} 获取设备信息")
            req = self._session.post(
                self.http_endpoint + info_watch,
                headers={'pan-auth': token}, 
                timeout=30
            )
            
            if req.status_code != 200:
                logger.error(f"请求失败，状态码: {req.status_code}")
                logger.error(f"响应内容: {req.text}")
                req.raise_for_status()
            
            data = req.json()
            self._device_id = data.get("target")
            
            if not self._device_id:
                logger.error(f"响应中未找到设备ID: {data}")
                raise ValueError("响应中未找到设备ID")
            
            logger.info(f"成功获取设备ID: {self._device_id}")
            return self._device_id
        
        except requests.exceptions.RequestException as e:
            logger.error(f"获取设备ID时发生网络错误: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"获取设备ID时出错: {str(e)}")
            raise ValueError(f"获取设备ID失败: {str(e)}")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        try:
            if endpoint.startswith('http'):
                url = endpoint
            else:
                if not endpoint.startswith('/'):
                    endpoint = '/' + endpoint
                url = f"{self.http_endpoint}{endpoint}"
            
            headers = kwargs.pop('headers', self.headers)
            
            logger.info(f"正在发送 {method} 请求到: {url}")
            logger.debug(f"请求头: {headers}")
            if 'params' in kwargs:
                logger.debug(f"请求参数: {kwargs['params']}")
            if 'data' in kwargs:
                logger.debug(f"请求体: {kwargs['data']}")
            
            response = self._session.request(method, url, headers=headers, **kwargs)
            
            if response.status_code != 200:
                logger.error(f"请求失败，状态码: {response.status_code}")
                logger.error(f"响应头: {dict(response.headers)}")
                logger.error(f"响应内容: {response.text}")
            
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"响应状态码: {response.status_code}")
            logger.debug(f"响应内容: {result}")
            
            if result.get('error_code') == 403:
                raise PanAuthInvalid(result.get('error'))
            
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {str(e)}")
            logger.error(f"请求URL: {url}")
            raise

    def _init_download_directory(self, download_root_dir: str):
        """初始化下载目录
        
        Args:
            download_root_dir (str): 指定的下载目录名称。为空时使用第一个可用目录
            
        Raises:
            ValueError: 当找不到指定目录或无可用目录时抛出
            RequestException: 当API请求失败时抛出
        """
        logger.info(f"Initializing download directory. Specified dir: {download_root_dir}")
        
        try:
            # 确保有device_id
            if not self._device_id:
                self._device_id = self.get_device_id()
            
            # 获取所有可用目录
            endpoint = "webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/files"
            params = {
                "space": self._device_id,
                "limit": "200",
                "parent_id": "",
                "filters": "{\"kind\":{\"eq\":\"drive#folder\"}}",
                "page_token": "",
                "device_space": ""
            }
            
            data = self._make_request('GET', endpoint, params=params)
            files = data.get('files', [])
            
            if not files:
                logger.error("No download folders found in device")
                raise ValueError("No download folders found")
            
            logger.info(f"Found {len(files)} download folders: {[f.get('name') for f in files]}")
            
            # 选择下载目录
            if not download_root_dir:
                # 使用第一个可用目录
                first_folder = files[0]
                self._parent_folder_id = first_folder.get('id')
                self._parent_folder_name = first_folder.get('name')
                logger.info(f"Using default download folder: {self._parent_folder_name} (ID: {self._parent_folder_id})")
            else:
                # 查找指定名称的目录
                matching_folders = [f for f in files if f.get('name') == download_root_dir]
                
                if not matching_folders:
                    available_folders = ", ".join([f.get('name', '') for f in files])
                    error_msg = f"Download root dir '{download_root_dir}' not found. Available folders: {available_folders}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                folder = matching_folders[0]
                self._parent_folder_id = folder.get('id')
                self._parent_folder_name = folder.get('name')
                logger.info(f"Using specified folder: {self._parent_folder_name} (ID: {self._parent_folder_id})")
            
            if not self._parent_folder_id:
                raise ValueError("Failed to get valid folder ID")
                        
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch download directories: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Error initializing download directory: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def completed_tasks(self) -> List[TaskInfo]:
        """获取所有已经完成的任务

        Returns:
            List: 任务列表
        """
        url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/tasks?space={quote(self._device_id)}&page_token=&filters=%7B%22phase%22%3A%7B%22in%22%3A%22PHASE_TYPE_COMPLETE%22%7D%2C%22type%22%3A%7B%22in%22%3A%22user%23download-url%2Cuser%23download%22%7D%7D&limit=200&device_space="
        data = self._session.get(url, headers=self.headers).json()
        tasks = data.get('tasks')
        if not tasks:
            return []
        res = []
        for task in tasks:
            progress =  task.get('progress') if task.get('progress') else 0
            res.append(TaskInfo(
                name=task.get('name'),
                file_name=task.get('name'),
                file_size=int(task.get('file_size')),
                updated_time=task.get('updated_time'),
                progress=progress,
                real_path=task.get('params').get('real_path'),
                speed=int(task.get('params').get('speed',0)),
                created_time=task.get('created_time'),
                origin=task
            ))
        return res

    def uncompleted_tasks(self) -> List[TaskInfo]:
        """获取未完成的任务

        Returns:
            List[TaskInfo]: _description_
        """
        url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/tasks?space={quote(self._device_id)}&page_token=&filters=%7B%22phase%22%3A%7B%22in%22%3A%22PHASE_TYPE_PENDING%2CPHASE_TYPE_RUNNING%2CPHASE_TYPE_PAUSED%2CPHASE_TYPE_ERROR%22%7D%2C%22type%22%3A%7B%22in%22%3A%22user%23download-url%2Cuser%23download%22%7D%7D&limit=200&device_space="
        data = self._session.get(url, headers=self.headers).json()
        tasks = data.get('tasks')
        if not tasks:
            return []
        res = []
        for task in tasks:
            progress =  task.get('progress') if task.get('progress') else 0
            res.append(TaskInfo(
                file_name=task.get('name'),
                name=task.get('name'),
                file_size=int(task.get('file_size')),
                updated_time=task.get('updated_time'),
                progress=progress,
                real_path=task.get('params').get('real_path'),
                speed=int(task.get('params').get('speed',0)),
                created_time=task.get('created_time'),
                origin=task
            ))
        return res

    def download_http_task(self) -> bool:
        """下载http连接
        暂不实现
        Returns:
            bool: _description_
        """
        return False

    def download_magnetic(self, magnetic_link: str, sub_dir: str = '', preprocess_files=None) -> int:
        """下载磁力链接

        Args:
            magnetic_link (str): 磁力链接
            sub_dir (str, optional): 子目录，不为空时将新建子目录下载 Defaults to ''.
            preprocess_files (_type_, optional): 添加任务的回调函数，会传入文件列表，要求返回文件列表.可以在此函数中实现过滤下载文件的操作 Defaults to None.

        Returns:
            int: 三种情况:
                0: 失败
                1: 成功
                2: 已存在跳过
        """
        try:
            logger.info(f"开始处理磁力链接下载: {magnetic_link}")

            # 提取文件 list
            url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/resource/list?device_space="
            body = {"urls": magnetic_link}
            
            logger.info("正在获取资源列表...")
            response = self._session.post(
                url, headers=self.headers, data=json.dumps(body), timeout=60)
            
            if response.status_code != 200:
                logger.error(f"获取资源列表失败: HTTP {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return 0
            
            data = response.json()
            if not data.get('list', {}).get('resources'):
                logger.error(f"未找到资源: {data}")
                return 0
            
            task_name = data.get('list').get('resources')[0].get('name')
            logger.info(f"获取到任务名称: {task_name}")

            # 检查任务是否已存在
            all_task_names = set(
                [i.name for i in self.completed_tasks() + self.uncompleted_tasks()])
            if task_name in all_task_names:
                logger.info(f"任务已存在，跳过: {task_name}")
                return 2

            # 获取文件列表
            task_file_count = data.get('list').get('resources')[0].get('file_count')
            task_files = []
            # 递归处理
            def helper(resources):
                for resource in resources:
                    if resource.get('is_dir'):
                        helper(resource.get('dir').get('resources'))
                    else:
                        if not resource.get('file_index'):
                            file_index = 0
                        else:
                            file_index = resource.get('file_index')
                        task_files.append(
                            TaskFile(
                                index=file_index,
                                file_size=resource.get('file_size'),
                                file_name=resource.get('name')
                            )
                        )
            root_resources = data.get('list').get('resources')
            helper(root_resources)
            if callable(preprocess_files):
                task_files = preprocess_files(task_files)
            sub_file_index = [str(i.index) for i in task_files]

            target_parent_id = self._parent_folder_id
            # 创建子目录
            if sub_dir:
                if "/" in sub_dir:
                    logger.error("Multilevel subdirectories are not supported")
                    return False
                body = {"parent_id": self._parent_folder_id, "name": sub_dir,
                        "space": self._device_id, "kind": "drive#folder"}
                response = self._session.post(
                    f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/files?device_space=", headers=self.headers, data=json.dumps(body))
                target_parent_id = response.json().get('file').get('id')

            logger.info(f"正在提交下载任务: {task_name}")
            body = {
                "type": "user#download-url",
                "name": task_name,
                "file_name": task_name,
                "file_size": str(sum([i.file_size for i in task_files])),
                "space": self._device_id,
                "params": {
                    "target": self._device_id,
                    "url": magnetic_link,
                    "total_file_count": str(task_file_count),
                    "parent_folder_id": target_parent_id,
                    "sub_file_index": ",".join(sub_file_index),
                    "file_id": ""
                }
            }
            
            response = self._session.post(
                f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/drive/v1/task?device_space=",
                headers=self.headers,
                data=json.dumps(body)
            )
            
            result = response.json()
            if result.get('HttpStatus') == 0:
                logger.info(f"任务创建成功: {task_name}")
                return 1
            else:
                logger.error(f"任务创建失败: {result}")
                return 0
            
        except Exception as e:
            logger.exception(f"下载磁力链接时发生错误: {str(e)}")
            return 0

    def download_torrent(self, torrent_file_path: str,sub_dir:str='',preprocess_files=None) -> int:
        """_summary_

        Args:
            torrent_file_path (str): _description_

        Returns:
            int: _description_
        """
        magnet_link = self._torrent2magnet(torrent_file_path)
        return self.download_magnetic(magnet_link,sub_dir,preprocess_files)

    def _torrent2magnet(self, file_path: str) -> str:
        """种子转磁力

        Args:
            torrent_body (bytes): _description_

        Returns:
            str: _description_
        """
        torrent = Torrent.from_file(file_path)
        trs = torrent.announce_urls

        trs = '&'.join([quote(tr[0]) for tr in trs])
        return torrent.magnet_link + "&" + trs

    def filter_file_by_size(self, task_files: List[TaskFile], min_size: int = 500 * 1024 * 1024, max_size: int = 40 * 1024 * 1024 * 1024) -> List[TaskFile]:
        """preprocess_files参数内置函数，通过文件大小过滤文件

        Args:
            task_files (List[TaskFile]): _description_
            min_size (int, optional): _description_. Defaults to 500*1024*1024.
            max_size (int, optional): _description_. Defaults to 40*1024*1024*1024.

        Returns:
            List[TaskFile]: _description_
        """
        if not task_files:
            return []
        return [i for i in task_files if min_size <= i.file_size <= max_size]

    def delete_task(self, task_id: str) -> bool:
        """删除指定的下载任务

        Args:
            task_id (str): 任务ID

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        try:
            logger.info(f"Deleting task with ID: {task_id}")
            
            if not self._device_id:
                self._device_id = self.get_device_id()
            
            url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/method/patch/drive/v1/task"
            params = {
                'pan_auth': self.get_pan_auth(),
                'device_space': ''
            }
            
            data = {
                "space": self._device_id,
                "type": "user#download-url",
                "id": task_id,
                "set_params": {
                    "spec": "{\"phase\":\"delete\"}"
                }
            }
            
            response = self._session.post(
                url, 
                params=params,
                headers=self.headers,
                json=data
            )
            
            if response.status_code != 200:
                logger.error(f"Request failed with status code: {response.status_code}")
                response.raise_for_status()
                
            result = response.json()
            
            if result.get('error_code', 0) == 0:
                logger.info(f"Successfully deleted task: {task_id}")
                return True
            else:
                logger.error(f"Failed to delete task: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {str(e)}")
            return False

    def pause_task(self, task_id: str) -> bool:
        """暂停指定的下载任务

        Args:
            task_id (str): 任务ID

        Returns:
            bool: 暂停成功返回True，失败返回False
        """
        try:
            logger.info(f"暂停任务，ID: {task_id}")
            
            if not self._device_id:
                self._device_id = self.get_device_id()
            
            url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/method/patch/drive/v1/task"
            params = {
                'pan_auth': self.get_pan_auth(),
                'device_space': ''
            }
            
            data = {
                "space": self._device_id,
                "type": "user#download-url",
                "id": task_id,
                "set_params": {
                    "spec": "{\"phase\":\"pause\"}"
                }
            }
            
            response = self._session.post(
                url,
                params=params,
                headers=self.headers,
                json=data
            )
            
            result = response.json()
            
            if result.get('error_code', 0) == 0:
                logger.info(f"成功暂停任务: {task_id}")
                return True
            else:
                logger.error(f"暂停任务失败: {result}")
                return False
            
        except Exception as e:
            logger.error(f"暂停任务 {task_id} 时发生错误: {str(e)}")
            return False

    def start_task(self, task_id: str) -> bool:
        """开始/继续指定的下载任务

        Args:
            task_id (str): 任务ID

        Returns:
            bool: 开始成功返回True，失败返回False
        """
        try:
            logger.info(f"开始任务，ID: {task_id}")
            
            if not self._device_id:
                self._device_id = self.get_device_id()
            
            url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/method/patch/drive/v1/task"
            params = {
                'pan_auth': self.get_pan_auth(),
                'device_space': ''
            }
            
            data = {
                "space": self._device_id,
                "type": "user#download-url",
                "id": task_id,
                "set_params": {
                    "spec": "{\"phase\":\"running\"}"
                }
            }
            
            response = self._session.post(
                url,
                params=params,
                headers=self.headers,
                json=data
            )
            
            result = response.json()
            
            if result.get('error_code', 0) == 0:
                logger.info(f"成功开始任务: {task_id}")
                return True
            else:
                logger.error(f"开始任务失败: {result}")
                return False
            
        except Exception as e:
            logger.error(f"开始任务 {task_id} 时发生错误: {str(e)}")
            return False

    def _create_session(self) -> requests.Session:
        """创建并配置 requests session"""
        session = requests.Session()
        
        session.auth = ('licheng', '996633')
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        session.headers.update(headers)
        
        try:
            login_url = f"{self.http_endpoint}/webman/3rdparty/pan-xunlei-com/index.cgi/"
            logger.info(f"正在获取初始Cookie: {login_url}")
            
            response = session.get(login_url)
            logger.info(f"初始响应状态码: {response.status_code}")
            logger.info(f"获取到的Cookie: {dict(session.cookies)}")
            
            if response.status_code == 200:
                logger.info("成功获取初始Cookie")
            else:
                logger.error(f"获取初始Cookie失败，状态码: {response.status_code}")
                
        except Exception as e:
            logger.error(f"初始化Cookie时发生错误: {e}")
        
        return session
