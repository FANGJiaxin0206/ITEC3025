"""Real SMTP delivery with persisted claims; no credentials in frontend state."""
import json
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from .core import atomic_json
from .intake_store import _LOCK, _load, _moment
from .web_settings import validate_settings


def mail_config(root):
    path=Path(root)/'mail.local.json'
    try:
        value=json.loads(path.read_text())
        sender=value['sender_email'].strip();password=value['app_password'].replace(' ','')
        validate_settings({'caregiver_email':sender})
        if not sender or not password or 'YOUR_' in sender or 'YOUR_' in password:return None
        if any('\n' in str(value.get(k,'')) or '\r' in str(value.get(k,'')) for k in ('sender_email','sender_name','username','smtp_host')):return None
        port=int(value.get('smtp_port',465));security=value.get('smtp_security','ssl')
        if not 1<=port<=65535 or security not in {'ssl','starttls'}:return None
        return {**value,'sender_email':sender,'app_password':password,'smtp_port':port,'smtp_security':security}
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None


def submit_email(config,recipient,subject,body):
    message=EmailMessage();message['From']=formataddr((config.get('sender_name','MediConfirm'),config['sender_email']))
    message['To']=recipient;message['Subject']=subject;message.set_content(body)
    context=ssl.create_default_context();smtp=None;stage='connection'
    try:
        host=config.get('smtp_host','smtp.gmail.com')
        if config['smtp_security']=='ssl':smtp=smtplib.SMTP_SSL(host,config['smtp_port'],timeout=15,context=context)
        else:
            smtp=smtplib.SMTP(host,config['smtp_port'],timeout=15);smtp.ehlo();smtp.starttls(context=context);smtp.ehlo()
        smtp.login(config.get('username') or config['sender_email'],config['app_password'])
        stage='submission';refused=smtp.send_message(message)
        if refused:return 'failed','recipient_rejected'
        return 'submitted','accepted_by_email_provider'
    except smtplib.SMTPAuthenticationError:return 'failed','sender_authorization_failed'
    except (smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError):return 'failed','email_provider_rejected_message'
    except (OSError,smtplib.SMTPException):return ('delivery_unknown','check_inbox_before_retrying') if stage=='submission' else ('failed','email_connection_failed')
    finally:
        if smtp:
            try:smtp.quit()
            except Exception:pass


class EmailDelivery:
    def __init__(self,root):self.root=Path(root)
    def process(self,path,settings):
        config=mail_config(self.root);jobs=[]
        with _LOCK:
            store=_load(path);changed=False
            for key,item in store.get('simulated_notifications',{}).items():
                if item.get('delivery_status')=='sending':
                    from datetime import datetime
                    try:stale=(_moment(None)-datetime.fromisoformat(item['attempted_at'])).total_seconds()>120
                    except (ValueError,KeyError,TypeError):stale=True
                    if stale:
                        item.update(delivery_status='delivery_unknown',sent=False,delivery_reason='sending_interrupted_check_inbox');changed=True
                if item.get('delivery_status'):continue
                if not item.get('requires_delivery'):
                    item.update(delivery_status='legacy_not_sent',sent=False);changed=True;continue
                recipient=settings.get('caregiver_email','')
                item.update(simulated=False,sent=False,channel='email',recipient=recipient,
                  subject='MediConfirm: '+({'severe_discomfort':'Urgent check-in requested','test':'Email connection test'}.get(item['type'],'Medication confirmation overdue')))
                if not settings.get('real_email_enabled'):item.update(delivery_status='not_enabled',delivery_reason='real_email_alerts_are_off')
                elif not recipient:item.update(delivery_status='not_configured',delivery_reason='caregiver_email_missing')
                elif not config:item.update(delivery_status='not_configured',delivery_reason='sender_not_configured')
                else:
                    item.update(delivery_status='sending',delivery_reason='submitting_to_email_provider',attempted_at=_moment(None).isoformat())
                    jobs.append((key,recipient,item['subject'],item['message'],config))
                changed=True
            if changed:atomic_json(path,store)
        for job in jobs:threading.Thread(target=self._send,args=(path,*job),daemon=True).start()
    def _send(self,path,key,recipient,subject,body,config):
        status,reason=submit_email(config,recipient,subject,body)
        with _LOCK:
            store=_load(path);item=store['simulated_notifications'].get(key)
            if not item or item.get('delivery_status') not in {'sending','delivery_unknown'}:return
            item.update(delivery_status=status,delivery_reason=reason,sent=status=='submitted',delivery_updated_at=_moment(None).isoformat())
            atomic_json(path,store)
    def retry(self,path,key,settings):
        if not settings.get('real_email_enabled') or not mail_config(self.root) or not settings.get('caregiver_email'):
            raise ValueError('Configure the sender, save the recipient and enable real email alerts first.')
        with _LOCK:
            store=_load(path);item=store.get('simulated_notifications',{}).get(key)
            if not item or item.get('delivery_status') not in {'failed','not_configured','not_enabled'}:
                raise ValueError('This notification cannot be retried automatically.')
            item.pop('delivery_status',None);item['requires_delivery']=True
            atomic_json(path,store)
        self.process(path,settings)
