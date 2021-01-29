#!/usr/bin/python3 -i
# Copy this file to something else and update as necessary.
# Running this script will do the following and leave you with an interactive shell
# where you can use the 'm' object.
# Output will print to the console as well as the log file.

import os
from manageGHE import manageGHE

os.environ['GHE_TOKEN']='1234567890abcdefghijklmnopqrstuvwxyz1234'
os.environ['GHE_ORG']='CPSCNNN-YYYYS-TM'
os.environ['GHE_DRYRUN']='TRUE'
m = manageGHE(logFile='cpscnnn.log')
print(m)
