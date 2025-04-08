#!/usr/bin/env python3
import smtplib
import sys
import logging
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import (
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_SENDER
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("report_by_mail")

def send_email(subject, message, recipients, sender=EMAIL_SENDER):
    """Envoie un email via le serveur SMTP configuré."""
    try:
        # Créer le message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = ", ".join(recipients)
        
        # Ajouter le corps du message
        msg.attach(MIMEText(message, 'plain'))
        
        # Se connecter au serveur SMTP
        logger.info(f"Connexion au serveur SMTP {EMAIL_SMTP_SERVER}:{EMAIL_SMTP_PORT}")
        smtp = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        
        # Envoyer l'email
        logger.info(f"Envoi de l'email à {recipients}")
        smtp.sendmail(sender, recipients, msg.as_string())
        
        # Fermer la connexion
        smtp.quit()
        logger.info(f"Email envoyé avec succès à {recipients}")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envoie un rapport par email.")
    parser.add_argument("--subject", required=True, help="Sujet de l'email")
    parser.add_argument("--message", required=True, help="Corps du message")
    parser.add_argument("--recipients", required=True, help="Destinataires (séparés par des virgules)")
    parser.add_argument("--sender", default=EMAIL_SENDER, help="Adresse de l'expéditeur")
    
    args = parser.parse_args()
    
    recipients_list = [email.strip() for email in args.recipients.split(',')]
    
    success = send_email(args.subject, args.message, recipients_list, args.sender)
    
    if not success:
        sys.exit(1) 