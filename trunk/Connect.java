/*
 * Copyright (C) 2007 Google Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Name:
 *
 *   Connect.java
 *
 * Description:
 *
 *   Class for testing the JDBC connection to the database.
 *
 *   This class can be configured to use the same database drivers as the
 *   appliance so that you can test connections to your database before
 *   configuring a database crawl from the appliance. You must use the same
 *   database drivers that the appliance uses. See the documentation on
 *   http://support.google.com/enterprise/ for details of the specific
 *   JDBC driver versions supported.
 *
 *   You should run the program from a different machine to the database
 *   machine to ensure that you are checking network connections to the DB.
 *
 * Usage:
 *
 *   1. Compile:
 *
 *       javac Connect.java
 *
 *   2. Run the program with the following parameters:
 *
 *       1. Class name of driver
 *       2. Database URL
 *       3. Username
 *       4. Password
 *       5. SQL query
 *
 *      Ensure that you have the driver in your classpath
 *
 *       java -classpath <path-to-db-class> Connect <driver> <database-url> <username> <password> <sql-query>
 *
 * Below are some notes on the drivers that are used by the appliance. It is best to 
 * test the connection using the same driver version that the appliance uses.
 *
 * MySQL
 *  Driver class file:         mysql-3.0.14.jar
 *  Driver class name:         com.mysql.jdbc.Driver
 *  Database URL:              jdbc:mysql://<hostname>/<db-name>
 *
 * DB2
 *  Driver version:            IBM DB2 JDBC driver 8.1.0.64 (Type-3 pure Java)
 *  Driver class file:         db2java.jar
 *  Driver class name:         COM.ibm.db2.jdbc.net.DB2Driver
 *  Database URL:              jdbc:db2://<hostname>:<port>/<db-name>
 *
 * Postgres
 *  Driver version:            PostgreSQL 7.1.3 (Type-4 pure Java)
 *  Driver class file:         pgjdbc2.jar
 *
 * Oracle
 *  Driver version:            Oracle JDBC Driver version - 10.1.0.2.0 (Type-4 pure Java)
 *
 */

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;

public class Connect {
  public static void main(String[] args) {
    System.out.println("Connection/SQL test starting in Connect.java...");
    String driver = args[0];
    String url = args[1];
    String userid = args[2];
    String password = args[3];
    String query = args[4];

    Connection connection = null;
    try {
      Class.forName(driver);
    } catch (Exception e) {
      System.out.println("Error loading driver");
      e.printStackTrace();
      return;
    }
    try {
      connection = DriverManager.getConnection(url, userid, password);
      System.out.println("Connection successful!");
      Statement statement =
          connection.createStatement(ResultSet.TYPE_SCROLL_SENSITIVE, ResultSet.CONCUR_READ_ONLY);
      ResultSet rs = statement.executeQuery(query);
      if (rs != null) {
        ResultSetMetaData rsMetaData = rs.getMetaData();
        int numberOfColumns = rsMetaData.getColumnCount();
        boolean b = rs.first();
        int counter = 1;
        while(b) {
          for (int i = 1; i < numberOfColumns + 1; i++) {
            String tableName = rsMetaData.getTableName(i);
            String columnName = rsMetaData.getColumnName(i);
            String output = rs.getString(columnName);
            if(i == 1 && counter == 1) {
              System.out.println("Using Table: " + tableName);
            }
            System.out.print("Row: " + counter + " column name=" + columnName);
            System.out.println(" Column_output=" + output);
          }
          counter++;
          b = rs.next();
        }
      }
      else {
        System.out.println("Query returned no results!");
      }
    } catch (SQLException e) {
      System.out.println("Caught SQLException: " + e.getMessage());
      e.printStackTrace();
    } finally {
      try {
        connection.close();
      } catch (SQLException e) {
        e.printStackTrace();
      }
    }
    System.out.println("Program ended correctly!");
  }
}
