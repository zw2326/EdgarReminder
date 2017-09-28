#!/usr/bin/python
# Script to scan Edgar, look for new financial statements for subscribed companies and send out email notification.
from bs4 import BeautifulSoup
from collections import defaultdict
from email.header import Header
from email.mime.text import MIMEText
from time import strftime, sleep, time
import os.path
import smtplib
import sys
import requests

mylist = 'mylist.txt'
mylog = os.path.sep.join(['workspace', 'mylog.log'])
emailconfigfile = 'emailconfig.ini'

smtp = ''
emailfrom = ''
emailpwd = ''
emailto = []

interval = 1800
clearcache = False
debug = False

class Cache(object):
    # Class to manage cache for each subscribed company.
    def __init__(self):
        pass

    @classmethod
    def Get(cls, symbol):
        filename = os.path.sep.join(['workspace', 'cache', '{0}.CACHE'.format(symbol)])
        if not os.path.isfile(filename):
            return ''
        return open(filename, 'r').read()

    @classmethod
    def Set(cls, symbol, content):
        filename = os.path.sep.join(['workspace', 'cache', '{0}.CACHE'.format(symbol)])
        open(filename, 'w').write(content)

    @classmethod
    def Clear(cls):
        for filename in os.listdir(os.path.sep.join(['workspace', 'cache'])):
            if filename.endswith(".CACHE"):
                os.remove(os.path.sep.join(['workspace', 'cache', filename]))


def PrepareDirs():
    if not os.path.exists('workspace'):
        os.makedirs('workspace')
    if not os.path.exists(os.path.sep.join(['workspace', 'cache'])):
        os.makedirs(os.path.sep.join(['workspace', 'cache']))

def ParseArgs():
    global debug, clearcache, emailconfigfile
    ptr = 1
    while ptr < len(sys.argv):
        if sys.argv[ptr] == '--clear':
            clearcache = True
        elif sys.argv[ptr] == '--debug':
            debug = True
        elif sys.argv[ptr] == '--email-config':
            if ptr + 1 >= len(sys.argv):
                print '--config must specify an Email config file.'
                exit(1)
            ptr += 1
            emailconfigfile = sys.argv[ptr]
        elif sys.argv[ptr] == '--help':
            print '''
Usage: python main.py [OPTIONS]
Script to scan Edgar, look for new financial statements for
subscribed companies and send out email notification.

  --clear                Clear all cache before running.
  --debug                Print out debug messages.
  --email-config FILE    Specify a Email config file.
                         Default is emailconfig.ini.
            '''
            exit(0)
        else:
            print 'Invalid argument: {0}'.format(sys.argv[ptr])
            exit(1)
        ptr += 1

def ParseEmailConfigFile():
    global smtp, emailfrom, emailpwd, emailto
    fid = open(emailconfigfile, 'r')
    smtp = fid.readline().strip()
    emailfrom = fid.readline().strip()
    emailpwd = fid.readline().strip()
    for line in fid:
        emailto.append(line.strip())
    fid.close()

# Load symbol of each subscribed company.
def LoadSymbols():
    symbols = set([])
    fid = open(mylist, 'r')
    for line in fid:
        symbols.add(line.strip())
    fid.close()
    LogDebug('Loaded symbols: {0}'.format(', '.join(symbols)))
    return symbols

# Send out emails.
def SendEmails(title, message):
    msg = MIMEText(message, 'html', 'utf-8')
    msg['Subject'] = Header(title, 'utf-8')
    msg['from'] = emailfrom
    msg['to'] = ', '.join(emailto)

    server = smtplib.SMTP_SSL(smtp)
    server.login(emailfrom.rsplit('@', 1)[0], emailpwd)
    server.sendmail(emailfrom, ', '.join(emailto), msg.as_string())
    server.quit()

def Log(message):
    fid = open(mylog, 'a')
    fid.write('[{0}] {1}\n'.format(strftime('%Y-%m-%d %H:%M:%S'), message))
    fid.close()

