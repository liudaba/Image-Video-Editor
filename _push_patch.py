"""推送补丁到管理后台"""
import requests
import json

base = 'https://api.wangzha178.com'

# 1. 管理员登录
login_resp = requests.post(f'{base}/api/auth/login', json={
    'username': 'admin',
    'password': 'Admin123456'
}, timeout=10)
print(f'登录状态: {login_resp.status_code}')
if login_resp.status_code != 200:
    print(f'登录失败: {login_resp.text}')
    exit(1)

token = login_resp.json().get('access_token', '')
print(f'Token获取成功')

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 2. 查询现有版本，如果1.0.1已存在则先删除
list_resp = requests.get(f'{base}/api/admin/versions', headers=headers, timeout=10)
if list_resp.status_code == 200:
    versions = list_resp.json().get('versions', [])
    for v in versions:
        if v['version'] == '1.0.1':
            vid = v['id']
            print(f'发现已存在的1.0.1版本 (id={vid})，正在删除...')
            del_resp = requests.delete(f'{base}/api/admin/versions/{vid}', headers=headers, timeout=10)
            print(f'删除状态: {del_resp.status_code}')
            break

# 3. 创建版本 1.0.1
version_data = {
    'version': '1.0.1',
    'update_type': 'patch',
    'from_version': '1.0.0',
    'patch_url': f'{base}/static/patches/update_1.0.0_to_1.0.1.zip',
    'patch_hash': '0c59b19aef1e96c1f774a7b91d49c852e91a220e74a982f2168950b54193f4db',
    'patch_size': 9224,
    'changelog': ['修复GPU显存显示误报，区分本进程显存和总显存'],
    'priority': 'normal',
    'force_update': False
}

create_resp = requests.post(f'{base}/api/admin/versions', json=version_data, headers=headers, timeout=10)
print(f'创建版本状态: {create_resp.status_code}')
print(f'响应: {create_resp.text}')

if create_resp.status_code == 200:
    print('\n补丁推送成功！客户端启动后将自动检测到1.0.1版本更新。')
