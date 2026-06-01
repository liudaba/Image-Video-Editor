# -*- coding: utf-8 -*-
"""批量SD图像生成器 - 从 My-Video Generator.py 提取"""

import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import Config, get_http_session
from .cache import image_cache
from .model_profiles import get_model_profile, detect_model_type


class BatchSDGenerator:
    """批量SD图像生成器 - 支持连接池和并发"""

    def __init__(self, api_url=None, max_workers=4):
        self.api_url = api_url or Config.SD_API_BASE_URL
        self.max_workers = max_workers

    def generate_batch(self, prompts_data, width=768, height=512,
                      model_name="", progress_callback=None, log_callback=None):
        """批量生成图像 - 使用队列控制避免SD过载

        Args:
            prompts_data: [(idx, prompt, negative_prompt), ...]
            width, height: 图像尺寸
            model_name: SD模型名称，用于获取模型配置
            progress_callback: 进度回调 (completed, total, from_cache)
            log_callback: 日志回调 (message)

        Returns:
            按索引排列的图像数据列表
        """
        model_profile = get_model_profile(model_name)
        gen_params = model_profile["params"]
        needs_negative = model_profile["needs_negative"]
        use_vae = model_profile.get("use_vae_override", False)
        vae_name = model_profile.get("vae_name", "")
        model_type = detect_model_type(model_name)

        results = [None] * len(prompts_data)
        completed = 0
        total = len(prompts_data)
        lock = threading.Lock()

        effective_workers = min(self.max_workers, 4)

        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        def generate_single(item):
            idx, prompt, negative_prompt = item
            start_time = time.time()

            try:
                cache_key = hashlib.md5(
                    f"{prompt}_{negative_prompt or ''}_{width}_{height}_{model_name}".encode()
                ).hexdigest()
                cached = image_cache.get(cache_key)
                if cached:
                    log(f"📷 [{idx+1}/{total}] 缓存命中，跳过生成")
                    with lock:
                        results[idx] = cached
                    return idx, cached, True, 0

                log(f"📷 [{idx+1}/{total}] 开始生成...")

                max_retries = 3
                retry_delay = 5
                for retry in range(max_retries):
                    if not retry == 0:
                        actual_delay = retry_delay * (2 ** (retry - 1))
                        log(f"   🔄 重试 {retry}/{max_retries}，等待{actual_delay}秒...")
                        time.sleep(actual_delay)
                    try:
                        request_payload = {
                            "prompt": prompt,
                            "negative_prompt": negative_prompt if needs_negative else "",
                            "width": width,
                            "height": height,
                            "steps": gen_params["steps"],
                            "cfg_scale": gen_params["cfg_scale"],
                            "batch_size": 1,
                            "sampler_name": gen_params["sampler_name"],
                            "scheduler": gen_params["scheduler"],
                            "seed": -1,
                        }
                        override_settings = {}
                        if use_vae and vae_name:
                            override_settings["sd_vae"] = vae_name
                        if override_settings:
                            request_payload["override_settings"] = override_settings

                        response = get_http_session().post(
                            f"{self.api_url}/sdapi/v1/txt2img",
                            json=request_payload,
                            timeout=180
                        )

                        elapsed = time.time() - start_time

                        if response.status_code == 200:
                            result = response.json()
                            images = result.get('images', [])
                            if images:
                                image_cache.set(cache_key, images[0])
                                with lock:
                                    results[idx] = images[0]
                                log(f"   ✅ 完成 (耗时 {elapsed:.1f}s)")
                                return idx, images[0], False, elapsed
                            else:
                                log(f"   ❌ 失败: 无图像数据")
                                if retry < max_retries - 1:
                                    continue
                                return idx, None, False, elapsed
                        else:
                            log(f"   ❌ 失败: HTTP {response.status_code}")
                            if retry < max_retries - 1:
                                continue
                            return idx, None, False, elapsed

                    except Exception as e:
                        if retry < max_retries - 1:
                            log(f"   ⚠️ 请求失败: {str(e)[:60]}")
                            continue
                        elapsed = time.time() - start_time
                        log(f"   ❌ 错误: {str(e)[:80]}")
                        return idx, None, False, elapsed

                return idx, None, False, time.time() - start_time

            except Exception as e:
                elapsed = time.time() - start_time
                log(f"   ❌ 错误: {str(e)[:80]}")
                return idx, None, False, elapsed

        log(f"🚀 启动批量生成: {total}张图像，实际并发{effective_workers}线程")
        log(f"   模型类型: {model_profile['name']}, steps={gen_params['steps']}, cfg={gen_params['cfg_scale']}, sampler={gen_params['sampler_name']} {gen_params['scheduler']}")

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = {executor.submit(generate_single, item): item[0] for item in prompts_data}

            for future in as_completed(futures):
                idx, image_data, from_cache, elapsed = future.result()
                with lock:
                    completed += 1

                if progress_callback:
                    try:
                        progress_callback(completed, total, from_cache)
                    except Exception as e:
                        log(f"进度回调错误: {e}")

        success_count = sum(1 for r in results if r is not None)
        log(f"📊 批量生成完成: {success_count}/{total} 成功")

        if success_count < total:
            log(f"⚠️ {total - success_count}张图像生成失败，建议：")
            log(f"   1. 降低线程数到2-4")
            log(f"   2. 检查SD WebUI是否正常运行")
            log(f"   3. 降低图像分辨率或步数")

        return results

