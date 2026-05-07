import requests

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("  短视频生成器 API 集成测试")
print("=" * 60)

print("\n1. 测试健康检查...")
r = requests.get(f"{BASE}/health")
print(f"   GET /health => {r.status_code} {r.json()}")

print("\n2. 测试用户注册...")
r = requests.post(f"{BASE}/api/auth/register", json={
    "username": "buyer2",
    "email": "buyer2@test.com",
    "password": "buy123456"
})
print(f"   POST /api/auth/register => {r.status_code}")
if r.status_code == 200:
    data = r.json()
    token = data["access_token"]
    license_data = data.get("license")
    print(f"   Token: {token[:8]}...")
    print(f"   License: type={license_data.get('license_type') if license_data else 'N/A'}, valid={license_data.get('is_valid') if license_data else 'N/A'}")
    print(f"   Days left: {license_data.get('days_left') if license_data else 'N/A'}")
else:
    print(f"   Error: {r.text[:200]}")
    token = None

if token:
    headers = {"Authorization": f"Bearer {token}"}

    print("\n3. 测试用户登录...")
    r = requests.post(f"{BASE}/api/auth/login", json={
        "username": "buyer2",
        "password": "buy123456"
    })
    print(f"   POST /api/auth/login => {r.status_code}")
    if r.status_code == 200:
        login_data = r.json()
        print(f"   Token: {login_data['access_token'][:8]}...")
        token = login_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

    print("\n4. 测试查询授权状态...")
    r = requests.get(f"{BASE}/api/user/license_status", headers=headers)
    print(f"   GET /api/user/license_status => {r.status_code}")
    if r.status_code == 200:
        ls = r.json()
        lic = ls.get("license", {})
        print(f"   License: type={lic.get('license_type')}, valid={lic.get('is_valid')}, days_left={lic.get('days_left')}")

    print("\n5. 测试心跳验证...")
    r = requests.post(f"{BASE}/api/user/heartbeat", headers=headers, json={
        "fingerprint": "abc123def456",
        "app_version": "2.0.0"
    })
    print(f"   POST /api/user/heartbeat => {r.status_code}")
    if r.status_code == 200:
        hb = r.json()
        print(f"   is_valid={hb.get('is_valid')}")

    print("\n6. 测试机器绑定...")
    r = requests.post(f"{BASE}/api/user/bind_machine", headers=headers, json={
        "fingerprint": "abc123def456"
    })
    print(f"   POST /api/user/bind_machine => {r.status_code}")
    if r.status_code == 200:
        print(f"   Result: {r.json()}")

    print("\n7. 测试版本检查...")
    r = requests.get(f"{BASE}/api/version/latest", params={"current_version": "1.0.0"})
    print(f"   GET /api/version/latest => {r.status_code}")
    if r.status_code == 200:
        vi = r.json()
        print(f"   has_update={vi.get('has_update')}, version={vi.get('version')}")

    print("\n8. 测试创建支付订单...")
    r = requests.post(f"{BASE}/api/payment/create_order", headers=headers, json={
        "plan_type": "monthly",
        "payment_method": "alipay"
    })
    print(f"   POST /api/payment/create_order => {r.status_code}")
    if r.status_code == 200:
        print(f"   Order: {r.json()}")
    else:
        print(f"   Error: {r.text[:200]}")

    print("\n9. 测试激活许可证...")
    r = requests.post(f"{BASE}/api/license/activate", headers=headers, json={
        "license_key": "VG-TEST-1234-5678"
    })
    print(f"   POST /api/license/activate => {r.status_code}")
    if r.status_code != 200:
        print(f"   Expected error: {r.json().get('detail', 'N/A')}")

print("\n" + "=" * 60)
print("  ✅ 所有核心 API 测试完成!")
print("=" * 60)
