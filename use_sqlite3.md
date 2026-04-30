# sqlite3
连接数据库
创建游标（cursor）
执行 SQL
提交（commit）
关闭连接
# 示例
```
import sqlite3

# 1️⃣ 连接数据库（没有就会自动创建 test.db）
conn = sqlite3.connect("test.db")

# 2️⃣ 创建游标
cursor = conn.cursor()

# 3️⃣ 创建表
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER
)
""")

# 4️⃣ 插入数据
cursor.execute("INSERT INTO users (name, age) VALUES (?, ?)", ("Alice", 20))
cursor.execute("INSERT INTO users (name, age) VALUES (?, ?)", ("Bob", 25))

# 5️⃣ 提交
conn.commit()

# 6️⃣ 查询数据
cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()

for row in rows:
    print(row)

# 7️⃣ 关闭
cursor.close()
conn.close()

```