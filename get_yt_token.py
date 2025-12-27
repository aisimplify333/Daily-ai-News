import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Make sure 'client_secret.json' is the name of the file you downloaded
CLIENT_SECRET_FILE = 'client_secret.json' 
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
credentials = flow.run_local_server(port=0)

print(f"\n✅ YOUR REFRESH TOKEN: {credentials.refresh_token}")
