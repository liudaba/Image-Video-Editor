
# 修改后的render_video_threaded方法
# 将此方法替换My-Video Generator.py中的render_video_threaded方法

def render_video_threaded(self):
    """跑图生成视频（完整流程：生成分镜 + 生成图片 + 合成视频）

    前置检查：
    1. 必须导入音频文件
    2. 图片文件夹内不允许存在图片文件（除非有对应的分镜脚本）

    工作流程：
    - 如果存在分镜脚本文件，直接使用它生成图片
    - 如果不存在分镜脚本文件，则生成分镜脚本，然后生成图片
    - 最后合成视频
    """
    try:
        self.log("🎞️ 开始跑图生成视频...")

        # ===== 前置检查 =====
        # 检查1: 必须导入音频文件
        if not self.audio_path:
            self.log("❌ 没有导入音频文件，无法执行任务")
            messagebox.showwarning("缺少音频", "请先导入音频文件，再执行跑图生成视频任务！")
            return

        if not os.path.exists(self.audio_path):
            self.log(f"❌ 音频文件不存在: {self.audio_path}")
            messagebox.showwarning("音频文件丢失", "音频文件不存在，请重新导入音频文件！")
            return

        # 检查2: 检查是否存在分镜脚本文件
        shots_file = os.path.join(self.output_dir, "shots_data.json")
        has_shots_file = os.path.exists(shots_file)

        # 检查3: 图片文件夹内是否存在图片文件
        has_images = False
        if os.path.exists(self.images_dir):
            image_files = [f for f in os.listdir(self.images_dir)
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
            has_images = len(image_files) > 0

            # 如果有图片但没有分镜脚本，提示用户清理图片
            if has_images and not has_shots_file:
                self.log(f"⚠️ 图片文件夹中已存在 {len(image_files)} 个图片文件，但没有分镜脚本")
                messagebox.showwarning(
                    "图片文件已存在",
                    f"图片文件夹中已存在 {len(image_files)} 个图片文件，但没有分镜脚本！\n\n"
                    "请先清理图片文件夹，然后重新执行跑图生成视频任务。\n\n"
                    "提示：可以在左侧面板点击「清除」按钮清理旧文件。"
                )
                return

            # 如果既有图片又有分镜脚本，询问用户是否使用现有分镜脚本
            if has_images and has_shots_file:
                self.log(f"✅ 检测到 {len(image_files)} 个图片文件和分镜脚本文件")
                self.log("ℹ️ 将使用现有分镜脚本文件，直接生成视频")
                # 直接生成视频，不重新生成分镜和图片
                self.generate_video(skip_clear=True, skip_image_check=True)
                return

        # 启动渲染线程
        def render_video_worker():
            self.task_running = True
            self.pause_event.set()
            try:
                # ========== 阶段1: 生成分镜脚本 ==========
                self.log("")
                self.log("━" * 50)
                self.log("📋 阶段1: 生成分镜脚本")
                self.log("━" * 50)

                # 检查是否存在分镜脚本文件
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    self.log("✅ 检测到已存在的分镜脚本文件")
                    self.log("ℹ️ 将使用现有分镜脚本文件，跳过生成步骤")
                    # 加载现有分镜数据
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        self.log(f"📂 已加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        # 如果加载失败，则重新生成
                        self.log("ℹ️ 加载失败，将重新生成分镜脚本")
                        self._generate_shots_data()
                else:
                    # 没有分镜脚本文件，生成新的
                    self._generate_shots_data()

                # 验证分镜是否生成成功
                if not hasattr(self, 'shots_data') or not self.shots_data:
                    self.log("❌ 分镜生成失败，无法继续")
                    self.update_task_progress("就绪")
                    return

                self.log(f"✅ 分镜准备完成: {len(self.shots_data)} 个分镜")

                # ========== 阶段2: 生成图片 & 合成视频 ==========
                self.log("")
                self.log("━" * 50)
                self.log("🖼️ 阶段2: 生成图片 & 合成视频")
                self.log("━" * 50)

                self.generate_video(skip_clear=False, skip_image_check=False)

            except Exception as e:
                self.log(f"❌ 渲染视频出错: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.task_running = False
                if hasattr(self, '_pregenerated_prompts'):
                    delattr(self, '_pregenerated_prompts')

        thread = threading.Thread(target=render_video_worker, daemon=True)
        thread.start()
        self.log("✅ 渲染线程已启动")
    except Exception as e:
        self.log(f"❌ 渲染视频线程启动失败: {e}")
        import traceback
        traceback.print_exc()

def _generate_shots_data(self):
    """生成分镜数据的辅助方法"""
    # 清除旧的分镜数据，避免残留旧音频内容
    self.log("🗑️ 清除旧分镜数据，确保使用当前音频...")
    self.shots_data = []
    if hasattr(self, '_pregenerated_prompts'):
        delattr(self, '_pregenerated_prompts')
    if hasattr(self, '_shot_texts_for_context'):
        delattr(self, '_shot_texts_for_context')

    # 删除旧的分镜脚本文件
    shots_file = os.path.join(self.output_dir, "shots_data.json")
    if os.path.exists(shots_file):
        os.remove(shots_file)
        self.log("   🗑️ 已删除旧的shots_data.json")

    # 清除音频分析缓存，强制重新转录
    self.cache_clear()
    try:
        prompt_cache.clear()
    except Exception:
        pass
    try:
        image_cache.clear()
    except Exception:
        pass

    # 重置状态管理器
    try:
        if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
            self.state_manager['shots'] = {
                'generated': False,
                'count': 0,
                'data': []
            }
    except Exception:
        pass

    self.log("✅ 旧数据已清除，开始生成分镜...")

    # 生成分镜脚本（auto_mode=True，不弹窗）
    self.generate_shots(auto_mode=True)

    # 验证分镜是否生成成功
    if not hasattr(self, 'shots_data') or not self.shots_data:
        # 尝试从文件加载
        shots_file = os.path.join(self.output_dir, "shots_data.json")
        if os.path.exists(shots_file):
            try:
                with open(shots_file, 'r', encoding='utf-8') as f:
                    self.shots_data = json.load(f)
                self.log(f"📂 从文件加载分镜数据: {len(self.shots_data)} 个分镜")
            except Exception as e:
                self.log(f"❌ 加载分镜数据失败: {e}")

        if not self.shots_data:
            self.log("❌ 分镜生成失败，无法继续")
            self.update_task_progress("就绪")
            return

    self.log(f"✅ 分镜生成完成: {len(self.shots_data)} 个分镜")
