GSA Admin Toolkit
=================
The GSA Admin Toolkit is a collection of standalone tools that handle some
common tasks for Google Search Appliance (GSA) administrators.

Prerequisites
-------------
The programs are mostly written in Java, Python, or Bash. Any
required libraries that are non-standard will be documented within the
source code file for the program.

Installation, setup and usage instructions
------------------------------------------
Instructions for compiling (if required) and running each program are
given at the top of the source code file for each program.

This code is not supported by Google.

Downloads
----------------
Ready-to-use downloads are available for the following utilities from [Google Drive](https://drive.google.com/folderview?id=0B7nWgkrzL8DFTWdFZWpCTVo2Y3c&usp=sharing#list).

  * `GSA-GA.zip` -- Google Analytics integration resources.
  * `sht.zip` -- Self Help Tool for integrating GSA with Microsoft SharePoint, Fileshares and Kerberos
  * `gsa_sign.exe` -- .NET executable to re-sign exported configuration. Allows you to export config, edit, and re-import.

Source
------

  1. [monitor.sh](https://github.com/google/gsa-admin-toolkit/blob/master/monitor.sh) -- Monitoring script that verifies serving on the GSA
  1. [load.py](https://github.com/google/gsa-admin-toolkit/blob/master/load.py) -- Runs load tests against the appliance
  1. [authn.py](https://github.com/google/gsa-admin-toolkit/blob/master/authn.py) -- Web server for testing the Authn SPI
  1. [authz.py](https://github.com/google/gsa-admin-toolkit/blob/master/authz.py) -- Web server for testing the Authz SPI
  1. [Connect.java](https://github.com/google/gsa-admin-toolkit/blob/master/Connect.java) -- Java class for testing the JDBC connection to the database
  1. [cached_copy_checker.py](https://github.com/google/gsa-admin-toolkit/blob/master/cached_copy_checker.py) -- Monitoring script that verifies crawling, indexing and serving are working on an appliance
  1. [sso.py](https://github.com/google/gsa-admin-toolkit/blob/master/sso.py) -- Web server for testing Cookie Sites. Can be configured to mimic Oblix.
  1. [searchstats.py](https://github.com/google/gsa-admin-toolkit/blob/master/searchstats.py) -- Search logfile analysis (error rates, queries per second, average response time)
  1. [smbcrawler.py](https://github.com/google/gsa-admin-toolkit/blob/master/smbcrawler.py) -- Script that mimics how the appliance crawls SMB. Useful for troubleshooting SMB crawl problems where the error message on the appliance is unhelpful.
  1. [reverse_proxy.py](https://github.com/google/gsa-admin-toolkit/blob/master/reverse_proxy.py) -- Reverse proxy that can be used to queue requests to the appliance in order to limit the number of concurrent connections. It was written as a proof-of-concept and has not been tested in a production environment.
  1. [gsa_admin.py](https://github.com/google/gsa-admin-toolkit/blob/master/gsa_admin.py) -- Python script for automating Admin Console tasks. Used in cases where the Admin Console GData API won't work (e.g. software version before 6.0, or feature missing in API)
  1. [remove-or-recrawl-urls.html](https://github.com/google/gsa-admin-toolkit/blob/master/remove-or-recrawl-urls.html) -- HTML+JavaScript helper page that builds feeds to remove or re-crawl URLs.
  1. [urlstats.py](https://github.com/google/gsa-admin-toolkit/blob/master/urlstats.py) -- Python script that generates reports about URLs in the GSA.
  1. [ssoproxy.py](https://github.com/google/gsa-admin-toolkit/blob/master/ssoproxy.py)  --  Configurable python script that proxies SSO systems login rules to provide GSA with crawling/serving SSO cookies 
  1. [CrawlReport.java](https://github.com/google/gsa-admin-toolkit/blob/master/CrawlReport.java) -- Java class to retrieve via the new Admin API (software version 6.0.0) the number of urls crawled since yesterday
  1. [connectormanager.py](https://github.com/google/gsa-admin-toolkit/tree/master/connectormanager) -- Simple connectormanager and example connectors with [documentation on how to write a new connector](https://github.com/google/gsa-admin-toolkit/wiki/ConnectorManagerDocumentation)
  1. [Kerberos Validation Tool](https://github.com/google/gsa-admin-toolkit/wiki/GSAKerberosValidation) -- HTML Application to validate Kerberos/IWA setup (keytab/AD, etc)
  1. [interactive-feed-client.html](https://github.com/google/gsa-admin-toolkit/blob/master/interactive-feed-client.html) -- HTML/Javascript page that generates XML feeds from inputs such as the URL and hostname then submits to a GSA.
  1. [search_report_xhtml.xsl](https://github.com/google/gsa-admin-toolkit/blob/master/search_report_xhtml.xsl) -- XSLT stylesheet to transform exported search report XMLs into human-readable XHTML.
  1. [search_results_analyzer.py](https://github.com/google/gsa-admin-toolkit/blob/master/search_results_analyzer.py) -- Tool for analyzing search results and comparing results between two appliances.
  1. [convert_cached_copy_to_feed.py](https://github.com/google/gsa-admin-toolkit/blob/master/convert_cached_copy_to_feed.py) -- Tool for converting cached versions into content feeds for migration purposes.
  1. [fetch_secure.py](https://github.com/google/gsa-admin-toolkit/blob/master/fetch_secure.py) -- Fetch secure search results from GSA by following all Universal Login redirects.
  1. [gsa_sign.cs](https://github.com/google/gsa-admin-toolkit/blob/master/gsa_sign.cs) -- Example in C# how to sign exported configuration 
  1. [license_exceeded.py](https://github.com/google/gsa-admin-toolkit/blob/master/license_exceeded.py) --  Audit the exported URLs for common cause of high license usage, and provide resolution tips.
  1. [SimpleFeedContentGenerator.java](https://github.com/google/gsa-admin-toolkit/blob/master/SimpleFeedContentGenerator.java) --  Simple feed content generator. Useful for performance testing. Generates feed file with simple content and metadata.