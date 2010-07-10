#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.

import connectormanager

class ExampleConnector(connectormanager.Connector):
  @staticmethod
  def getConnectorType():
    return 'example-connector'

  def getStatus(self):
    return '0'

  def startConnector(self):
    pass

  def stopConnector(self):
    pass

  def restartConnectorTraversal(self):
    pass

  @staticmethod
  def getConfigForm():
    config_form = ('<CmResponse>'
                   '<StatusId>0</StatusId>'
                   '<ConfigureResponse>'
                   '<FormSnippet>'
                   '<![CDATA[Example: <input type="text" name="example"]]>'
                   '</FormSnippet>'
                   '</ConfigureResponse>'
                   '</CmResponse>')
    return config_form

  def getForm(self):
    ex = self.getConfigParam('example')
    return '<![CDATA[<input type="text" name="example" value="%s"]]>' % ex
