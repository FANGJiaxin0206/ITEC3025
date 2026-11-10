"""Configure this computer's Gmail sender once. No email is sent by this script."""
import getpass
import json
import os
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent
    print('MediConfirm Gmail sender setup. Credentials stay in mail.local.json; never upload it.')
    sender=input('Team MediConfirm Gmail address: ').strip()
    if '@' not in sender or '\n' in sender or '\r' in sender:raise ValueError('Enter a valid Gmail address.')
    password=getpass.getpass('Google app password (hidden; not your normal account password): ').replace(' ','')
    if len(password)!=16:raise ValueError('Use the 16-character Google app password.')
    value={'smtp_host':'smtp.gmail.com','smtp_port':465,'smtp_security':'ssl','sender_email':sender,
           'sender_name':'MediConfirm','username':sender,'app_password':password}
    path=root/'mail.local.json'
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(descriptor,0o600)
    with os.fdopen(descriptor,'w') as output:output.write(json.dumps(value,indent=2)+'\n')
    print('Saved locally. In Me → Family notifications, save a recipient, enable real email alerts, then send a test email.')

if __name__=='__main__':main()
