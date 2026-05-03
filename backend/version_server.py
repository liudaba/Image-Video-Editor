"""
短视频生成器 - 版本管理API
提供最新版本信息和更新包下载
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import json
import os
from datetime import datetime

app = FastAPI(title="VideoGen Version API")

# 版本信息存储(实际项目中应该从数据库读取)
VERSIONS_FILE = "versions.json"

class VersionData(BaseModel):
    version: str
    release_date: str
    download_url: str
    file_size: int
    changelog: List[str]
    force_update: bool = False
    min_version: str = "1.0.0"  # 最低兼容版本

def load_versions():
    """加载版本信息"""
    if os.path.exists(VERSIONS_FILE):
        with open(VERSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"latest": None, "history": []}

def save_versions(data):
    """保存版本信息"""
    with open(VERSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@app.get("/api/version/latest")
def get_latest_version(current_version: str = None):
    """获取最新版本信息"""
    versions_data = load_versions()
    latest = versions_data.get('latest')
    
    if not latest:
        raise HTTPException(status_code=404, detail="未找到版本信息")
    
    # 检查是否需要更新
    if current_version and latest['version'] == current_version:
        return {
            "has_update": False,
            "message": "已是最新版本"
        }
    
    return {
        "has_update": True,
        "version": latest['version'],
        "release_date": latest['release_date'],
        "download_url": latest['download_url'],
        "file_size": latest['file_size'],
        "changelog": latest['changelog'],
        "force_update": latest.get('force_update', False)
    }

@app.get("/api/version/history")
def get_version_history(limit: int = 10):
    """获取版本历史"""
    versions_data = load_versions()
    history = versions_data.get('history', [])
    
    # 返回最近的N个版本
    return history[:limit]

@app.post("/api/version/publish", tags=["admin"])
def publish_new_version(version_data: VersionData):
    """发布新版本(管理员接口)"""
    # TODO: 添加身份验证
    
    versions_data = load_versions()
    
    # 将当前latest移入history
    if versions_data.get('latest'):
        versions_data['history'].insert(0, versions_data['latest'])
    
    # 设置新的latest
    versions_data['latest'] = version_data.dict()
    
    save_versions(versions_data)
    
    return {
        "message": f"版本 v{version_data.version} 发布成功",
        "version": version_data.version
    }

# 初始化示例数据
if not os.path.exists(VERSIONS_FILE):
    sample_data = {
        "latest": {
            "version": "1.0.0",
            "release_date": "2026-05-03",
            "download_url": "https://cdn.videogen.com/releases/VideoGen_v1.0.0_Setup.exe",
            "file_size": 52428800,  # 50MB
            "changelog": [
                "🎉 首个正式版本发布",
                "✅ 支持音频自动转视频",
                "✅ 13种艺术风格可选",
                "✅ 本地和云端双模式",
                "✅ 用户注册和7天试用"
            ],
            "force_update": False
        },
        "history": []
    }
    save_versions(sample_data)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
