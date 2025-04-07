import os
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

def send_report_email(email_script, marc_output_dir, output_filename, downloaded_files_count, total_notices, success=True, error_message=None, recipients=None, is_daily=True):
    """
    Envoie un email de rapport d'exécution.
    
    Args:
        email_script (str): Chemin vers le script d'envoi d'email
        marc_output_dir (str): Répertoire de sortie des fichiers MARC
        output_filename (str): Nom du fichier de sortie
        downloaded_files_count (int): Nombre de fichiers téléchargés
        total_notices (int): Nombre total de notices traitées
        success (bool): Indique si le traitement s'est terminé avec succès
        error_message (str): Message d'erreur en cas d'échec
        recipients (str): Destinataires de l'email
        is_daily (bool): Indique s'il s'agit du traitement quotidien ou complet
    
    Returns:
        bool: True si l'email a été envoyé avec succès, False sinon
    """
    try:
        # Préparer le contenu du rapport
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Déterminer le type de transfert (quotidien ou complet)
        transfer_type = "quotidien" if is_daily else "complet"
        
        # Ajouter l'indicateur visuel dans le sujet
        status_icon = "✅" if success else "❌"
        subject = f"[Sierra MARC to EDS] {status_icon} Rapport d'exécution du transfert {transfer_type} - {today}"
        
        if success:
            message = f"""
Rapport d'exécution Sierra MARC du {today}

✅ Le traitement s'est terminé avec succès.

📊 Statistiques:
- Fichiers téléchargés: {downloaded_files_count}
- Notices traitées: {total_notices}
- Fichier fusionné: {os.path.join(marc_output_dir, output_filename)}
- Transfert SFTP: Réussi

"""
        else:
            message = f"""
Rapport d'exécution Sierra MARC - {today}

❌ Le traitement a rencontré des erreurs.

📊 Statistiques:
- Fichiers téléchargés: {downloaded_files_count}
- Notices traitées: {total_notices}

❌ Erreur: {error_message}

"""
        
        # Exécuter le script d'envoi d'email
        logger.info(f"Envoi du rapport par email à {recipients}")
        subprocess.run([
            "python3", 
            email_script, 
            "--subject", subject, 
            "--message", message, 
            "--recipients", recipients
        ], check=True)
        
        logger.info(f"Rapport envoyé avec succès")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi du rapport par email: {e}")
        return False