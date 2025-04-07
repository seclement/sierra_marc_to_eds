import os
import time
import paramiko
import sys
import logging
from config import (
    SFTP_HOST,
    SFTP_USERNAME,
    SFTP_PASSWORD,
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sftp_transfer")

def upload_file_to_sftp(local_file_path, remote_directory, max_retries=3, delay=5):
    """Envoie un fichier sur un serveur SFTP avec remplacement complet du fichier."""
    attempt = 0
    while attempt < max_retries:
        try:
            transport = paramiko.Transport((SFTP_HOST, 22))
            transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
            sftp = paramiko.SFTPClient.from_transport(transport)


            remote_file_path = f"{remote_directory.rstrip('/')}/{os.path.basename(local_file_path)}"
            
            # Vérifier si le fichier existe déjà et le supprimer
            try:
                sftp.stat(remote_file_path)
                logger.info(f"Le fichier {remote_file_path} existe déjà, suppression avant remplacement")
                sftp.remove(remote_file_path)
            except IOError:
                # Le fichier n'existe pas, c'est normal
                pass

            # Uploader le fichier complet
            file_size = os.path.getsize(local_file_path)
            with open(local_file_path, 'rb') as f:
                sftp.putfo(f, remote_file_path, file_size=file_size)

            logger.info(f"Fichier {local_file_path} ({file_size} octets) envoyé sur le serveur SFTP sous le nom {remote_file_path}")
            sftp.close()
            transport.close()
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du fichier sur le serveur SFTP: {e}")

        attempt += 1
        logger.info(f"Tentative {attempt}/{max_retries} échouée. Nouvelle tentative dans {delay} secondes...")
        time.sleep(delay)

    logger.error(f"Échec de l'envoi du fichier après {max_retries} tentatives.")
    return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        logger.error("Usage: python sftp_transfer.py <local_file_path> <remote_directory>")
        sys.exit(1)

    local_file_path = sys.argv[1]
    remote_directory = sys.argv[2]

    if not upload_file_to_sftp(local_file_path, remote_directory):
        logger.error("Le transfert du fichier a échoué après plusieurs tentatives.")