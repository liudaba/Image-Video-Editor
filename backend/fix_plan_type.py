import sqlite3
conn = sqlite3.connect('videogen.db')
c = conn.cursor()

# 更新已有license记录的plan_type
c.execute("UPDATE licenses SET plan_type = 'TRIAL_15D' WHERE license_type = 'TRIAL' AND plan_type IS NULL")
print(f"Updated {c.rowcount} trial licenses with plan_type = TRIAL_15D")

c.execute("UPDATE licenses SET plan_type = 'LIFETIME' WHERE license_type = 'PRO' AND (expiry_date IS NULL OR expiry_date = '') AND plan_type IS NULL")
print(f"Updated {c.rowcount} lifetime pro licenses with plan_type = LIFETIME")

c.execute("UPDATE licenses SET plan_type = 'MONTHLY' WHERE license_type = 'PRO' AND expiry_date IS NOT NULL AND plan_type IS NULL")
print(f"Updated {c.rowcount} monthly pro licenses with plan_type = MONTHLY")

conn.commit()
conn.close()
print("Done!")
