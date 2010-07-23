#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This code is not supported by Google
#

"""An abstract connector that runs continually with a specified time interval.

A connector that implements this TimedConnector just needs to override the run()
method. The getInterval and setInterval methods are provided to manipulate the
timer delay (the default is 15 minutes).

If a TimedConnector implementation's interval comes from the configuration form,
then setInterval should be called in an init() method with the appropriate
value from getConfigParam.
"""

__author__ = 'jonathanho@google.com (Jonathan Ho)'

import connectormanager
import threading

class TimedConnector(connectormanager.Connector):
  _interval = 15*60 # 15 minutes
  _timer = None

  def run(self):
    """Runs the connector logic."""
    raise NotImplementedError("run() not implemented")

  def _run(self):
    self.run()
    self._timer = threading.Timer(self._interval, self.startConnector)
    self._timer.start()

  def startConnector(self):
    """Starts the connector by calling the run() method periodically, as
    specified by setInterval."""
    self._timer = threading.Timer(self._interval, self._run)
    self._timer.start()

  def stopConnector(self):
    """Stops the connector by cancelling the timer."""
    if self._timer:
      self._timer.cancel()
      self._timer = None

  def restartConnectorTraversal(self):
    """Restarts the connector by stopping and starting it again.

    Note: this may be completely incorrect, depending on the connector
    implementation. For example, if the connector maintains some sort of
    traversal state after stopConnector(), this would fail to reset that state.
    This method should, of course, be overridden if this is the case.
    """
    self.stopConnector()
    self.startConnector()

  def getInterval(self):
    """Returns the timer interval.

    Returns:
      The timer interval, in seconds.
    """
    return self._interval

  def setInterval(self, interval):
    """Sets the timer interval.

    Args:
      interval: The timer interval in seconds, as a float or int.
    """
    self._interval = interval