def LogDebug(message):
    if debug == True:
        Log('DEBUG: ' + message)

# Main loop wrapper.
def Start():
    preheartbeat = time()
    counter = 0 # number of iterations
    ecounter = 0 # number of exceptions
    urltemplate = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={0}&owner=exclude'

    while True:
        symbols = LoadSymbols()
        iteminterval = interval / len(symbols) # interval between scan for each symbol
        emailupdates = defaultdict(list) # {symbol: [filing list]}
        cacheupdates = defaultdict(str) # {symbol: cache ID}

        for symbol in symbols:
            # Scan for latest statements.
            try:
                html = requests.get(urltemplate.format(symbol)).text
            except Exception as e:
                Log('Exception while downloading: {0}'.format(str(e)))
                ecounter += 1
                if counter > 0:
                    sleep(iteminterval) # Take a nap between each symbol.
                continue

            # Parse downloaded HTML.
            try:
                soup = BeautifulSoup(html, 'lxml')
                rows = soup.find('table', {'class': 'tableFile2', 'summary': 'Results'}).find_all('tr')[1:]
                if len(rows) == 0:
                    raise Exception('no row is found')
            except Exception as e:
                Log('Exception while parsing for table rows: {0}'.format(str(e)))
                ecounter += 1
                if counter > 0:
                    sleep(iteminterval) # Take a nap between each symbol.
                continue

            # Process each statement that is newer than the cached one.
            cacheID = Cache.Get(symbol) # Load this company's cache.
            for i, row in enumerate(rows):
                tds = row.find_all('td')
                if len(tds) < 5:
                    Log('Exception while parsing row {0}: #columns = {1} < 5'.format(i, len(tds)))
                    ecounter += 1
                    break

                 # We use Edgar's file number as the unique cache ID.
                currentID = str(tds[4].find(text=True, recursive=False)).strip()
                if currentID == cacheID:
                    break
                if i == 0: # Save current ID for cache update after Email is sent.
                    cacheupdates[symbol] = currentID
                emailupdates[symbol].append((tds[0].text, tds[2].text, tds[3].text)) # Add to email update: (filing type, description, date)

            if counter > 0:
                sleep(iteminterval) # Take a nap between each symbol.

        # Assemble and send email.
        if len(emailupdates.keys()) != 0:
            title = 'Last scanned at: {0}'.format(strftime('%Y-%m-%d %H:%M:%S'))
            content = '<p>New statement{1} available for {0} symbol{1}.</p>\n'.format(len(emailupdates.keys()), '' if len(emailupdates.keys()) == 1 else 's')
            for symbol in emailupdates.keys():
                content += '<p>Symbol: <a href="{0}">{1}</a></p>\n'.format(urltemplate.format(symbol), symbol)
                for item in emailupdates[symbol]:
                    content += "<p>Filing: {0} (<small>{1}</small>)</p>\n".format(item[0], item[1].encode('utf-8'))
            LogDebug('Mail content: {0}'.format(content))
            try:
                SendEmails(title, content)
                Log('Notification Email sent')

                # Update cache.
                for symbol in cacheupdates.keys():
                    Cache.Set(symbol, cacheupdates[symbol])
            except Exception as e:
                Log('Exception while sending Email: Failed to send Email ({0})'.format(str(e)))
                ecounter += 1
        else:
            Log('No notification Email sent because scan shows no update')

        # Send heartbeat Email per day. If it fails, let the program exit.
        if int(time() - preheartbeat) > 86400:
            SendEmails('Heartbeat: {0}'.format(strftime('%Y-%m-%d %H:%M:%S')), 'Exception count: {0}'.format(str(ecounter)))
            Log('Heartbeat Email sent')
            preheartbeat = time()

        counter += 1
        sleep(iteminterval)


if __name__ == '__main__':
    PrepareDirs()
    ParseArgs()
    ParseEmailConfigFile()
    if clearcache == True:
        Cache.Clear()

    Start()
