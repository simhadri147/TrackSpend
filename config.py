# config.py

MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = ''
MYSQL_DB = 'expense_tracker'
MYSQL_CURSORCLASS = 'DictCursor'

# Flask secret key
SECRET_KEY = '1234567890'

# Mail config (Use Gmail for now)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'abhiram09882@gmail.com'       # ⚠️ Your Gmail
MAIL_PASSWORD = 'ghimrdolykuvvrkg'          # ⚠️ App Password (not Gmail password)
