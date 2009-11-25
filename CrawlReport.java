/**
 * Copyright (C) 2009 Google Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 *
 * Name: CrawlReport.java
 *
 * Description: Command line application to count the number of urls crawled
 * during the last 24h.
 *
 * The class uses the Google Admin API for java. This requires the appliance to
 * be at least of software version 6.0. It will pull the information from Crawl
 * Diagnostics and provide an overall value of files recrawled as well as a
 * detailed list for each host.
 *
 * Please note that this class needs the following GData libraries:
 * - gdata-core-1.0.jar
 * - gdata-client-meta-1.0.jar
 * - gdata-client-1.0.jar
 * - gdata-gsa-meta-1.0.jar
 * - gdata-gsa-1.0.jar
 *
 * The libraries can be downloaded from:
 * http://code.google.com/p/google-enterprise-gdata-api/
 * 
 * To run the program use the following two commands:
 * 1) compile
 *   export LIBS="gdata-client-1.0.jar:gdata-client-meta-1.0.jar:gdata-core-1.0.jar:gdata-gsa-1.0.jar:gdata-gsa-meta-1.0.jar"
 *   javac -cp "$LIBS" CrawlReport.java
 *
 * 2) execute
 *   java -cp "$LIBS:./" CrawlReport --protocol=http --username=admin \
 *     --port=8000 --hostname=gsa.corp.com --password=secret
 *
 * Please note that the parameter settings are just examples. You will have to
 * replace them with your local appliance values.
 */
import com.google.enterprise.apis.client.GsaClient;
import com.google.enterprise.apis.client.GsaEntry;
import com.google.enterprise.apis.client.GsaFeed;
import com.google.gdata.util.AuthenticationException;
import com.google.gdata.util.ServiceException;

import java.io.IOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Command line application to count the number of urls crawled during the last
 * 24h.
 *
 * The class uses the Google Admin API for java. This requires the appliance to
 * be at least of software version 6.0.
 *
 * Usage Example: java CrawlReport --protocol http --hostname=gsa1 \
 * --port=8000 --username=admin --password=secret
 *
 */
public class CrawlReport {
  /** the gdata client for the admin api. */
  private static GsaClient myClient;
  /** the map of hosts we counted. */
  private static Map<String, Integer> hostmap = new HashMap<String, Integer>();
  /** the map of parsed
   *  command line options. */
  private static Map<String, String> optionMap = new HashMap<String, String>();
  /** the unparsed map of command line options. */
  private static List<String> argsList = new ArrayList<String>();
  /** set of expected options. */
  private static final String[] BASIC_OPTIONS =
      {"protocol", "hostname", "port", "username", "password"};
  /** number of required parameters. */
  private static final int REQUIRED_ARGS_NUM = 5;
  /** milliseconds of 24h. */
  private static final long ONE_DAY_IN_MSEC = (24L * 3600L * 1000L);

  /**
   * unused constructor since we use only static methods, called from main.
   */
  private CrawlReport() {
    // unused -> empty.
  }

  /**
   * The main entry point of the program.
   *
   * We enforce and parse command line args. Afterwards we establish the
   * connection to the appliance and count docs in crawl diagnostics.
   *
   * @param args Command line parameters
   */
  public static void main(final String[] args) {
    if (args.length < REQUIRED_ARGS_NUM) {
      usage();
      return;
    }
    parseArgs(args);
    try {
      establishConnection();
      System.out.println("Documents crawled during the last 24h: "
          + countDocsCrawledSinceYesterday());
      System.out.println("\nDocuments crawled during the last 24h per host:");
      Iterator<String> hostIterator = hostmap.keySet().iterator();
      while (hostIterator.hasNext()) {
        String host = hostIterator.next();
        System.out.println(host + ": " + hostmap.get(host));
      }
    } catch (AuthenticationException e) {
      System.err.println(e.getMessage());
      e.printStackTrace();
    } catch (MalformedURLException e) {
      System.err.println(e.getMessage());
      e.printStackTrace();
    } catch (ServiceException e) {
      System.err.println(e.getMessage());
      e.printStackTrace();
    } catch (IOException e) {
      System.err.println(e.getMessage());
      e.printStackTrace();
    }
  }

