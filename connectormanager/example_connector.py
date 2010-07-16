#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.

import connectormanager

class ExampleConnector(connectormanager.Connector):
  CONNECTOR_TYPE = 'example-connector'
  CONNECTOR_CONFIG = {
      'example_field': { 'type': 'text', 'label': 'Example field' }
  }

  def startConnector(self):
    pass

  def stopConnector(self):
    pass

  def restartConnectorTraversal(self):
    pass
