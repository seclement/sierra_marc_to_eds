import os
import time
import logging
import shutil
import asyncio
import stamina
import subprocess
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

import httpx
from pydantic import BaseModel

from config import (
    CLIENT_ID,
    CLIENT_SECRET,
    TOKEN_URL,
    BIBS_URL,
    TOKEN_EXPIRATION,
    LOG_LEVEL,
    STATE_FILE_PATH,
    BATCH_SIZE,
    MARC_OUTPUT_DIR,
    BASE_PROCESSING_DIR,
    TIMEOUT_CONNECT,
    TIMEOUT_READ,
    TIMEOUT_WRITE,
    TIMEOUT_POOL,
    RETRY_ATTEMPTS,
    RETRY_INITIAL_WAIT,
    RETRY_MAX_WAIT,
    MAX_CONCURRENT_REQUESTS,
    EMAIL_RECIPIENTS,
    DAYS_TO_KEEP_LOGS,
)

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
        if filename.startswith("full_marc_fetch_") and filename.endswith(".log"):
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
log_file = os.path.join(logs_dir, f"full_marc_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, logging.StreamHandler()],
)
logger = logging.getLogger("full_marc_fetch")

# Log le nombre de fichiers supprimés
logger.info(f"Nettoyage des logs: {deleted_count} fichiers de plus de {DAYS_TO_KEEP_LOGS} jours supprimés")

# Modèles de données
class BibEntry(BaseModel):
    id: int

class BibResponse(BaseModel):
    entries: List[BibEntry]
    total: int

class MarcResponse(BaseModel):
    file: str

from email_utils import send_report_email as send_email_report

