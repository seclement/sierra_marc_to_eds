# config.py - Configuration pour l'API Sierra
from dotenv import load_dotenv
import os

# Charger les variables d'environnement depuis .env
load_dotenv()

# Credentials pour l'API Sierra
API_URL = os.getenv("API_URL")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Credentials pour le serveur SFTP
SFTP_HOST = os.getenv("SFTP_HOST")
SFTP_USERNAME = os.getenv("SFTP_USERNAME")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")

# URLs dérivées
TOKEN_URL = f"{API_URL}token"
BIBS_URL = f"{API_URL}bibs"

# Durée de validité du token en secondes (5 min)
TOKEN_EXPIRATION = 300

# Paramètres d'exécution
BASE_PROCESSING_DIR = os.getenv("BASE_PROCESSING_DIR")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2000"))  # Nombre d'éléments à récupérer par lot
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "last_start_id.txt")
MARC_OUTPUT_DIR = os.getenv("MARC_OUTPUT_DIR", "marc_files")

# Paramètres de logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR, CRITICAL
DAYS_TO_KEEP_LOGS = int(os.getenv("DAYS_TO_KEEP_LOGS", "30"))

# Paramètres de timeout (en secondes)
TIMEOUT_CONNECT = float(os.getenv("TIMEOUT_CONNECT", "10.0"))
TIMEOUT_READ = float(os.getenv("TIMEOUT_READ", "60.0"))
TIMEOUT_WRITE = float(os.getenv("TIMEOUT_WRITE", "10.0"))
TIMEOUT_POOL = float(os.getenv("TIMEOUT_POOL", "10.0"))

# Paramètres de retry
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_INITIAL_WAIT = float(os.getenv("RETRY_INITIAL_WAIT", "1.0"))
RETRY_MAX_WAIT = float(os.getenv("RETRY_MAX_WAIT", "10.0"))

MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))

# Paramètres Email
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS")
