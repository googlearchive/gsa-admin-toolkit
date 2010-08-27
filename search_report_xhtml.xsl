<?xml version="1.0" encoding="ISO-8859-1"?>

<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="xml" indent="yes" 
    doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"
    doctype-public="-//W3C//DTD XHTML 1.0 Transitional//EN" />
<!--

 Copyright 2009 Google Inc. All Rights Reserved.

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.

 This code is not supported by Google

 ****************************************************************************

 This XSLT stylesheet is intended to convert XML output from Search Reports
 from GSA into human-readable XHTML 1.0 document. You can use any XSTL
 processor/software. We recommend using 'xsltproc' command line tool:

 $ xsltproc search_report_xhtml.xsl report_search_report_1.xml > output.html

-->

<!-- sort of hashmaps for grouping search report data -->
<xsl:key name="months" match="daily" use="substring(@date,0,8)"/>
<xsl:key name="counts" match="daily" use="@date"/>
<xsl:key name="hourcounts" match="hourlyAvg" use="@hour"/>

<!--

 HELPER FUNCTIONS

-->

<!-- for loop in XSL, adapted for search reports -->
<xsl:template name="for.loop">
  <xsl:param name="i" />
  <xsl:param name="count" />
  <xsl:param name="mode" select="'iterate'" />

  <xsl:if test="$i &lt;= $count">
    <td>
    <xsl:if test="$i &lt;= $count">

      <xsl:choose>
        <xsl:when test="$mode='hour'">
          <xsl:value-of select="key('hourcounts', $i)" />
        </xsl:when>
        <xsl:when test="$mode='iterate'">
          <xsl:value-of select="$i" />
        </xsl:when>
        <xsl:otherwise>
          <xsl:choose>
            <xsl:when test="$i &lt; 10">
              <xsl:value-of select="key('counts', concat($mode,'-0',$i))" />
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="key('counts', concat($mode,'-',$i))" />
            </xsl:otherwise>
          </xsl:choose>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    </td>
  </xsl:if>

  <xsl:if test="$i &lt;= $count">
    <xsl:call-template name="for.loop">
      <xsl:with-param name="i" select="$i + 1" />
      <xsl:with-param name="count" select="$count" />
      <xsl:with-param name="mode" select="$mode" />
    </xsl:call-template>
  </xsl:if>
</xsl:template>

<!-- returns the name of the month -->
<xsl:template name="format.month">
  <xsl:param name="mo" />
  <xsl:choose>
    <xsl:when test="$mo = '01'"><xsl:value-of select="'January'"/></xsl:when>
    <xsl:when test="$mo = '02'"><xsl:value-of select="'February'"/></xsl:when>
    <xsl:when test="$mo = '03'"><xsl:value-of select="'March'"/></xsl:when>
    <xsl:when test="$mo = '04'"><xsl:value-of select="'April'"/></xsl:when>
    <xsl:when test="$mo = '05'"><xsl:value-of select="'May'"/></xsl:when>
    <xsl:when test="$mo = '06'"><xsl:value-of select="'June'"/></xsl:when>
    <xsl:when test="$mo = '07'"><xsl:value-of select="'July'"/></xsl:when>
    <xsl:when test="$mo = '08'"><xsl:value-of select="'August'"/></xsl:when>
    <xsl:when test="$mo = '09'"><xsl:value-of select="'September'"/></xsl:when>
    <xsl:when test="$mo = '10'"><xsl:value-of select="'October'"/></xsl:when>
    <xsl:when test="$mo = '11'"><xsl:value-of select="'November'"/></xsl:when>
    <xsl:when test="$mo = '12'"><xsl:value-of select="'December'"/></xsl:when>
  </xsl:choose>
</xsl:template>

<!--

 MAIN PROCESSING MEAT

-->
<xsl:template match="/">

