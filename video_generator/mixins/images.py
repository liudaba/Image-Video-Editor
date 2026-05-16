"""Image generation mixin - SD API pipeline with prefetch."""
import os
import json
import time
import threading
import hashlib
import queue
import base64
import requests
import tkinter as tk

from video_generator.mixins.logging import safe_print_exc

from video_generator.config import Config, get_http_session, validate_image_size
from video_generator.cache import image_cache
from video_generator.model_profiles import get_model_profile
from video_generator.ollama_client import is_cloud_image_active

class ImagesMixin:
    def _run_image_saver(self, save_queue):
        """独立IO线程: 解码base64并保存图片到磁盘"""
        from PIL import Image
        from io import BytesIO
        while True:
            try:
                item = save_queue.get(timeout=30)
            except queue.Empty:
                if not self.task_running:
                    break
                continue
            if item is None:
                save_queue.task_done()
                break
            try:
                _, save_path, b64_data = item
                img_bytes = base64.b64decode(b64_data)
                with Image.open(BytesIO(img_bytes)) as image:
                    image.save(save_path)
            except Exception as e:
                self._log_exception(f"   ⚠️ 图片保存失败: {os.path.basename(save_path) if save_path else '未知'}", e)
            finally:
                save_queue.task_done()

    def _consume_image_results(self, result_queue, save_queue, total_tasks, saver_thread=None, producer_thread=None):
        """公共消费者逻辑：从 result_queue 取结果，更新进度，统计计数"""
        generated_count = 0
        failed_count = 0
        cached_count = 0
        batch_start_time = time.time()
        received = 0
        task_cancelled = False

        while received < total_tasks:
            try:
                item = result_queue.get(timeout=30)
            except queue.Empty:
                if not self.task_running:
                    task_cancelled = True
                    self.log("❌ 任务已被取消")
                    break
                continue
            if item is None:
                break

            result_type = item[3] if len(item) > 3 else "unknown"

            if result_type == "cancelled":
                task_cancelled = True
                self.log("❌ 任务已被取消")
                break

            idx = item[0]
            progress = 40 + (received / total_tasks) * 50
            self.update_task_progress(f"生成图像 {received+1}/{total_tasks}...", progress)

            if received % 5 == 0 or received == total_tasks - 1:
                elapsed = time.time() - batch_start_time
                avg_time = elapsed / (received + 1)
                remaining = (total_tasks - received - 1) * avg_time
                self.log(f"📷 [{received+1}/{total_tasks}] (已用{elapsed:.0f}s, 预计剩余{remaining:.0f}s)")

            if result_type == "cached":
                cached_count += 1
                img_path = item[5]
                save_queue.put((idx, img_path, item[2]), timeout=30)
                self.log(f"   ✅ 缓存命中")

            elif result_type == "generated":
                generated_count += 1
                req_time = item[4]
                img_path = item[5]
                save_queue.put((idx, img_path, item[2]), timeout=30)
                self.log(f"   ✅ 完成 (耗时 {req_time:.1f}s)")

            elif result_type == "connection_error":
                failed_count += 1
                self.log(f"   ❌ 连接失败: SD服务未响应")
                self.log(f"   💡 请检查 SD WebUI 是否正常运行")
                break

            else:
                failed_count += 1
                self.log(f"   ❌ 生成失败")

            received += 1
            result_queue.task_done()

        while not result_queue.empty():
            try:
                result_queue.get_nowait()
                result_queue.task_done()
            except queue.Empty:
                break

        if generated_count + cached_count > 0 and not task_cancelled:
            self.state_manager['images']['generated'] = True
        self.state_manager['images']['count'] = generated_count + cached_count

        return task_cancelled, saver_thread, producer_thread

    def _check_sd_api_impl(self, silent=False):
        """实际执行SD API连接检查（内部方法）"""
        if is_cloud_image_active():
            if not silent:
                self.log("☁️ 云端生图已启用，无需连接本地SD API")
            return True

        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL

        check_timeout = Config.API_TIMEOUT_SHORT if silent else Config.API_TIMEOUT_MEDIUM

        try:
            response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=check_timeout)
            if response.status_code == 200:
                if not silent:
                    self.log("✅ SD API 连接成功！")
                self._sd_api_connected = True
                
                # 更新状态变量（即使 label 还不存在也要更新，这样面板打开时能显示正确状态）
                if hasattr(self, 'sd_api_status_var'):
                    self.sd_api_status_var.set("✅ 已连接")
                
                # 更新 UI 显示（如果 label 已存在）
                if hasattr(self, 'sd_api_status_label'):
                    def update_ui():
                        if hasattr(self, 'sd_api_status_label'):
                            self.sd_api_status_label.config(foreground="green")
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
                
                # 更新模型下拉菜单
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, self._update_model_dropdown)
                
                return True
            else:
                if not silent:
                    self.log(f"❌ SD API 连接失败: 状态码 {response.status_code}")
                self._sd_api_connected = False
                
                # 更新状态变量
                if hasattr(self, 'sd_api_status_var'):
                    self.sd_api_status_var.set("❌ 未连接")
                
                # 更新 UI 显示
                if hasattr(self, 'sd_api_status_label'):
                    def update_ui():
                        if hasattr(self, 'sd_api_status_label'):
                            self.sd_api_status_label.config(foreground="red")
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
                return False
        except Exception as e:
            if not silent:
                self._log_exception("❌ SD API 连接异常", e)
            self._sd_api_connected = False
            
            # 更新状态变量
            if hasattr(self, 'sd_api_status_var'):
                self.sd_api_status_var.set("❌ 未连接")
            
            # 更新 UI 显示
            if hasattr(self, 'sd_api_status_label'):
                def update_ui():
                    if hasattr(self, 'sd_api_status_label'):
                        self.sd_api_status_label.config(foreground="red")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            return False
    

    def _get_sd_models_from_api(self):
        """从 SD API 获取可用模型列表"""
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL

        try:
            response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_SHORT)
            if response.status_code == 200:
                models_data = response.json()
                # 提取模型名称（使用 title 或 model_name）
                model_names = []
                for model in models_data:
                    title = model.get('title', '')
                    model_name = model.get('model_name', '')
                    # 优先使用 title，因为更易读
                    if title:
                        # 去掉文件扩展名，使显示更简洁
                        display_name = title.replace('.safetensors', '').replace('.ckpt', '')
                        model_names.append(display_name)
                    elif model_name:
                        model_names.append(model_name)
                return model_names
        except Exception as e:
            pass  # 静默失败，使用默认列表
        return []
    

    def _show_sd_api_result(self, result):
        """显示SD API连接结果（在主线程中调用）"""
        if not result:
            messagebox.showerror("错误", "SD API 连接失败，请检查Stable Diffusion是否已启动")
    

    def generate_images(self):
        """生成图像"""
        if not getattr(self, '_auth_valid', False):
            self.log("⚠️ 请先登录后再操作")
            self._show_login_dialog()
            return
        self.log("🖼️ 开始生成图像...")
        try:
            from PIL import Image
            from io import BytesIO

            cloud_image_enabled = is_cloud_image_active()

            if cloud_image_enabled:
                self._generate_images_cloud()
            else:
                self._generate_images_local()
        except Exception as e:
            self.log(f"❌ 图像生成失败: {e}")
            safe_print_exc()
        finally:
            try:
                import gc
                gc.collect()
            except Exception:
                pass
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def _generate_images_cloud(self):
        """云端生图流程"""
        from video_generator.cloud_image_client import call_cloud_image, get_cloud_image_config
        from PIL import Image
        from io import BytesIO

        self._safe_release_whisper_gpu()
        if not self._whisper_on_gpu:
            self.log("   🧹 Whisper GPU 显存已释放（云端生图模式）")
        try:
            self._unload_ollama_models(log_prefix="   ☁️ ")
        except Exception:
            pass

        if not self.shots_data:
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            if os.path.exists(shots_file):
                try:
                    with open(shots_file, 'r', encoding='utf-8') as f:
                        loaded_shots = json.load(f)
                    with self.resource_lock:
                        self.shots_data = loaded_shots
                    self.log(f"📂 已从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                except Exception as e:
                    self._log_exception("❌ 加载分镜数据失败", e)
                    self.update_task_progress("就绪")
                    return
            else:
                self.log("❌ 没有分镜数据，无法生成图像")
                self.update_task_progress("就绪")
                return

        self.update_task_progress("正在准备云端生图...", 10)

        cloud_config = get_cloud_image_config()
        from video_generator.cloud_image_client import IMAGE_PROVIDER_CONFIG
        provider_name = IMAGE_PROVIDER_CONFIG.get(cloud_config.get("provider", ""), {}).get("name", "未知")
        cloud_model = cloud_config.get("model", "未知")

        width, height = validate_image_size(
            self.width_var.get() if hasattr(self, 'width_var') else '1024',
            self.height_var.get() if hasattr(self, 'height_var') else '576'
        )
        selected_styles = self.get_selected_styles()

        self.log("")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("☁️ 云端生图任务开始")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log(f"   服务商: {provider_name}")
        self.log(f"   模型:   {cloud_model}")
        self.log(f"   尺寸:   {width} × {height}")
        if selected_styles:
            self.log(f"   风格预设: {', '.join(selected_styles)}")
        self.log(f"   所有图片将由云端生成，无需本地SD")
        self.log("")

        os.makedirs(self.images_dir, exist_ok=True)

        style_descriptions = []
        for style in selected_styles:
            style_desc = self.generate_style_description(style)
            if style_desc:
                style_descriptions.append(style_desc)

        sorted_shots = sorted(self.shots_data, key=lambda x: x['id'])

        tasks = []
        skipped_count = 0
        for shot in sorted_shots:
            shot_id = shot['id']
            prompt = shot['prompt_en']
            image_file = shot['image_file']
            image_path = os.path.join(self.images_dir, image_file)
            negative_prompt = shot.get('negative_prompt', '')

            if os.path.exists(image_path):
                skipped_count += 1
                continue

            enhanced_prompt = prompt
            if style_descriptions:
                style_text = ", ".join(style_descriptions)
                enhanced_prompt = f"{style_text}, {prompt}"

            tasks.append((shot_id, enhanced_prompt, image_file, image_path, negative_prompt))

        self.log(f"📊 任务统计:")
        self.log(f"   总分镜数: {len(self.shots_data)} 个")
        if skipped_count > 0:
            self.log(f"   已存在跳过: {skipped_count} 个")
        self.log(f"   需要生成: {len(tasks)} 个")

        _kf_count = sum(1 for s in sorted_shots if s.get('semantic_weight', 0.5) >= 2.0 or s.get('id', 0) == 0 or s.get('id', 0) == len(sorted_shots) - 1)
        if _kf_count > 0:
            self.log(f"   关键帧分镜: {_kf_count} 个")

        if not tasks:
            self.log("✅ 所有图片已存在，无需生成")
            self.state_manager['images']['generated'] = True
            self.state_manager['images']['count'] = len(self.shots_data)
            return

        self.log(f"🚀 开始云端生成 {len(tasks)} 张图像...")
        self.log("")

        import queue

        save_queue = queue.Queue(maxsize=8)

        saver_thread = threading.Thread(target=self._run_image_saver, args=(save_queue,), daemon=True)
        saver_thread.start()

        result_queue = queue.Queue(maxsize=16)

        def cloud_producer():
            for idx, (sid, prompt, img_file, img_path, neg) in enumerate(tasks):
                if not self.task_running:
                    try:
                        result_queue.put((idx, None, None, "cancelled"), timeout=5)
                    except queue.Full:
                        pass
                    break
                if not self.pause_event.is_set():
                    self.pause_event.wait(timeout=5)
                    if not self.pause_event.is_set() and not self.task_running:
                        try:
                            result_queue.put((idx, None, None, "cancelled"), timeout=5)
                        except queue.Full:
                            pass
                        break

                ck = hashlib.md5(f"{prompt}_{neg or ''}_{width}_{height}_{cloud_model}".encode()).hexdigest()
                cached = image_cache.get(ck)
                if cached:
                    try:
                        result_queue.put((idx, ck, cached, "cached", 0.0, img_path), timeout=30)
                    except queue.Full:
                        pass
                    continue

                max_retries = 3
                retry_delay = 8
                for retry in range(max_retries):
                    if not self.task_running:
                        try:
                            result_queue.put((idx, None, None, "cancelled"), timeout=5)
                        except queue.Full:
                            pass
                        break
                    try:
                        req_start = time.time()
                        img_b64, used_model = call_cloud_image(
                            prompt=prompt,
                            negative_prompt=neg or "",
                            width=width,
                            height=height,
                            log_callback=lambda msg: self.log(f"   {msg}") if msg else None,
                        )
                        req_time = time.time() - req_start

                        if img_b64:
                            image_cache.set(ck, img_b64)
                            try:
                                result_queue.put((idx, ck, img_b64, "generated", req_time, img_path), timeout=30)
                            except queue.Full:
                                pass
                            break
                        else:
                            if retry < max_retries - 1:
                                self.log(f"   ⚠️ 第{retry+1}次生成失败，{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                            else:
                                try:
                                    result_queue.put((idx, None, None, "failed"), timeout=5)
                                except queue.Full:
                                    pass
                    except Exception as e:
                        if retry < max_retries - 1:
                            self._log_exception(f"   ⚠️ 云端生图异常，{retry_delay}秒后重试", e)
                            time.sleep(retry_delay)
                        else:
                            try:
                                result_queue.put((idx, None, None, "failed"), timeout=5)
                            except queue.Full:
                                pass

            try:
                result_queue.put(None, timeout=5)
            except queue.Full:
                pass

        producer_thread = threading.Thread(target=cloud_producer, daemon=True, name="Cloud-Image-Producer")
        producer_thread.start()

        task_cancelled, _, _ = self._consume_image_results(result_queue, save_queue, len(tasks), saver_thread=saver_thread, producer_thread=producer_thread)

        try:
            save_queue.put(None, timeout=5)
        except Exception:
            pass
        try:
            saver_thread.join(timeout=10)
        except Exception:
            pass
        try:
            producer_thread.join(timeout=5)
        except Exception:
            pass

    def _generate_images_local(self):
        """本地SD生图流程（原有逻辑）"""
        # 检查是否有分镜数据，如果没有则尝试从文件加载
        if not self.shots_data:
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            if os.path.exists(shots_file):
                try:
                    with open(shots_file, 'r', encoding='utf-8') as f:
                        loaded_shots = json.load(f)
                    with self.resource_lock:
                        self.shots_data = loaded_shots
                    for shot in self.shots_data:
                        if 'description' in shot and shot['description']:
                            shot['description'] = self.clean_text(shot['description'])
                    self.log(f"📂 已从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                except Exception as e:
                    self._log_exception("❌ 加载分镜数据失败", e)
                    self.log("❌ 没有分镜数据，无法生成图像")
                    self.update_task_progress("就绪")
                    return
            else:
                self.log("❌ 没有分镜数据，无法生成图像")
                self.update_task_progress("就绪")
                return
            
        # 更新进度
        self.update_task_progress("正在连接SD服务...", 10)
            
        # 检查SD API连接状态
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL
        current_sd_model = "未知"  # 当前实际使用的SD模型
            
        # 获取用户设置的像素尺寸
        width, height = validate_image_size(
            self.width_var.get() if hasattr(self, 'width_var') else '1024',
            self.height_var.get() if hasattr(self, 'height_var') else '576'
        )
            
        # 调试：显示原始设置值
        raw_width = self.width_var.get() if hasattr(self, 'width_var') else "未设置"
        raw_height = self.height_var.get() if hasattr(self, 'height_var') else "未设置"
        self.log(f"   原始设置: 宽={raw_width}, 高={raw_height}")
            
        # 获取用户选择的模型
        selected_model = self.model_var.get() if hasattr(self, 'model_var') else "使用当前模型"
            
        # 获取用户选择的风格预设
        selected_styles = self.get_selected_styles()
            
        # ========== 步骤1: 连接SD服务 ==========
        self.log("")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("🖼️ 图像生成任务开始")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
        try:
            # 获取当前SD配置
            options_response = get_http_session().get(f"{api_url}/sdapi/v1/options", timeout=Config.API_TIMEOUT_MEDIUM)
            if options_response.status_code != 200:
                self.log(f"❌ SD服务连接失败 (状态码: {options_response.status_code})")
                self.log("💡 请确认 Stable Diffusion Web UI 已启动")
                self.update_task_progress("就绪")
                return
                
            options = options_response.json()
            current_sd_model = options.get('sd_model_checkpoint', '未知')
            self.log(f"✅ SD服务连接成功")
            self.log(f"   服务地址: {api_url}")
            self.log(f"   当前模型: {current_sd_model}")
                
            # 获取可用模型列表
            models_response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_MEDIUM)
            if models_response.status_code == 200:
                available_models = models_response.json()
                self.log(f"   可用模型: {len(available_models)} 个")
            else:
                available_models = []
                self.log(f"   可用模型: 无法获取")
                    
        except Exception as e:
            self.log("❌ SD服务连接异常，💡 请确认 Stable Diffusion Web UI 已启动且API地址正确")
            self.update_task_progress("就绪")
            return
            
        # ========== 步骤2: 准备生成参数 ==========
        self.update_task_progress("正在准备生成参数...", 20)
        self.log("")
        self.log("📋 生成参数配置:")
        self.log(f"   图像尺寸: {width} × {height} 像素")
        self.log(f"   用户选择模型: {selected_model}")

        # 根据制图模型获取最优参数配置
        model_profile = get_model_profile(selected_model)
        gen_params = model_profile["params"]
        needs_negative = model_profile["needs_negative"]
        use_vae = model_profile.get("use_vae_override", False)
        vae_name = model_profile.get("vae_name", "")

        self.log(f"   模型类型: {model_profile['name']}")
        self.log(f"   提示词格式: {model_profile['prompt_format']}")
        self.log(f"   采样参数: steps={gen_params['steps']}, cfg_scale={gen_params['cfg_scale']}, sampler={gen_params['sampler_name']} {gen_params['scheduler']}")
        self.log(f"   负面提示词: {'需要' if needs_negative else '不需要'}")
        if use_vae and vae_name:
            self.log(f"   VAE覆盖: {vae_name}")

        if selected_styles:
            self.log(f"   风格预设: {', '.join(selected_styles)}")
            
        # 确保图像目录存在
        os.makedirs(self.images_dir, exist_ok=True)
        # 准备风格描述
        style_descriptions = []
        for style in selected_styles:
            style_desc = self.generate_style_description(style)
            if style_desc:
                style_descriptions.append(style_desc)
            
        # 按分镜ID排序
        sorted_shots = sorted(self.shots_data, key=lambda x: x['id'])
            
        # 统计需要生成的图像
        tasks = []
        skipped_count = 0
        for shot in sorted_shots:
            shot_id = shot['id']
            prompt = shot['prompt_en']
            image_file = shot['image_file']
            image_path = os.path.join(self.images_dir, image_file)
            description = shot.get('description', 'No content')
            negative_prompt = shot.get('negative_prompt', '')

            if os.path.exists(image_path):
                skipped_count += 1
                continue

            # 根据模型类型处理负面提示词
            if not needs_negative:
                negative_prompt = ""

            enhanced_prompt = prompt
            if style_descriptions:
                style_text = ", ".join(style_descriptions)
                enhanced_prompt = f"{style_text}, {prompt}"

            tasks.append((shot_id, enhanced_prompt, image_file, image_path, description, negative_prompt))
            
        self.log("")
        self.log(f"📊 任务统计:")
        self.log(f"   总分镜数: {len(self.shots_data)} 个")
        if skipped_count > 0:
            self.log(f"   已存在跳过: {skipped_count} 个")
        self.log(f"   需要生成: {len(tasks)} 个")
            
        _keyframe_count = 0
        for shot in sorted_shots:
            sw = shot.get('semantic_weight', 0.5)
            total = len(sorted_shots)
            sid = shot.get('id', 0)
            is_key = sw >= 2.0 or sid == 0 or sid == total - 1
            if is_key:
                _keyframe_count += 1
        if _keyframe_count > 0:
            self.log(f"   关键帧分镜: {_keyframe_count} 个（将使用增强采样参数）")
            
        # ========== 步骤3: 模型切换（如需要）==========
        if selected_model and selected_model != "使用当前模型":
            self.log("")
            self.log("🔄 模型切换:")
            self.log(f"   目标模型: {selected_model}")
            self.log(f"   当前模型: {current_sd_model}")
                
            try:
                sd_model_name = selected_model
                    
                import re as _re
                sd_model_name = _re.sub(r'^\[SD1\.5\]\s*|\[SDXL\]\s*|\[Flux\]\s*|\[SD3\]\s*', '', sd_model_name).strip()
                    
                if len(available_models) == 0:
                    models_response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_LONG)
                    if models_response.status_code == 200:
                        available_models = models_response.json()
                    
                target_model = None
                for model_info in available_models:
                    # 精确匹配或部分匹配
                    model_title = model_info.get('title', '')
                    model_name = model_info.get('model_name', '')
                        
                    # 去掉扩展名后比较
                    clean_title = model_title.replace('.safetensors', '').replace('.ckpt', '')
                        
                    if sd_model_name == clean_title or sd_model_name == model_title or sd_model_name == model_name:
                        target_model = model_title  # 使用完整的 title 来切换
                        break
                    # 也支持部分匹配
                    elif sd_model_name.lower() in model_title.lower() or sd_model_name.lower() in model_name.lower():
                        target_model = model_title
                        break
                    
                if target_model:
                    switch_response = get_http_session().post(
                        f"{api_url}/sdapi/v1/options",
                        json={"sd_model_checkpoint": target_model},
                        timeout=30
                    )
                    if switch_response.status_code == 200:
                        self.log(f"   ⏳ 模型切换中，等待加载...")
                        model_loaded = False
                        for wait_i in range(30):
                            time.sleep(2)
                            try:
                                check_resp = get_http_session().get(f"{api_url}/sdapi/v1/options", timeout=5)
                                if check_resp.status_code == 200:
                                    check_opts = check_resp.json()
                                    if check_opts.get('sd_model_checkpoint', '') == target_model:
                                        model_loaded = True
                                        current_sd_model = target_model
                                        self.log(f"   ✅ 模型加载完成: {target_model}")
                                        break
                                    elif check_opts.get('sd_model_checkpoint', '') != current_sd_model:
                                        current_sd_model = check_opts.get('sd_model_checkpoint', '')
                                        self.log(f"   ✅ 切换成功: {current_sd_model}")
                                        model_loaded = True
                                        break
                            except Exception:
                                pass
                            if wait_i % 5 == 4:
                                self.log(f"   ⏳ 仍在加载模型... ({(wait_i+1)*2}秒)")
                        if not model_loaded:
                            self.log(f"   ⚠️ 模型加载超时，继续使用当前模型")
                    else:
                        self.log(f"   ❌ 切换失败 (HTTP {switch_response.status_code})")
                        self.log(f"   继续使用: {current_sd_model}")
                else:
                    self.log(f"   ❌ 未找到目标模型")
                    self.log(f"   继续使用: {current_sd_model}")
                        
            except Exception as e:
                self._log_exception("   ❌ 切换异常", e)
                self.log(f"   继续使用: {current_sd_model}")
            
        # ========== 最终配置确认 ==========
        self.log("")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log(f"🎯 实际使用模型: {current_sd_model}")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("")
            
        # ========== 步骤4: 预取流水线生成图像 ==========
        if tasks:
            self.log("")
            self._safe_release_whisper_gpu()
            if not self._whisper_on_gpu:
                self.log("   🧹 Whisper GPU 显存已释放")
                
            try:
                self._unload_ollama_models(log_prefix="   ")
            except Exception:
                pass
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    vram = torch.cuda.memory_allocated(0) / 1024**3
                    self.log(f"   📊 GPU 显存占用: {vram:.1f} GB")
                    if vram > 2.0:
                        self.log(f"   ⚠️ GPU 显存仍较高，等待释放...")
                        for _ in range(10):
                            time.sleep(1)
                            torch.cuda.empty_cache()
                            vram = torch.cuda.memory_allocated(0) / 1024**3
                            if vram < 1.5:
                                break
                    self.log(f"   📊 GPU 显存: {vram:.1f} GB")
            except Exception:
                pass
            self.log(f"🚀 开始生成 {len(tasks)} 张图像...")
            self.log(f"   模式: 预取流水线（SD生成与图片保存并行）")
            self.log("")

            import queue
            import base64
            from PIL import Image
            from io import BytesIO

            save_queue = None
            saver_thread = None
            producer_thread = None

            if tasks:
                save_queue = queue.Queue(maxsize=8)

                saver_thread = threading.Thread(target=self._run_image_saver, args=(save_queue,), daemon=True)
                saver_thread.start()

                result_queue = queue.Queue(maxsize=16)

            if not tasks:
                self.log("   ⚠️ 没有需要生成的图片任务")
                self.update_task_progress("就绪")
                return

            def sd_producer():
                """独立请求线程: 连续发送SD生成请求，实现预取"""
                for idx, (sid, prompt, img_file, img_path, desc, neg) in enumerate(tasks):
                    if not self.task_running:
                        try:
                            result_queue.put((idx, None, None, "cancelled"), timeout=5)
                        except queue.Full:
                            pass
                        break
                    if not self.pause_event.is_set():
                        self.pause_event.wait(timeout=5)
                        if not self.pause_event.is_set() and not self.task_running:
                            try:
                                result_queue.put((idx, None, None, "cancelled"), timeout=5)
                            except queue.Full:
                                pass
                            break

                    ck = hashlib.md5(f"{prompt}_{neg}_{width}_{height}_{current_sd_model}".encode()).hexdigest()
                    cached = image_cache.get(ck)
                    if cached:
                        try:
                            result_queue.put((idx, ck, cached, "cached", 0.0, img_path), timeout=30)
                        except queue.Full:
                            pass
                        continue

                    max_retries = 3
                    retry_delay = 5
                    for retry in range(max_retries):
                        if not self.task_running:
                            try:
                                result_queue.put((idx, None, None, "cancelled"), timeout=5)
                            except queue.Full:
                                pass
                            break
                        try:
                            req_start = time.time()
                            request_payload = {
                                "prompt": prompt,
                                "negative_prompt": neg or "",
                                "width": width, "height": height,
                                "steps": gen_params["steps"],
                                "cfg_scale": gen_params["cfg_scale"],
                                "sampler_name": gen_params["sampler_name"],
                                "scheduler": gen_params["scheduler"],
                                "seed": -1, "batch_size": 1,
                            }
                            _shot_data = None
                            for s in sorted_shots:
                                if s.get('id') == idx:
                                    _shot_data = s
                                    break
                            if _shot_data:
                                _sw = _shot_data.get('semantic_weight', 0.5)
                                _total_shots = len(sorted_shots)
                                _sid = _shot_data.get('id', 0)
                                _is_keyframe = _sw >= 2.0 or _sid == 0 or _sid == _total_shots - 1
                                if _is_keyframe:
                                    request_payload["steps"] = min(gen_params["steps"] + 8, 50)
                                    request_payload["cfg_scale"] = min(gen_params["cfg_scale"] + 0.5, 12.0)
                            override_settings = {}
                            if use_vae and vae_name:
                                override_settings["sd_vae"] = vae_name
                            if override_settings:
                                request_payload["override_settings"] = override_settings

                            resp = get_http_session().post(
                                f"{api_url}/sdapi/v1/txt2img",
                                json=request_payload,
                                timeout=Config.API_TIMEOUT_LONG
                            )
                            req_time = time.time() - req_start

                            if resp.status_code == 200:
                                rj = resp.json()
                                if "images" in rj and rj["images"]:
                                    img_data = rj["images"][0]
                                    image_cache.set(ck, img_data)
                                    try:
                                        result_queue.put((idx, ck, img_data, "generated", req_time, img_path), timeout=30)
                                    except queue.Full:
                                        pass
                                    break
                                else:
                                    if retry < max_retries - 1:
                                        time.sleep(retry_delay)
                            else:
                                if retry < max_retries - 1:
                                    time.sleep(retry_delay)
                        except requests.exceptions.ConnectionError:
                            try:
                                result_queue.put((idx, None, None, "connection_error"), timeout=5)
                            except queue.Full:
                                pass
                            break
                        except requests.exceptions.Timeout:
                            if retry < max_retries - 1:
                                time.sleep(retry_delay)
                        except Exception as e:
                            if retry < max_retries - 1:
                                time.sleep(retry_delay)
                    else:
                        try:
                            result_queue.put((idx, None, None, "failed"), timeout=5)
                        except queue.Full:
                            pass
                try:
                    result_queue.put(None, timeout=5)
                except queue.Full:
                    pass

            producer_thread = threading.Thread(target=sd_producer, daemon=True, name="SD-Producer")
            producer_thread.start()

            task_cancelled, _, _ = self._consume_image_results(result_queue, save_queue, len(tasks), saver_thread=saver_thread, producer_thread=producer_thread)

        try:
            save_queue.put(None, timeout=5)
        except Exception:
            pass
        try:
            saver_thread.join(timeout=10)
        except Exception:
            pass
        try:
            producer_thread.join(timeout=5)
        except Exception:
            pass
    
    # =======================================================================
    # 第十一部分：音视频导入与渲染 (行 9398-10278)
    # 包含：清除图片视频、导入音频、视频渲染、输出文件夹
    # =======================================================================

    def clear_images_and_videos(self):
        """清除图片和视频文件"""
        self.log("🗑️ 开始清除图片和视频文件...")
        self._move_output_to_trash(reason="清除图片视频")
        self.log("✅ 图片和视频文件已移至垃圾桶")
    

