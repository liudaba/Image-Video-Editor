import subprocess, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_git(args):
    r = subprocess.run(["git"] + args, capture_output=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr

out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git_result.txt")

results = []
results.append("=== ADD ===")
results.append(run_git(["add", "-A"]))

results.append("=== COMMIT ===")
results.append(run_git(["commit", "-m", "fix: 全栈代码审查修复 - 16项Bug和安全漏洞\n\n致命级修复:\n- BUG-1: 修复API路径前缀不匹配，后端所有路由加/api前缀\n- BUG-2: 修复HMAC签名算法不兼容，统一JSON序列化签名\n- BUG-3: 补充缺失的is_license_expired/build_license_response函数\n- BUG-4: Order模型添加payment_url和qr_code字段\n\n严重级修复:\n- BUG-5: 心跳响应添加timestamp字段\n- BUG-6: 修复Token获取方式，改用_get_token()解密方法\n- BUG-7: 支付成功后自动激活许可证\n- BUG-8: 版本检查实现语义化版本比较逻辑\n- BUG-9: 密码验证规则前后端对齐(8位+大小写+数字)\n\n安全漏洞修复:\n- VULN-1: 支付签名验证失败时返回False而非True\n- VULN-2: 管理后台页面添加session认证保护\n- VULN-4: 管理员创建用户密码最小8位验证\n- VULN-5: 重置密码返回reset_token而非明文密码\n\n逻辑缺陷修复:\n- BUG-10: 心跳双重commit合并为单次\n- BUG-11: heartbeat_service.py修复相对导入\n- BUG-12: 移除不可靠的防篡改检测\n- BUG-13: 生产环境数据库配置安全检查\n\n额外修复:\n- 版本检查API添加Authorization认证头"]))

results.append("=== PUSH ===")
results.append(run_git(["push", "origin", "master"]))

with open(out_file, "w", encoding="utf-8") as f:
    f.write("\n".join(results))
