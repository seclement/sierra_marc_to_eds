# Sierra MARC Export System

A Python-based system for exporting MARC records from Sierra ILS and transferring them to an SFTP server. The system supports both full exports and daily incremental updates.

## Features

- Full export of all MARC records from Sierra ILS
- Daily incremental updates of modified records
- Asynchronous processing for improved performance
- Automatic file merging
- SFTP transfer to remote server
- Email reporting of execution results
- Automatic log rotation and cleanup

## Requirements

- Python 3.7+
- Required Python packages (see `requirements.txt`)
- Sierra API credentials
- SFTP server access

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/sierra-marc-export.git
   cd sierra-marc-export

2. Install required packages:
   ```bash
   pip install -r requirements.txt

3. Create a .env file based on the provided .env.sample :
   ```bash
   cp .env.sample .env

4. Update the.env file with your Sierra API credentials and SFTP server details.

## Configuration
The system uses a combination of environment variables (loaded from .env ) and default values in config.py . Key configuration parameters include:

- BASE_PROCESSING_DIR : Base directory for all processing files
- API_URL : Sierra API base URL
- CLIENT_ID and CLIENT_SECRET : Sierra API credentials
- SFTP_HOST , SFTP_USERNAME , and SFTP_PASSWORD : SFTP server credentials
- BATCH_SIZE : Number of records to process in each batch
- MAX_CONCURRENT_REQUESTS : Maximum number of concurrent API requests
- DAYS_TO_KEEP_LOGS : Number of days to keep log files before cleanup
See config.py for all available configuration options and their default values.

## Usage
### Full Export
To perform a full export of all MARC records:
```bash
python sierra_full_export.py
```
This will:

1. Fetch all bibliographic records from Sierra
2. Download MARC files for each batch
3. Merge all files into a single MARC file
4. Transfer the merged file to the SFTP server
5. Send an email report of the operation

### Daily Incremental Update
To perform a daily incremental update of modified records:
```bash
python sierra_daily_update.py
```

## File Structure
- sierra_full_export.py : Main script for full export
- sierra_daily_update.py : Main script for daily updates
- sftp_transfer.py : Handles SFTP file transfers
- email_utils.py : Utilities for sending email reports
- config.py : Configuration loading and defaults
- .env : Environment-specific configuration (not in Git)
- .env.sample : Template for creating your own .env file

## Logging
Logs are stored in the logs directory under the base processing directory. Log files are automatically rotated and cleaned up after the number of days specified in the DAYS_TO_KEEP_LOGS configuration.

## License
## License
GNU General Public License v3.0 (GPL-3.0)

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html) for more details.

## Contributors
Sébastien Clément / Bibliothèque interuniversitaire de la Sorbonne  
Email: sebastien.clement@bis-sorbonne.fr