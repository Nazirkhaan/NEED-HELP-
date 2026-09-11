import psycopg

conn = psycopg.connect(
    "dbname=sih26044 user=sih password=sih host=192.168.162.220 port=5432",
    autocommit=True,
)
cur = conn.cursor()
cur.execute(
    """
    select u.email, r.name as role, u.password_hash, u.is_active
    from users u
    join roles_permissions r on r.id = u.role_id
    order by u.email
    limit 50
    """
)
rows = cur.fetchall()
for row in rows:
    print(row)
print("count=", len(rows))
conn.close()
