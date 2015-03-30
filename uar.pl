#!/usr/bin/perl -w
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
# This code is not supported by Google
#
# uar.pl - Command line tool to manage GSA User Added Results (UAR)
#
#   Configuration Notes:
#   - REQUEST urls may need to be customized, as well as the ULF flow
#   - You will need to create the security_token frontend 
#     (See security_token.xslt)

use strict;
use Getopt::Long;
use HTTP::Cookies;
use LWP;
use Pod::Usage;
use URI::Encode qw(uri_encode);
use XML::XPath;

my $GSA_HOST = "";  # If you want to hardcode the gsa hostname
my $GSA_FRONTEND = "default_frontend";
my $HTTP = "https://";
my $TOKEN_REQUEST =  "/search?q=test&access=a&proxystylesheet=security_token";
my $SEARCH_REQUEST = "/search?access=a&num=1";
my $ULF_REQUEST = "/security-manager/samlauthn";
my $UAR_REQUEST = "/uar";
my $USER = "ericl";
my $PASSWORD = "test";
my $security_token = "";

my $help = 0;
my $verbose = 0;
my $action = "";
my $query = "";
my $uar_name = "";
my $uar_title = "";
my $uar_url = "";
my $uar_rid;

GetOptions ("action=s" => \$action,
            "query=s" => \$query,
            "name=s" => \$uar_name,
            "title=s" => \$uar_title,
            "url=s" => \$uar_url,
            "rid=i" => \$uar_rid,
            "host=s" => \$GSA_HOST,
            "frontend=s" => \$GSA_FRONTEND,
            "verbose|v" => \$verbose,
            "help|?" => \$help)
  or usage("Error in command line arguments");

# Check command line args
if ($help) {
  usage("");
}

if ($GSA_HOST eq "") {
  usage("gsa hostname or IP must be specified with --host");
}

if ($action eq "") {
  usage("action must be specified");
}

if ($uar_name ne "") {
  if ($uar_name !~ /^[a-z][a-z_0-9-]{0,31}$/i) {
    usage("invalid UAR name specified");
  }
}

if ($query ne "") {
  if ($query =~ /([\&\?])/) {
    usage("Invalid character in query: '$1'");
  }
}

if ($action eq "add") {
  if ($query eq "" || $uar_name eq "" || $uar_title eq "" or $uar_url eq "") {
    usage("query, name, tile and url must be specified");
  }
}

if ($action eq "edit") {
  if ($uar_name eq "" || $uar_title eq "" || $uar_url eq "") {
    usage("name, title and url must be specified");
  }
}

if ($action eq "delete") {
  if (($query eq "" && $uar_rid eq "") || $uar_name eq "") {
    usage("query|rid & name must be specified");
  }
}

# Setup "browser" client
my $browser = LWP::UserAgent->new(
  ssl_opts => { SSL_verify_mode => 'SSL_VERIFY_NONE'},
  requests_redirectable => [ 'GET', 'HEAD', 'POST' ]
  );
$browser->ssl_opts(verify_hostname => 0);
$browser->cookie_jar(HTTP::Cookies->new(file => "$ENV{HOME}/.cookies.txt"));
if ($verbose) {
  $browser->add_handler("request_send",  \&dump_ua);
  $browser->add_handler("response_done", \&dump_ua);
}

# Login to GSA, get a security token
# May need to modify depending on your authN config
my $response = $browser->get($HTTP . $GSA_HOST . $TOKEN_REQUEST);
$response = submit_ulf();
$security_token = $response->content;

if ($action eq "list") {
  list_all_uar($query,$uar_name);
} elsif ($action eq "add") {
  add_uar($query,$uar_name,$uar_title,$uar_url);
} elsif ($action eq "delete" && $uar_rid ne "") {
  delete_single_uar($uar_rid, $uar_name);
} elsif ($action eq "delete" && $query ne "") {
  delete_all_uar($query,$uar_name);
} elsif ($action eq "edit") {
  edit_uar($query,$uar_name,$uar_rid,$uar_title,$uar_url);
} else {
  usage("action of list|add|delete|edit must be specified");
}

exit();

# Return XML list of UAR entries for a specific query
sub get_uar {
  my $query = shift;

  my $response = $browser->get($HTTP . $GSA_HOST . $SEARCH_REQUEST . 
                               "&client=" . $GSA_FRONTEND . "&q=" . $query);

  if (!$response->is_success || $response->code != 200) {
    die("Error getting response from GSA - check request parameters");
  }

  my $body = $response->content();
  my $p = XML::Parser->new(NoLWP => 1);
  my $xp = XML::XPath->new(parser => $p, xml => $body);
  my $ob = $xp->find('/GSP/ENTOBRESULTS/OBRES/MODULE_RESULT');

  return $ob;
}

