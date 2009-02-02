#!/bin/sh
# autoadmin - for automating the pressing or clicking of buttons in the
#   GSA Administrative Interface
# Version 1.0 by Gregg Bloom for Google on 2007.09.17
# Released under Apache License, Version 2.0
#   http://www.apache.org/licenses/LICENSE-2.0.html

#####
#
# REQUIREMENTS
#
#   This program requires that curl is installed.  Command line options of curl
#   have changed over time and aren't backwards compatible.  This script has
#   been tested against curl version 7.18.0, which worked fine, and also
#   curl version 7.8.0, which didn't work at all.  At the time of writing,
#   the lastest stable version of curl, 7.19.3, should work fine, and it can
#   be downloaded from http://curl.haxx.se/.
#
#####
#
# NOTES
#
#   This program contains a plaintext administrative password.  It is
#   recommended that this program be stored as viewable and executable only
#   to the person who needs to run the program.  I.e., when you're done,
#      chmod 500 autoadmin*
#
#####

#####
#
# CONFIGURATION VARIABLES
#

TEMPORARY_FILE_LOCATION=/tmp
# Where do you want to store your temporary files?  /tmp is a good place unless
# you know of a better one...

CURL_EXECUTABLE_LOCATION=/usr/bin/curl
# You can typically type "which curl" at the command prompt in order to find
# the path for your curl executable.  Mine is in /usr/bin, so I enter
# /usr/bin/curl here.
# Don't have curl installed yet?!  curl can be found here:
#   http://curl.haxx.se/

USE_HTTPS="N"
# Set USE_HTTPS to "Y" if you want to use HTTPS (SSL security) for your
# requests.  Curl will need to include this functionality, as well.  Otherwise,
# setting USE_HTTPS to "N" will just use standard (unsecured) HTTP.

GSA_WEB_IP_ADDRESS='1.1.1.1'
# Theoretically, a host name will also be sufficient, but to play it safe,
# you can type "nslookup -sil {GSA HOSTNAME}" and use the IP address provided
# in the output.

GSA_ADMIN_LOGIN='admin'
# The admin login for your appliance.  May be 'admin', however for tracking
# purposes you may want to create a separate login just for this program.

GSA_ADMIN_PASSWORD=''
# The password for the above login...

GSA_ADMIN_SUBMIT_PAGE=''
# The GSA_ADMIN_SUBMIT_PAGE is the key part of the automation - this is a URL
# to request in order to affect the desired change, just don't include the
# "http://{IP}:8000" part.  Start with the "/".
# Here's an example value you could use if you wanted to change the appliance's
# User Agent:
# GSA_ADMIN_SUBMIT_PAGE='/EnterpriseController?actionType=httpHeaders&userAgent=gsa-crawler-myip&addHTTPHdrs=&httpHeadersSave=Update%20Header%20Settings'
# Yeah, it's a pretty silly example, but it at least demonstrates how you can
# parse through the HTML of any Admin page in order to find all the form
# values you need and then add those values as GET parameters.

#####
#
# PROGRAMMING
#      Make a backup before altering anything below here.
#      You know... just in case.
#
#####

TMP=${TEMPORARY_FILE_LOCATION}
CURL=${CURL_EXECUTABLE_LOCATION}
GSA=${GSA_WEB_IP_ADDRESS}
USER=${GSA_ADMIN_LOGIN}
PASS=${GSA_ADMIN_PASSWORD}
ADMIN_URL=${GSA_ADMIN_SUBMIT_PAGE}

if [ "X${USE_HTTPS}" = "XN" ] ; then
  PROTOCOL="http"
  PORT=8000
else
  PROTOCOL="https"
  PORT=8443
fi

ME=`basename ${0}`
TMPFILE=${TMP}/${ME}.${$}

LOGIN_URL="${PROTOCOL}://${GSA}:${PORT}/EnterpriseController"

${CURL} -b ${TMPFILE} -c ${TMPFILE} -s ${LOGIN_URL} > /dev/null

${CURL} -b ${TMPFILE} -c ${TMPFILE} -s -d actionType=authenticateUser -d userName=${USER} -d password=${PASS} ${LOGIN_URL} > /dev/null

${CURL} -b ${TMPFILE} -c ${TMPFILE} -s "${PROTOCOL}://${GSA}:${PORT}${ADMIN_URL}" > /dev/null

rm ${TMPFILE}
