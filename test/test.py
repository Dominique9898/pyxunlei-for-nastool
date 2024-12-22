import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxunlei.pyxunlei import XunLeiClient
from loguru import logger

if __name__ == "__main__":
    try:
        logger.info("开始测试迅雷下载...")
        
        xunlei_client = XunLeiClient(
            '192.168.1.21', 2345, device_name="群晖-xunlei-")
            
        logger.info("正在添加磁力链接下载任务...")
        result = xunlei_client.download_magnetic(
            'magnet:?xt=urn:btih:8F2977E2E2D2F351FC5C57FC25AEC39EBE4F3822&dn=The.Mortal.Instruments.The.Shadow.Hunter.Chronicles.S01E01.720p.WEB-DL.DDP5.1.Atmos.HEVC.H.265-RARBG'
        )
        
        logger.info(f"下载任务添加结果: {result}")
        if result == 1:
            logger.info("下载任务添加成功")
        elif result == 2:
            logger.info("任务已存在，已跳过")
        else:
            logger.error("下载任务添加失败")
        
    except Exception as e:
        logger.exception(f"测试过程中发生错误: {str(e)}")
        sys.exit(1)
