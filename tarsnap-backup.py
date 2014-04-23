#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
import argparse
import calendar
import logging
import os
import re
import shlex
import StringIO
import subprocess
import sys

class MyArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super(MyArgumentParser, self).__init__(*args, **kwargs)

    def convert_arg_line_to_args(self, line):
        for arg in shlex.split(line, comments=True):
            if not arg.strip():
                continue
            yield arg

argparser = MyArgumentParser(fromfile_prefix_chars='@')
argparser.add_argument('-v', '--verbose', action='count',
    help='Produce verbose output (can be specified more than once)')
argparser.add_argument('-n', '--dry-run', action='store_true',
    help='Do not modify anything')
argparser.add_argument('-d', '--dir', action='append', required=True,
    help='Specify a directory to backup (can be given multiple times)')
argparser.add_argument('--daily', type=int, default=7,
    help='Number of daily backups to keep (default: 7)')
argparser.add_argument('--weekly', type=int, default=4,
    help='Number of weekly backups to keep (default: 4)')
argparser.add_argument('--monthly', type=int, default=2,
    help='Number of monthly backups to keep (default: 2)')
argparser.add_argument('--weekly-day', type=int, default=0,
    help='Which day to do weekly backups on (0=monday, 6=sunday)')
argparser.add_argument('--monthly-day', type=int, default=1,
    help='Which day to do monthly backups on (1-31)')

cmdline_args = argparser.parse_args()

if cmdline_args.verbose == 1:
    loglevel = logging.INFO
elif cmdline_args.verbose >= 2:
    loglevel = logging.DEBUG
else:
    loglevel = logging.WARNING

log = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S", level=loglevel)

now = datetime.now()

backup_name = now.strftime('%Y%m%d-%H%M%S')
backup_type = None

if now.day == cmdline_args.monthly_day:
    backup_type = 'monthly'
elif calendar.weekday(now.year, now.month, now.day) == cmdline_args.weekly_day:
    backup_type = 'weekly'
else:
    backup_type = 'daily'

backup_name += '-{}'.format(backup_type)

log.debug('backup type: %s', backup_type)
log.debug('backup basename: %s', backup_name)

dirs = set(cmdline_args.dir)

def tarsnap_cmd(*args):
    cmd = ['tarsnap']
    cmd += args
    return cmd

def exec_cmd(cmd, **kwargs):
    log.debug('executing %s', ' '.join(cmd))
    subprocess.check_call(cmd, **kwargs)

# create the backups
for dir in dirs:
    cmd = tarsnap_cmd('-c', '-f', '{}-{}'.format(backup_name, dir),
        dir)
    log.info('backing up %s', dir)
    if not cmdline_args.dry_run:
        exec_cmd(cmd)

# retrieve a list of archives and remove old ones
archives = os.tmpfile()

exec_cmd(tarsnap_cmd('--list-archives'), stdout=archives,
    stderr=archives)

if cmdline_args.dry_run:
    for dir in dirs:
        archives.write('{}-{}\n'.format(backup_name, dir))

delete_archives = []

def get_oldest(lst, keep):
    return sorted(lst, reverse=True)[keep:]

for dir in dirs:
    archives.seek(0)

    re_daily = re.compile(r'^\d{8}-\d{6}-daily-' + dir)
    re_weekly = re.compile(r'^\d{8}-\d{6}-weekly-' + dir)
    re_monthly = re.compile(r'^\d{8}-\d{6}-monthly-' + dir)

    daily_archives = []
    weekly_archives = []
    monthly_archives = []

    for line in archives:
        line = line.strip()
        if re_daily.match(line):
            daily_archives.append(line)
        elif re_weekly.match(line):
            weekly_archives.append(line)
        elif re_monthly.match(line):
            monthly_archives.append(line)

    delete_archives += get_oldest(daily_archives,
        cmdline_args.daily)
    delete_archives += get_oldest(weekly_archives,
        cmdline_args.weekly)
    delete_archives += get_oldest(monthly_archives,
        cmdline_args.monthly)

archives.close()

for archive in delete_archives:
    log.info('deleting archive %s', archive)

    if not cmdline_args.dry_run:
        exec_cmd(tarsnap_cmd('-d', '-f', archive))
