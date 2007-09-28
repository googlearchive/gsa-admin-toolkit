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
#   adminconsole-cookie.sh
#
# Description:
#   Shell script that gets a cookie for accessing the Admin Console.
#   This script doesn't do any error checking.
#
# Usage:
#   adminconsole-cookie.sh <appliance-hostname> <username> <password>
#
# Detailed description:
#
#   You can use the cookie that you get from this script in a curl 
#   command to run an operation on the Admin Console. For example,
#   you can delete a collection with:
#
#     curl -s -i -b ${cookie} -o $o "${url}?actionType=deleteCollection&rm_collection=${coll}"
#
#   You can create a frontend with:
#
#     a="frontend=${frontend}&createFrontend=+Create+New+Front+End+&actionType=createFrontend" 
#     curl -s -i -b ${cookie} -o $o -d $a ${url}
#

hostname=$1
username=$2
password=$3

port=8000

c=/tmp/c.$$
o=/dev/null
url="http://${hostname}:${port}/EnterpriseController"

# First login
curl -s -i -c $c -o $o $url

a="actionType=authenticateUser&userName=${username}&password=${password}" 
curl -s -i -b $c -o $o -d $a $url 

cat $c | grep -v "^#" | grep -v "^$" | awk '{ print $6 "=" $7 }'
rm $c


