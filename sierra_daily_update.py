import os
import time
import logging
import httpx
from datetime import datetime, timedelta
import shutil
import subprocess
import sys
from config import (
    CLIENT_ID,
    CLIENT_SECRET,
    TOKEN_URL,
    BIBS_URL,
    TOKEN_EXPIRATION,
    LOG_LEVEL,
    DAYS_TO_KEEP_LOGS,
    MARC_OUTPUT_DIR,
    BASE_PROCESSING_DIR,
    TIMEOUT_CONNECT,
    TIMEOUT_READ,
    TIMEOUT_WRITE,
    TIMEOUT_POOL,
    EMAIL_RECIPIENTS
)

OUTPUT_FILENAME = "daily_marc.mrc"

# Chemin absolu vers les scripts
script_dir = os.path.dirname(os.path.abspath(__file__))
sftp_script = os.path.join(script_dir, "sftp_transfer.py")
email_script = os.path.join(script_dir, "report_by_mail.py")

# Configuration du répertoire de logs
logs_dir = os.path.join(BASE_PROCESSING_DIR, "logs")
os.makedirs(logs_dir, exist_ok=True)

# Fonction pour supprimer les logs de plus de X jours
def cleanup_old_logs(log_dir, days_to_keep=30):
    """Supprime les fichiers de log de plus de X jours."""
    now = datetime.now()
    cutoff = now - timedelta(days=days_to_keep)
    
    count = 0
    for filename in os.listdir(log_dir):
        if filename.startswith("daily_marc_fetch_") and filename.endswith(".log"):
            filepath = os.path.join(log_dir, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff:
                    os.remove(filepath)
                    count += 1
    
    return count

# Supprimer les anciens logs
deleted_count = cleanup_old_logs(logs_dir, DAYS_TO_KEEP_LOGS)

# Configuration du logging avec un fichier horodaté dans le répertoire de logs
log_file = os.path.join(logs_dir, f"daily_marc_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, logging.StreamHandler()],
)
logger = logging.getLogger("daily_marc_fetch")

# Log le nombre de fichiers supprimés
logger.info(f"Nettoyage des logs: {deleted_count} fichiers de plus de 30 jours supprimés")

from email_utils import send_report_email as send_email_report

class SierraAPISync:
    def __init__(self):
        self.token = None
        self.token_expiry = 0
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=TIMEOUT_CONNECT,
                read=TIMEOUT_READ,
                write=TIMEOUT_WRITE,
                pool=TIMEOUT_POOL,
            )
        )
        self.marc_output_dir = os.path.join(BASE_PROCESSING_DIR, os.path.basename(MARC_OUTPUT_DIR))
        # Création du répertoire de base s'il n'existe pas
        os.makedirs(BASE_PROCESSING_DIR, exist_ok=True)
        # Création du répertoire de sortie s'il n'existe pas
        os.makedirs(self.marc_output_dir, exist_ok=True)
        self.downloaded_files = []
        self.total_notices = 0  # Compteur pour le nombre total de notices

    def get_access_token(self):
        """Récupère un token d'accès."""
        if self.token and time.time() < self.token_expiry:
            return self.token

        response = self.client.post(
            TOKEN_URL,
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        data = response.json()
        self.token = data.get("access_token")
        self.token_expiry = time.time() + TOKEN_EXPIRATION
        logger.debug("Nouveau token d'accès récupéré")
        return self.token

    def fetch_updated_bibs(self):
        """Récupère les fichiers MARC mis à jour pour aujourd'hui."""
        token = self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        today = datetime.now().strftime("%Y-%m-%d")

        start_id = 0
        while True:
            # Vérifier combien d'enregistrements ont été mis à jour aujourd'hui
            url = f"{BIBS_URL}?updatedDate=[{today},]&limit=2000&fields=id&offset={start_id}"
            response = self.client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            entries = data.get("entries", [])
            total_entries = len(entries)

            if total_entries == 0:
                logger.info("Aucune nouvelle donnée à récupérer ou fin des enregistrements.")
                break

            self.total_notices += total_entries  # Ajouter au total
            logger.info(f"Récupération des enregistrements de l'ID {start_id} à {start_id + total_entries - 1} (Notices dans ce lot: {total_entries}, Total cumulé: {self.total_notices})")

            # Récupérer le fichier MARC pour ce lot
            marc_url = f"{BIBS_URL}/marc?mapping=gates&limit=2000&updatedDate=[{today},]&offset={start_id}"
            response = self.client.get(marc_url, headers=headers)
            response.raise_for_status()
            marc_data = response.json()
            file_url = marc_data.get("file")

            if file_url:
                filename = f"marc_updated_{today}_{start_id}.mrc"
                self.download_file(file_url, filename)

                # Supprimer le fichier après téléchargement
                file_id = file_url.split("/")[-1]
                self.delete_file(file_id)

            # Si moins de 2000 entrées ont été récupérées, sortir de la boucle
            if total_entries < 2000:
                break

            start_id += total_entries

        # Afficher le nombre total de fichiers téléchargés et de notices traitées
        logger.info(f"Nombre total de fichiers MARC téléchargés: {len(self.downloaded_files)}")
        logger.info(f"Nombre total de notices bibliographiques traitées: {self.total_notices}")
            
        # Fusionner les fichiers téléchargés
        self.merge_marc_files()

    def download_file(self, url, filename):
        """Télécharge un fichier MARC."""
        token = self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        file_path = os.path.join(self.marc_output_dir, filename)

        response = self.client.get(url, headers=headers)
        response.raise_for_status()

        with open(file_path, "wb") as file:
            file.write(response.content)

        self.downloaded_files.append(file_path)
        logger.info(f"Fichier téléchargé: {filename} (Total: {len(self.downloaded_files)})")
        logger.debug(f"Fichier ajouté à la liste: {file_path}")

    def delete_file(self, file_id):
        """Supprime un fichier MARC après téléchargement."""
        delete_url = f"{BIBS_URL}/marc/files/{file_id}"
        token = self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.delete(delete_url, headers=headers)
        response.raise_for_status()
        logger.info(f"Fichier supprimé: {file_id}")

    def merge_marc_files(self, output_filename=OUTPUT_FILENAME):
        """Fusionne tous les fichiers MARC téléchargés en un seul fichier."""
        if not self.downloaded_files:
            logger.warning("Aucun fichier à fusionner.")
            return

        output_path = os.path.join(self.marc_output_dir, output_filename)
        try:
            logger.info(f"Fusion des {len(self.downloaded_files)} fichiers téléchargés...")
            logger.debug(f"Fichiers à fusionner: {self.downloaded_files}")  # Log pour déboguer
            
            with open(output_path, 'wb') as outfile:
                for file_path in self.downloaded_files:
                    if os.path.exists(file_path):
                        logger.debug(f"Fusion du fichier: {file_path}")
                        with open(file_path, 'rb') as infile:
                            shutil.copyfileobj(infile, outfile)
                        os.remove(file_path)  # Supprimer le fichier après fusion
                    else:
                        logger.warning(f"Fichier manquant: {file_path}")

            logger.info(f"Fusion terminée. Fichier combiné: {output_path}")

        except Exception as e:
            logger.error(f"Erreur lors de la fusion des fichiers: {e}")
    
    def transfer_file(self, local_file_path, remote_directory):
        """Transfère un fichier sur le serveur SFTP."""
        try:
            subprocess.run(["python3", sftp_script, local_file_path, remote_directory], check=True)
            logger.info(f"Fichier {local_file_path} transféré vers {remote_directory} sur le serveur SFTP.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur lors du transfert du fichier: {e}")

    def send_report_email(self, success=True, error_message=None):
        """Envoie un email de rapport d'exécution."""
        return send_email_report(
            email_script=email_script,
            marc_output_dir=self.marc_output_dir,
            output_filename=OUTPUT_FILENAME,
            downloaded_files_count=len(self.downloaded_files),
            total_notices=self.total_notices,
            success=success,
            error_message=error_message,
            recipients=EMAIL_RECIPIENTS,
            is_daily=True
        )

if __name__ == "__main__":
    api = SierraAPISync()
    success = True
    error_message = None
    
    try:
        api.fetch_updated_bibs()
        
        # Transférer le fichier fusionné après l'exécution principale
        output_path = os.path.join(api.marc_output_dir, OUTPUT_FILENAME)
        if os.path.exists(output_path):
            logger.info(f"Le fichier {output_path} existe et va être transféré")
            api.transfer_file(output_path, "//update")
        else:
            error_message = f"Le fichier {output_path} n'existe pas, impossible de le transférer"
            logger.error(error_message)
            success = False
    except Exception as e:
        error_message = str(e)
        logger.exception("Erreur pendant l'exécution du programme")
        success = False
    
    finally:
        # Envoyer un rapport par email à la fin de l'exécution
        api.send_report_email(success, error_message)