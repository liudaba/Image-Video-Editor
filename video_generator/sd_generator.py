# -*- coding: utf-8 -*-
"""批量SD图像生成器 - 从 My-Video Generator.py 提取"""

import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import Config, get_http_session
from .cache import image_cache


class BatchSDGenerator:
    """批量SD图像生成器 - 支持连接池和并发"""
    
    def __init__(self, api_url=None, max_workers=4):
        self.api_url = api_url or Config.SD_API_BASE_URL
        self.max_workers = max_workers
    
    def generate_batch(self, prompts_data, width=768, height=512, 
                      steps=28, cfg_scale=7.5, progress_callback=None, log_callback=None):
        """批量生成图像 - 使用队列控制避免SD过载
        
        Args:
            prompts_data: [(idx, prompt, negative_prompt), ...]
            width, height: 图像尺寸
            steps: 采样步数
            cfg_scale: CFG比例
            progress_callback: 进度回调 (completed, total, from_cache)
            log_callback: 日志回调 (message)
        
        Returns:
            按索引排列的图像数据列表
        """
        results = [None] * len(prompts_data)
        completed = 0
        total = len(prompts_data)
        lock = threading.Lock()
        
        # SD WebUI 同时处理太多请求会超时，限制并发数
        # 建议：根据GPU显存调整，8GB显存建议4线程，12GB+建议6-8线程
        effective_workers = min(self.max_workers, 6)  # 最多6个实际并发
        
        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
        
        def generate_single(item):
            idx, prompt, negative_prompt = item
            start_time = time.time()
            
            try:
                # 检查图像缓存
                cache_key = hashlib.md5(f"{prompt}_{negative_prompt or ''}_{width}_{height}_{steps}_{cfg_scale}".encode()).hexdigest()
                cached = image_cache.get(cache_key)
                if cached:
                    log(f"📷 [{idx+1}/{total}] 缓存命中，跳过生成")
                    with lock:
                        results[idx] = cached
                    return idx, cached, True, 0
                
                log(f"📷 [{idx+1}/{total}] 开始生成...")
                
                # 增加超时时间到120秒，并添加重试
                max_retries = 2
                for retry in range(max_retries):
                    try:
                        response = get_http_session().post(
                            f"{self.api_url}/sdapi/v1/txt2img",
                            json={
                                "prompt": prompt,
                                "negative_prompt": negative_prompt or "",
                                "width": width,
                                "height": height,
                                "steps": steps,
                                "cfg_scale": cfg_scale,
                                "batch_size": 1,
                                "sampler_name": "DPM++ 2M",
                                "scheduler": "Karras",
                                "override_settings": {
                                    "sd_vae": "vae-ft-mse-840000-ema-pruned.safetensors"
                                }
                            },
                            timeout=180  # 增加到180秒超时
                        )
                        
                        elapsed = time.time() - start_time
                        
                        if response.status_code == 200:
                            result = response.json()
                            images = result.get('images', [])
                            if images:
                                # 缓存图像
                                image_cache.set(cache_key, images[0])
                                with lock:
                                    results[idx] = images[0]
                                log(f"   ✅ 完成 (耗时 {elapsed:.1f}s)")
                                return idx, images[0], False, elapsed
                            else:
                                log(f"   ❌ 失败: 无图像数据")
                                return idx, None, False, elapsed
                        else:
                            log(f"   ❌ 失败: HTTP {response.status_code}")
                            if retry < max_retries - 1:
                                log(f"   🔄 重试 {retry+1}/{max_retries}...")
                                time.sleep(2)
                                continue
                            return idx, None, False, elapsed
                            
                    except Exception as e:
                        if retry < max_retries - 1:
                            log(f"   ⚠️ 请求失败，重试 {retry+1}/{max_retries}...")
                            time.sleep(2)
                            continue
                        raise
                    
            except Exception as e:
                elapsed = time.time() - start_time
                log(f"   ❌ 错误: {str(e)[:80]}")
                return idx, None, False, elapsed
        
        log(f"🚀 启动批量生成: {total}张图像，实际并发{effective_workers}线程 (设置{self.max_workers}线程)")
        log(f"💡 提示: 如果继续超时，请在高级设置中将线程数改为4-6")
        
        # 使用限制并发数的线程池
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = {executor.submit(generate_single, item): item[0] for item in prompts_data}
            
            for future in as_completed(futures):
                idx, image_data, from_cache, elapsed = future.result()
                # 结果已在generate_single中写入results
                with lock:
                    completed += 1
                
                if progress_callback:
                    try:
                        progress_callback(completed, total, from_cache)
                    except Exception as e:
                        log(f"进度回调错误: {e}")
        
        # 统计结果
        success_count = sum(1 for r in results if r is not None)
        log(f"📊 批量生成完成: {success_count}/{total} 成功")
        
        if success_count < total:
            log(f"⚠️ {total - success_count}张图像生成失败，建议：")
            log(f"   1. 降低线程数到4-6")
            log(f"   2. 检查SD WebUI是否正常运行")
            log(f"   3. 降低图像分辨率或步数")
        
        return results

