import sqlite3
conn = sqlite3.connect('videogen.db')
c = conn.cursor()

# 添加 plan_type 列到 licenses 表
try:
    c.execute("ALTER TABLE licenses ADD COLUMN plan_type VARCHAR(20) DEFAULT 'TRIAL_15D'")
    print("Added plan_type column to licenses table")
except Exception as e:
    print(f"plan_type column may already exist: {e}")

conn.commit()

# 验证
c.execute("PRAGMA table_info(licenses)")
cols = [col[1] for col in c.fetchall()]
print(f"licenses columns: {cols}")

conn.close()