  /**
   * tries to log into the Admin Console of the appliance.
   *
   * @throws AuthenticationException in case of password problem
   */
  private static void establishConnection() throws AuthenticationException {
    if (myClient == null) {
      myClient =
          new GsaClient(optionMap.get("protocol"), optionMap.get("hostname"),
              Integer.parseInt(optionMap.get("port")),
              optionMap.get("username"), optionMap.get("password"));
    }
  }

  /**
   * count the docs crawled during the last 24h.
   *
   * @return the number as a long.
   * @throws IOException in case of IO problems during the API communication
   * @throws ServiceException in case of errors during the service calls
   */
  private static long countDocsCrawledSinceYesterday()
    throws ServiceException, IOException {
    // local vars:
    Map<String, String> queries = new HashMap<String, String>();
    Date nowMinus24h = new Date();
    long docCounter = 0;
    // connect to GSA Admin Console
    if (myClient == null) {
      establishConnection();
    }
    // initialize our time filter with the filter: now - 24h
    nowMinus24h.setTime(new Date().getTime() - ONE_DAY_IN_MSEC);
    // prepare our query to the admin api
    int currentPage = 0;
    int maxPages = 1; // we assume the worst case;
    queries.put("sort", "host");
    queries.put("flatList", "true");
    /* queries.put("view","1"); // url status: 1 = crawled from remote host */
    do {
      currentPage++;
      queries.put("pageNum", "" + currentPage);
      // issue the query and iterate over the results
      GsaFeed myFeed = myClient.queryFeed("diagnostics", queries);
      for (GsaEntry entry : myFeed.getEntries()) {
        // we are not interested in the overview
        if (entry.getGsaContent("entryID").equals("description")) {
          // update the num of pages:
          maxPages = Integer.valueOf(entry.getGsaContent("numPages"));
        } else if (entry.getGsaContent("type").equals("FileContentData")) {
          Timestamp urlLastCrawlDate =  new Timestamp(
              Long.valueOf(entry.getGsaContent("timeStamp")) * 1000L);
          if (urlLastCrawlDate.after(nowMinus24h)) {
            // if we want to filter state state of the docs, we can use
            // entry.getGsaContent("docState")
            // the url is in entry.getGsaContent("entryID");
            URL u = new URL(entry.getGsaContent("entryID"));
            if (hostmap.get(u.getHost()) == null) {
              hostmap.put(u.getHost(), 1);
            } else {
              hostmap.put(u.getHost(), hostmap.get(u.getHost()) + 1);
            }
            docCounter++;
          }
        }
      }
    } while (currentPage < maxPages);
    return docCounter;
  }

  /**
   * Parses the arguments from String array.
   *
   * Any argument should begin with '--' except the {@code command}, {@code
   * feedName} and {@code entryName}. The {@code command} should be put in the
   * first position of the command line arguments.
   *
   * @param args Arguments array
   * @throws IllegalArgumentException in case of a non valid command line arg.
   */
  private static void parseArgs(final String[] args)
    throws IllegalArgumentException {
    // parse arguments
    for (String arg : args) {
      if (arg.startsWith("--")) {
        parseOption(arg.substring(2));
      } else {
        argsList.add(arg);
      }
    }
    validateBasicOption();
  }

  /**
   * Parses key and value pair from a string {@code argString}.
   *
   * The key-value pair will be restored in {@code optionMap}.
   *
   * @param argString the argument String
   */
  private static void parseOption(final String argString) {
    int index = argString.indexOf('=');

    if (index == -1) {
      optionMap.put(argString, null);
    } else {
      optionMap.put(argString.substring(0, index),
          argString.substring(index + 1));
    }
  }

  /**
   * Validates options for creating {@code GsaClient}.
   *
   * @throws IllegalArgumentException
   */
  private static void validateBasicOption() throws IllegalArgumentException {
    for (String option : BASIC_OPTIONS) {
      if (optionMap.get(option) == null) {
        throw new IllegalArgumentException("Please specify --" + option);
      }
    }
  }

  /**
   * Usage Description for the binary.
   */
  private static void usage() {
    System.err.println("Usage: CrawlReport <options> ");
    System.err.println("options:\n  --protocol:\n  --hostname:\n  --port:\n"
        + "  --username:\n  --password:\n  ");
    System.err.println("Example:\n  CrawlReport --protocol=http "
        + "--hostname=gsa1 --port=8000 --username=user --password=password  ");
  }
}