class SierraAPIAsync:
    """Classe pour interagir avec l'API Sierra de manière asynchrone."""

    def __init__(self):
        self.token: Optional[str] = None
        self.token_expiry: float = 0
        self.state_file: str = os.path.join(BASE_PROCESSING_DIR, os.path.basename(STATE_FILE_PATH))
        self.timeout = httpx.Timeout(
            connect=TIMEOUT_CONNECT,
            read=TIMEOUT_READ,
            write=TIMEOUT_WRITE,
            pool=TIMEOUT_POOL,
        )
        self.client = None
        self.marc_output_dir = os.path.join(BASE_PROCESSING_DIR, os.path.basename(MARC_OUTPUT_DIR))
        self.downloaded_files: List[str] = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.total_notices = 0  # Compteur pour le nombre total de notices

        # Création du répertoire de base s'il n'existe pas
        os.makedirs(BASE_PROCESSING_DIR, exist_ok=True)
        # Création du répertoire de sortie s'il n'existe pas
        os.makedirs(self.marc_output_dir, exist_ok=True)

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Attendre que toutes les tâches soient terminées avant de fermer le client."""
        if hasattr(self, "pending_tasks") and self.pending_tasks:
            logger.info("Attente de la fin des tâches en cours...")
            try:
                # Attendre que toutes les tâches soient terminées
                await asyncio.gather(*self.pending_tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Erreur lors de l'attente des tâches: {e}")

        # Fermer le client HTTP
        if self.client:
            await self.client.aclose()

        if exc_type:
            logger.error(f"Exception lors de l'exécution: {exc_type} - {exc_val}")
        return True

    async def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Méthode générique pour effectuer des requêtes HTTP avec stamina."""
        @stamina.retry(
            on=(httpx.HTTPError, httpx.ReadTimeout),  # Exceptions à capturer
            attempts=RETRY_ATTEMPTS,                 # Nombre de tentatives
            wait_initial=RETRY_INITIAL_WAIT,         # Délai initial
            wait_max=RETRY_MAX_WAIT,                 # Délai maximum
        )
        async def _request():
            async with self.semaphore:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response

        return await _request()

    async def get_access_token(self) -> Optional[str]:
        """Récupère un token d'accès."""
        if self.token and time.time() < self.token_expiry:
            return self.token

        try:
            response = await self._make_request(
                "POST",
                TOKEN_URL,
                auth=(CLIENT_ID, CLIENT_SECRET),
                data={"grant_type": "client_credentials"},
            )
            data = response.json()
            self.token = data.get("access_token")
            self.token_expiry = time.time() + TOKEN_EXPIRATION
            logger.debug("Nouveau token d'accès récupéré")
            return self.token
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du token: {e}")
            return None

    def load_last_start_id(self) -> int:
        """Charge le dernier start_id depuis un fichier."""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as file:
                return int(file.read().strip())
        return 0

    def save_last_start_id(self, start_id: int) -> None:
        """Sauvegarde le dernier start_id dans un fichier."""
        with open(self.state_file, "w") as file:
            file.write(str(start_id))
        logger.debug(f"ID de départ sauvegardé: {start_id}")

    async def get_bib_ids(self, start_id: int) -> Tuple[List[BibEntry], int]:
        """Récupère un lot d'IDs de bibliothèque."""
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BIBS_URL}?id=[{start_id},]&deleted=false&suppressed=false&limit={BATCH_SIZE}&fields=id"

        response = await self._make_request("GET", url, headers=headers)
        data = response.json()
        response_obj = BibResponse(**data)
        return response_obj.entries, response_obj.total

    async def get_marc_file_url(self, start_id: int, end_id: int) -> Optional[str]:
        """Récupère l'URL du fichier MARC pour un intervalle d'IDs."""
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        marc_url = f"{BIBS_URL}/marc?id=[{start_id},{end_id}]&mapping=gates&deleted=false&suppressed=false&limit={BATCH_SIZE}"

        response = await self._make_request("GET", marc_url, headers=headers)
        marc_data = response.json()
        response_obj = MarcResponse(**marc_data)
        return response_obj.file

    async def download_file(self, url: str, filename: str) -> bool:
        """Télécharge un fichier MARC."""
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        file_path = os.path.join(self.marc_output_dir, filename)

        response = await self._make_request("GET", url, headers=headers)
        with open(file_path, "wb") as file:
            file.write(response.content)

        self.downloaded_files.append(file_path)
        logger.info(f"Fichier téléchargé: {filename} (Total: {len(self.downloaded_files)})")
        logger.debug(f"Fichier ajouté à la liste: {file_path}")
        return True

    async def delete_file(self, file_id: str) -> bool:
        """Supprime un fichier MARC après téléchargement."""
        delete_url = f"{BIBS_URL}/marc/files/{file_id}"
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        await self._make_request("DELETE", delete_url, headers=headers)
        logger.info(f"Fichier supprimé: {file_id}")
        return True

    def merge_marc_files(self, output_filename: str = "full_marc.mrc") -> str:
        """Fusionne tous les fichiers MARC téléchargés en un seul fichier."""
        if not self.downloaded_files:
            logger.warning("Aucun fichier à fusionner.")
            return ""

        output_path = os.path.join(self.marc_output_dir, output_filename)
        temp_dir = os.path.join(self.marc_output_dir, "processed")
        os.makedirs(temp_dir, exist_ok=True)  # Créer un répertoire temporaire

        # Trier les fichiers par nom pour maintenir l'ordre des IDs
        sorted_files = sorted(self.downloaded_files)

        try:
            # Ouvrir le fichier de sortie en mode binaire
            with open(output_path, 'wb') as outfile:
                for file_path in sorted_files:
                    if os.path.exists(file_path):
                        logger.debug(f"Fusion du fichier: {file_path}")
                        with open(file_path, 'rb') as infile:
                            # Copier le contenu
                            shutil.copyfileobj(infile, outfile)

                        # Déplacer le fichier traité vers le répertoire temporaire
                        processed_path = os.path.join(temp_dir, os.path.basename(file_path))
                        shutil.move(file_path, processed_path)
                    else:
                        logger.warning(f"Fichier manquant: {file_path}")

            logger.info(f"Fusion terminée. Fichier combiné: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Erreur lors de la fusion des fichiers: {e}")
            return ""

    async def process_id_range(self, start_id: int, end_id: int) -> bool:
        """Traite un intervalle d'IDs pour récupérer les fichiers MARC."""
        try:
            file_url = await self.get_marc_file_url(start_id, end_id)
            if file_url:
                file_id = file_url.split("/")[-1]
                filename = f"marc_{start_id}_{end_id}.mrc"
                await self.download_file(file_url, filename)
                await self.delete_file(file_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Erreur lors du traitement de l'intervalle {start_id}-{end_id}: {e}")
            return False

    async def fetch_bibs_async(self, start_id: Optional[int] = None, auto_merge: bool = True) -> None:
        """Traitement asynchrone pour récupérer les fichiers MARC."""
        current_id = start_id if start_id is not None else self.load_last_start_id()
        logger.info(f"Démarrage du traitement asynchrone à partir de l'ID: {current_id}")

        self.pending_tasks = []  # Liste pour suivre les tâches en cours
        success = False
        
        # Obtenir la boucle d'événements actuelle
        current_loop = asyncio.get_running_loop()

        try:
            while True:
                try:
                    entries, total = await self.get_bib_ids(current_id)
                except ValueError:
                    # Gestion du cas où get_bib_ids ne retourne pas deux valeurs (à la fin)
                    logger.info("Réponse API incomplète - probablement fin des données.")
                    entries, total = [], None

                if not entries or not total:
                    logger.info("Fin des données.")
                    success = True
                    break

                last_id = entries[-1].id
                batch_count = len(entries)  # Nombre de notices dans ce lot
                self.total_notices += batch_count  # Ajouter au total
                logger.info(f"Intervalle récupéré: {current_id} - {last_id} (Notices dans ce lot: {batch_count}, Total cumulé: {self.total_notices})")

                # Créer une tâche pour traiter cet intervalle en utilisant la boucle actuelle
                task = current_loop.create_task(self.process_id_range(current_id, last_id))
                self.pending_tasks.append(task)

                # Préparer l'itération suivante
                next_id = int(last_id) + 1
                self.save_last_start_id(next_id)
                current_id = next_id

                # Attendre si trop de tâches sont en cours
                if len(self.pending_tasks) >= MAX_CONCURRENT_REQUESTS * 2:
                    # Attendre qu'au moins une tâche se termine
                    done, pending = await asyncio.wait(
                        self.pending_tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    # Convertir le set pending en liste
                    self.pending_tasks = list(pending)
                    # Vérifier s'il y a des erreurs
                    for task in done:
                        try:
                            if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                                logger.error(f"Tâche échouée: {task.exception()}")
                        except asyncio.InvalidStateError:
                            # La tâche n'est peut-être pas encore terminée
                            pass

        except KeyboardInterrupt:
            logger.info("Interruption par l'utilisateur. État sauvegardé.")
            for task in self.pending_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self.pending_tasks, return_exceptions=True)

        finally:
            # Attendre que toutes les tâches soient terminées
            if self.pending_tasks:
                logger.info("Attente de la fin des tâches en cours...")
                await asyncio.gather(*self.pending_tasks, return_exceptions=True)

            # Afficher le nombre total de fichiers téléchargés
            logger.info(f"Nombre total de fichiers MARC téléchargés: {len(self.downloaded_files)}")
            logger.info(f"Nombre total de notices bibliographiques traitées: {self.total_notices}")

            # Fusionner les fichiers à la fin, quelle que soit la façon dont on arrive ici
            if auto_merge and self.downloaded_files:
                logger.info(f"Fusion des {len(self.downloaded_files)} fichiers téléchargés...")
                logger.debug(f"Fichiers à fusionner: {self.downloaded_files}")  # Log pour déboguer
                output_filename = "full_marc.mrc"
                self.merge_marc_files(output_filename)
            
            # Supprimer les fichiers et répertoires si tout s'est bien passé
            if success:
                logger.info("Suppression des fichiers et répertoires temporaires...")
                try:
                    # Supprimer last_start_id.txt
                    if os.path.exists(self.state_file):
                        os.remove(self.state_file)
                        logger.info(f"Fichier supprimé: {self.state_file}")

                    # Supprimer le répertoire processed et son contenu
                    processed_dir = os.path.join(self.marc_output_dir, "processed")
                    if os.path.exists(processed_dir):
                        shutil.rmtree(processed_dir)
                        logger.info(f"Répertoire supprimé: {processed_dir}")
                
                except Exception as e:
                    logger.error(f"Erreur lors de la suppression des fichiers/répertoires: {e}")

    def send_report_email(self, success=True, error_message=None):
        """Envoie un email de rapport d'exécution."""
        return send_email_report(
            email_script=email_script,
            marc_output_dir=self.marc_output_dir,
            output_filename="full_marc.mrc",
            downloaded_files_count=len(self.downloaded_files),
            total_notices=self.total_notices,
            success=success,
            error_message=error_message,
            recipients=EMAIL_RECIPIENTS,
            is_daily=False
        )

    def transfer_file(self, local_file_path, remote_directory):
            """Transfère un fichier sur le serveur SFTP."""
            try:
                subprocess.run(["python3", sftp_script, local_file_path, remote_directory], check=True)
                logger.info(f"Fichier {local_file_path} transféré vers {remote_directory} sur le serveur SFTP.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Erreur lors du transfert du fichier: {e}")
            except Exception as e:
                logger.error(f"Erreur inattendue lors du transfert du fichier: {e}")

async def main(api: SierraAPIAsync):
    """Fonction principale asynchrone."""
    success = True
    error_message = None
    
    try:
        async with api:
            await api.fetch_bibs_async()
    except KeyboardInterrupt:
        error_message = "Programme interrompu par l'utilisateur."
        logger.info(error_message)
        success = False
    except Exception as e:
        error_message = str(e)
        logger.exception(f"Erreur fatale: {e}")
        success = False
    finally:
        logger.info("Programme terminé.")
        return success, error_message

if __name__ == "__main__":
    api = SierraAPIAsync()
    
    # Utiliser run_until_complete au lieu de asyncio.run pour éviter une nouvelle boucle
    loop = asyncio.get_event_loop()
    success, error_message = loop.run_until_complete(main(api))
    
    # Assurer que toutes les tâches sont terminées avant de continuer
    loop.run_until_complete(asyncio.sleep(1))
    
    # Transférer le fichier fusionné après l'exécution principale
    output_filename = "full_marc.mrc"
    output_path = os.path.join(api.marc_output_dir, output_filename)
    
    try:
        if os.path.exists(output_path):
            logger.info(f"Le fichier {output_path} existe et va être transféré")
            api.transfer_file(output_path, "//full")
        else:
            error_message = f"Le fichier {output_path} n'existe pas, impossible de le transférer"
            logger.error(error_message)
            success = False
    except Exception as e:
        error_message = str(e)
        logger.error(f"Erreur lors du transfert du fichier fusionné: {e}")
        success = False
    
    # Envoyer un rapport par email à la fin de l'exécution
    api.send_report_email(success, error_message)
    
    # Fermer proprement la boucle d'événements
    loop.close()