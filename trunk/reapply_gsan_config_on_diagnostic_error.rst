

This scripts logs in to the GSA administration interface, reads the
GSA^n diagnostics page (Google Search Appliance > GSA^n > Network
Diagnostics) at url
http://gsa.wwf.org:8000/EnterpriseController?actionType=gsanDiagnostics.

If the diagnostic page shows errors, then 'Apply Configuration' on
page Google Search Appliance >GSA^n >Configuration at url
http://gsa.wwf.org:8000/EnterpriseController?actionType=gsanConfig.

This script accepts fives options, plus the *-h, --help* and *-v,
--verbose* option, as shown on the help::

    ~$ python reapply_gsan_config_on_diagnostic_error.py -h
    Usage: reapply_gsan_config_on_diagnostic_error.py [options]
    
    Options:
      -h, --help            show this help message and exit
      -n HOSTNAME, --hostname=HOSTNAME
                            GSA hostname
      --port=PORT           Upload port. Defaults to 8000
      -u USERNAME, --username=USERNAME
                            Username to login GSA
      -p PASSWORD, --password=PASSWORD
                            Password for GSA user
      -v, --verbose         

And can be used like this::

    ~$ python reapply_gsan_config_on_diagnostic_error.py -n gsa.wwwf.org
    No need to re-apply the configuration  

When the a problem shows up on the diagnostic page, the script shows
these messages::

    ~$ python reapply_gsan_config_on_diagnostic_error.py -n gsa.wwwf.org
    Re-applying the configuration
    Diagnostic still in error. Check in a few minutes

The script shows the mentionned message in the default log level (no
*-v*). The verbose option has two more levels:

- *-v*: shows the url to which the script sends request::
 
     ~$ python reapply_gsan_config_on_diagnostic_error.py -n entzm02.hot -v
     Sending to this url:http://entzm02.hot:8000/EnterpriseController
     Sending to this url:http://entzm02.hot:8000/EnterpriseController
      ... with this body: userName=admin&password=p4ss&actionType=authenticateUser
     Sending to this url:http://entzm02.hot:8000/EnterpriseController?actionType=gsanDiagnostics
     No need to re-apply the configuration
     Sending to this url:http://entzm02.hot:8000/EnterpriseController?actionType=logout
 
- *-v -v*: the full text of the sent HTTP request and received HTTP response

Limitations: it is not cristal clear yet in which case this
re-applying the distributed configuration solves a distributed setup problem.