<xsl:variable name="top" select="summaryReport/reportParams/@topCount" />

  <html>
  <body>

  <h1>Search report - <xsl:value-of select="summaryReport/reportParams/@reportName"/></h1>

  <p>Report created on <b><xsl:value-of select="summaryReport/reportParams/@creationDate"/></b>. This report includes the following timeframe: <b><xsl:value-of select="summaryReport/reportParams/@reportDateRange"/></b>. Showing <b><xsl:value-of select="$top"/></b> top entries.</p>

  <table border="1">
    <tr>
      <th>Total result pages</th>
      <td><xsl:value-of select="summaryReport/resultPages"/></td>
    </tr>
    <tr>
      <th>Total searches</th>
      <td><xsl:value-of select="summaryReport/totalQueries"/></td>
    </tr>
    <tr>
      <th>Distinct searches</th>
      <td><xsl:value-of select="summaryReport/distinctQueries"/></td>
    </tr>
    <tr>
      <th>ASR entries</th>
      <td><xsl:value-of select="summaryReport/asrEntries"/></td>
    </tr>
  </table>

  <br />

  <table border="1">
    <tr>
      <th>Excluded terms</th>
    </tr>
    <xsl:for-each select="summaryReport/reportParams/excludedTerm">
    <tr>
      <td><xsl:value-of select="."/></td>
    </tr>
    </xsl:for-each>
  </table>

  <h2>Searches per day</h2>
  <table border="1">
  <!-- loop through months -->
  <xsl:for-each select="//daily[generate-id(.)=generate-id(key('months', substring(@date,0,8))[1])]">
    <xsl:sort select="substring(@date,0,8)"/>
    <!-- loop through days of months -->
    <xsl:for-each select="key('months', substring(@date,0,8))">
      <xsl:if test="position() = 1">
        <tr><th colspan="32">
          <xsl:call-template name="format.month">
            <xsl:with-param name="mo" select="substring(@date,6,2)" />
          </xsl:call-template>
          <xsl:text> </xsl:text>
          <xsl:value-of select="substring(@date,0,5)"/>
        </th></tr>
        <tr><th>Date</th>
        <xsl:call-template name="for.loop">
          <xsl:with-param name="i" select="'1'" />
          <xsl:with-param name="count" select="'31'" />
        </xsl:call-template>
        </tr>
      </xsl:if>
    </xsl:for-each>
    <!-- need another loop to create value columns -->
    <tr><th>Count</th>
    <xsl:call-template name="for.loop">
      <xsl:with-param name="i" select="'1'" />
      <xsl:with-param name="count" select="'31'" />
      <xsl:with-param name="mode" select="substring(@date,0,8)" />
    </xsl:call-template>
    </tr>
    <!--<xsl:value-of select="@date"/>-->
  </xsl:for-each>
  </table>

  <h2>Average searches per hour</h2>
  <table border="1">
    <tr>
      <th>Hour</th>
      <xsl:call-template name="for.loop">
        <xsl:with-param name="i" select="'0'" />
        <xsl:with-param name="count" select="'23'" />
      </xsl:call-template>
    </tr>
    <tr>
      <th>Count</th>
      <xsl:call-template name="for.loop">
        <xsl:with-param name="i" select="'0'" />
        <xsl:with-param name="count" select="'23'" />
        <xsl:with-param name="mode" select="'hour'" />
      </xsl:call-template>
    </tr>
  </table>

  <h2>Top <xsl:value-of select="$top"/> Keywords</h2>
  <table border="1">
    <tr>
      <th>Term</th>
      <th>Occurrence</th>
    </tr>
    <xsl:for-each select="summaryReport/topKeywords/topKeyword">
    <tr>
      <td><xsl:value-of select="@keyword"/></td>
      <td><xsl:value-of select="."/></td>
    </tr>
    </xsl:for-each>
  </table>

  <h2>Top <xsl:value-of select="$top"/> Queries</h2>
  <table border="1">
    <tr>
      <th>Query</th>
      <th>Occurrence</th>
    </tr>
    <xsl:for-each select="summaryReport/topQueries/topQuery">
    <tr>
      <td><xsl:value-of select="@query"/></td>
      <td><xsl:value-of select="."/></td>
    </tr>
    </xsl:for-each>
  </table>

  <h2>ASR IPs</h2>
  <table border="1">
    <tr>
      <th>IP</th>
      <th>Occurrence</th>
    </tr>
    <xsl:for-each select="summaryReport/asrIp/asrIp">
    <tr>
      <td><xsl:value-of select="@ip"/></td>
      <td><xsl:value-of select="."/></td>
    </tr>
    </xsl:for-each>
  </table>

  <h2>ASR URLs</h2>
  <table border="1">
    <tr>
      <th>URL</th>
      <th>Occurrence</th>
    </tr>
    <xsl:for-each select="summaryReport/asrUrl/asrUrl">
    <tr>
      <td><xsl:value-of select="@url"/></td>
      <td><xsl:value-of select="."/></td>
    </tr>
    </xsl:for-each>
  </table>

  </body>
  </html>
</xsl:template>

</xsl:stylesheet>