# List all UAR's for a specific query                                         
sub list_all_uar {
  my $query = shift;

  my $uar_list = get_uar($query);

  foreach my $node ($uar_list->get_nodelist) {
    my $title = $node->find('Field[@name="title"]')->string_value;
    my $url = $node->find('Field[@name="url"]')->string_value;
    my $rid = $node->find('Field[@name="rid"]')->string_value;
    my $addedBy = $node->find('Field[@name="addedby"]')->string_value;

    if ($rid ne "new") {
      print "$rid\n$title\n$url\n\n";
    }
  }
  return;
}

# Delete all UAR's for a specific query
sub delete_all_uar {
  my $query = shift;
  my $uar_name = shift;

  my $uar_list = get_uar($query);

  foreach my $node ($uar_list->get_nodelist) {
    my $rid = $node->find('Field[@name="rid"]')->string_value;

    if ($rid ne "new") {
      delete_single_uar($rid, $uar_name);
    }
  }
  return;
}

# Delete a single UAR based on rid
sub delete_single_uar {
  my $rid = shift;
  my $uar_name = shift;

  my $response =
    $browser->post($HTTP . $GSA_HOST . $UAR_REQUEST,
                   {
                     'action' => "DELETE",
                     'rid' => $rid,
                     'oneboxName' => $uar_name,
                     'token' => $security_token
                   });
  print $response->code. " - ". $response->content . "\n";
  return;
}

# Add a new UAR
sub add_uar {
  my $query = shift;
  my $uar_name = shift;
  my $uar_title = shift;
  my $uar_url = shift;

  # Submit UAR Add
  $response =
    $browser->post($HTTP . $GSA_HOST . $UAR_REQUEST,
                   {'action' => "ADD",
                    'url' => uri_encode($uar_url),
                    'oneboxName' => $uar_name,
                    'title' => $uar_title,
                    'query' => $query,
                    'token' => $security_token
                   });

  print $response->code. " - ". $response->content . "\n";
}

# Edit existing UAR based on rid
sub edit_uar {
  my $query = shift;
  my $uar_name = shift;
  my $rid = shift;
  my $uar_title = shift;
  my $uar_url = shift;

  # Submit UAR Edit
  my $response = 
    $browser->post($HTTP . $GSA_HOST . $UAR_REQUEST,
                   {
                     'action' => "EDIT",
                     'rid' => $rid,
                     'url' => uri_encode($uar_url),
                     'oneboxName' => $uar_name,
                     'title' => $uar_title,
                     'query' => $query,
                     'token' => $security_token
                   });

  print $response->code . " - " . $response->content . "\n";
  return;
}

# Submit the ULF
sub submit_ulf {
  my $response =
    $browser->post($HTTP . $GSA_HOST . $ULF_REQUEST,
                   { 
                     'uDefault' => $USER,
                     'pwDefault' => $PASSWORD
                   });

  if (!$response->is_success || $response->code != 200) {
    die "Error submitting credentials: " . $response->message;
  }

  return($response);
}

# print HTTP request/response when --verbose
sub dump_ua {
  my $ua = shift;
  $ua->dump;

  return;
}

# usage info
sub usage {
  my $message = shift;

  my $command = $0;
  $command =~ s/^.*[\/\\]//; # Remove path

  print STDERR (
    "Usage: $command --action <add|edit|list|delete> --query <query>\n" .
    "         --name <uar_config_name>\n" .
    "         --title <uar_title> --url <uar_url> --rid <uar_id>\n" .
    "         --host <gsa host>  --frontend <gsa frontend>\n" .
    "         --verbose|-v --help|-?\n\n"
    );

  print STDERR (
    "Examples\n" .
    "  List all UARs for a specific query:\n" .
    "    $command --action list --query foo\n\n" .
    "  Add new UAR:\n" .
    "    $command --action add --query foo --name myuar " .
    "--title=\"Example Title\" --url=http://www.example.com\n\n" .
    "  Edit existing UAR:\n" .
    "    $command --action edit --name myuar --rid 123456789 " .
    "--title=\"Example Title\" --url=http://www.example.com\n\n" .
    "  Delete single UAR entry:\n" .
    "    $command --action delete --rid 123456789 --name myuar\n\n" .
    "  Delete all UAR for a query:\n" .
    "    $command --action delete --query foo --name myuar\n\n"
    );
  
  if ($message ne "") {
    print STDERR ("\nERROR: " . $message . "\n\n");
  }
  exit();
}
