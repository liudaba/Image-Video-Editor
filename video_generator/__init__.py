# video_generator 包初始化文件
# 使 video_generator 成为一个可导入的 Python 包

from .enhanced_content_recognition import (
    get_enhanced_recognizer,
    EnhancedContentRecognizer,
    COUNTRY_MAPPING,
    REGION_MAPPING,
    CITY_MAPPING,
    ORGANIZATION_MAPPING,
    MILITARY_MAPPING,
    CONTENT_TYPE_KEYWORDS
)

__all__ = [
    'get_enhanced_recognizer',
    'EnhancedContentRecognizer', 
    'COUNTRY_MAPPING',
    'REGION_MAPPING',
    'CITY_MAPPING',
    'ORGANIZATION_MAPPING',
    'MILITARY_MAPPING',
    'CONTENT_TYPE_KEYWORDS'
]
