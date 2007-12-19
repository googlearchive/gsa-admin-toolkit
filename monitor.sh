#!/bin/sh
#
# Copyright (C) 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Name
#   monitor.sh
#
# Description:
#   Shell script for monitoring the appliance.
#
# Usage:
#   Run every minute from cron. For example:
#     * * * * * /root/monitor.sh search.google.com google >> /tmp/monitor.out
#   The first argument is the hostname of the appliance.
#   The second argument is a word that appears in a lot of documents,
#   such as your domain name.
#
# Sample output:
#   Wed Aug 1 16:25:20 PDT 2007  HTTP status: 200 Connect time: 0.023 \
#   Total time: 1.382 Size: 5537 Query: google+OR+23062 \
#   Estimated results: 6530 Curl exit status: 0
#
# Detailed description:
#  * Query strings are unique so that Google support can more easily
#    trace a query to the backend processes
#  * Each monitoring query contains a common string parameter so that 
#    customers can easily remove them from their logs when doing reports.
#  * The time on the monitor machine must be sync'd to the appliance
#    so that the timestamp from the monitor script matches the timestamp
#    in the appliance query logs.
#  * The exit status from curl shows the exact failure mode of the script.
#    See the curl man page for details.
#  * Run a query that doesn't use significant resources on the appliance,
#    such as large value for num or a date sort of all documents.
# 
#

appliance=""
domain=""
debug=0

while getopts h:q:d o; do
  case "$o" in
    h)     appliance="$OPTARG";;
    q)     domain="$OPTARG";;
    d)     debug=1;;
  esac
done

if test -z $appliance -o -z $domain; then
  echo "Usage: $0 -h appliance_hostname -q query_term"
  exit 1
fi

results_file=/tmp/curl.results.$$
status_file=/tmp/curl.status.$$
timeout="--connect-timeout 10 --max-time 60"
datestr=`date +%s`
query="${domain}+OR+${datestr}${RANDOM}"
timingstring="Connect time: %{time_connect} Total time: %{time_total}"
outstring="HTTP status: %{http_code} ${timingstring} Size: %{size_download} Query: ${query}"
params="client=default_frontend&site=default_collection&output=xml"
url="http://${appliance}/search?q=${query}&${params}&monitoring=1"

echo -n `date` " "
curl_command="curl -s --output ${results_file} -w \"${outstring}\" ${timeout} \"${url}\""
curl -s --output ${results_file} -w "${outstring}" ${timeout} "${url}" > ${status_file}
retval=$?
status=`cat ${status_file}`
echo -n ${status}
http_status=`echo ${status} | cut -d " " -f 3`
results=`cat ${results_file} | grep "<M>" | sed 's/.*<M>\(.*\)<\/M>.*/\1/;' | sed 's/ //g'`
echo -n " Estimated results: ${results} "
echo -n "Curl exit status: ${retval} "

final_status="Success"
if test ${retval} -ne 0; then
  final_status="Failed: curl error"
fi
if test -z ${results}; then
  final_status="Failed: no results"
fi
if test ${http_status} != "200"; then
  final_status="Failed: HTTP error"
fi

echo ${final_status}

if test ${debug} -eq 1; then
  echo ${curl_command}
  cat ${results_file}
fi

rm ${results_file}
rm ${status_file}
