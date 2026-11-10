# Team MediConfirm Gmail setup

This project uses Python's built-in smtplib. Everyone uses the team's sender account; caregivers are recipients, not sender accounts. Sender setup is once per backend computer, not once per run. A future central backend would need setup only on that server.

1. The owner signs in to the team Gmail account and enables Google 2-Step Verification.
2. The owner creates a Google app password for this computer, with a distinct name such as MediConfirm-Laptop. Do not use the account's ordinary password. If Google does not offer app passwords for the account, stop and use an approved OAuth-based setup; do not disable account protections.
3. In the project folder, run:

   ```bash
   python configure_email.py
   ```

4. Enter the team Gmail address and app password locally. The app password is hidden while entered. The script writes mail.local.json with owner-only permissions and does not send a message.
5. Open Me → Family notifications, enter the recipient address, select Send real email alerts to this address, and save.
6. Click Send test email yourself. Check both the delivery record and recipient inbox/spam folder.

For another computer, repeat the setup using the same team sender and a separate app password. Do not distribute mail.local.json through GitHub or chat. Restarting the program reuses its local configuration. Revoking/changing the authorization requires configuring it again.

The default transport is smtp.gmail.com port 465 with verified TLS. An advanced sender can use the fields in mail.example.json; the module also supports STARTTLS. Credentials never enter browser state.

Notification outcomes are Not enabled, Not configured, Sending, Submitted, Failed or Delivery uncertain. Submission does not prove delivery or that a person read the message. Failed/not-configured notices can be retried explicitly. Unknown transmissions are not retried automatically because the provider may already have accepted them. Closing the app during a send can leave an uncertain result; check the inbox first.

Historic previews are kept as history and never automatically sent. Severe-discomfort handling displays its help message immediately; it does not wait for an email connection.

Official references: [Google app passwords](https://support.google.com/mail/answer/185833?hl=en), [Gmail SMTP](https://developers.google.com/workspace/gmail/imap/imap-smtp).
