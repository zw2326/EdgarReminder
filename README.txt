Script to scan Edgar, look for new financial statements for subscribed companies and send out email notification.
To use it, you need to create two files:
1. emailconfig.ini (or any other file and specify the "--email-config" option, see script's usage via "--help" option), which has the following format:
[LINE 1] SMTP_HOST:SMTP_PORT
[LINE 2] FROM_EMAIL
[LINE 3] FROM_EMAIL_PASSWORD
[LINE 4] TO_EMAIL1
[LINE 5] TO_EMAIL2 (optional)
...

2. mylist.txt, each line should be a valid stock symbol.
